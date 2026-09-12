"""OpenRouter LLM provider adapter."""
from __future__ import annotations
import asyncio
import json
import logging
import ssl
import threading
import time
from typing import Any, Dict, Optional, Type, TypeVar

import certifi
import httpx

from ..interfaces import LLMProvider
from ..schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError, RetriableError, ToolCall

logger = logging.getLogger(__name__)
T = TypeVar("T")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/free"


class OpenRouterProvider:
    """Calls the OpenRouter API (OpenAI-compatible endpoint)."""

    provider_name = "openrouter"

    # Class-level rate limiter (shared across all instances)
    _rate_limit_lock = threading.Lock()
    _request_times: list[float] = []

    def __init__(self, api_key: str, model: Optional[str] = None, timeout: float = 60.0):
        import os
        self.api_key = api_key
        self.default_model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

    async def _enforce_rate_limit(self) -> None:
        """Enforce 15 requests per minute for OpenRouter API.

        Blocks until a request slot is available in the current 1-minute window.
        """
        with OpenRouterProvider._rate_limit_lock:
            now = time.time()
            # Remove timestamps older than 1 minute
            OpenRouterProvider._request_times = [
                ts for ts in OpenRouterProvider._request_times
                if now - ts < 60
            ]

            if len(OpenRouterProvider._request_times) >= 15:
                # Hit the limit, calculate wait time
                oldest_request = OpenRouterProvider._request_times[0]
                wait_time = 60 - (now - oldest_request)
                if wait_time > 0:
                    logger.warning(
                        f"OpenRouter rate limit: 15 requests reached, waiting {wait_time:.1f}s before next request"
                    )
                    # Release lock before sleeping to allow other code to proceed

        # Sleep outside the lock
        if len(OpenRouterProvider._request_times) >= 15:
            now = time.time()
            oldest_request = OpenRouterProvider._request_times[0]
            wait_time = 60 - (now - oldest_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                logger.info("OpenRouter rate limit wait complete, resuming requests")

        # Record this request
        with OpenRouterProvider._rate_limit_lock:
            now = time.time()
            OpenRouterProvider._request_times = [
                ts for ts in OpenRouterProvider._request_times
                if now - ts < 60
            ]
            OpenRouterProvider._request_times.append(now)

    def _get_ca_bundle_path(self) -> str:
        """Get CA bundle path, preferring combined bundle if available."""
        import os
        combined_path = "/app/backend/data/ca_bundle_combined.pem"
        if os.path.exists(combined_path):
            return combined_path
        return certifi.where()

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/repository-intelligence-platform",
            "X-Title": "Repository Intelligence Platform",
            "Content-Type": "application/json",
        }

    def _build_body(self, request: LLMRequest) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format:
            body["response_format"] = request.response_format
        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    }
                }
                for tool in request.tools
            ]
        return body

    async def generate(self, request: LLMRequest) -> LLMResponse:
        # Enforce rate limit before making the request
        await self._enforce_rate_limit()

        # Create SSL context with proper certificate verification
        # Use combined CA bundle that includes both certifi and Kaspersky root (for HTTPS inspection)
        ca_bundle = self._get_ca_bundle_path()
        ssl_context = ssl.create_default_context(cafile=ca_bundle)

        async with httpx.AsyncClient(verify=ssl_context, timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers=self._headers(),
                    json=self._build_body(request),
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                raise RetriableError(f"OpenRouter network error: {e}")

        if resp.status_code in (401, 403):
            raise NonRetriableError(f"OpenRouter auth error {resp.status_code}: {resp.text}", resp.status_code)
        if resp.status_code == 404:
            raise RetriableError(f"OpenRouter model not found or unavailable ({resp.status_code}): {resp.text}", resp.status_code)
        if resp.status_code == 400:
            raise NonRetriableError(f"OpenRouter bad request: {resp.text}", resp.status_code)
        if resp.status_code == 429:
            raise RetriableError(f"OpenRouter rate limited", resp.status_code)
        if resp.status_code >= 500:
            raise RetriableError(f"OpenRouter server error {resp.status_code}", resp.status_code)
        if resp.status_code != 200:
            raise NonRetriableError(f"OpenRouter unexpected status {resp.status_code}: {resp.text}", resp.status_code)


        data = resp.json()
        usage_data = data.get("usage", {})

        message = data["choices"][0]["message"]
        content = message.get("content") or ""

        tool_calls = None
        if "tool_calls" in message and message["tool_calls"]:
            tool_calls = [
                ToolCall(
                    tool_name=tc["function"]["name"],
                    parameters=json.loads(tc["function"].get("arguments", "{}")) if isinstance(tc["function"].get("arguments"), str) else tc["function"].get("arguments", {}),
                    tool_call_id=tc.get("id", f"openrouter-{i}"),
                )
                for i, tc in enumerate(message["tool_calls"])
            ]

        return LLMResponse(
            content=content,
            model=data.get("model", self.default_model),
            provider=self.provider_name,
            usage=TokenUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
            tool_calls=tool_calls,
        )

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        import json as _json
        json_schema = schema.model_json_schema()
        req = request.model_copy(update={
            "response_format": {"type": "json_object"},
            "messages": list(request.messages) + [],
        })
        # Inject schema instruction in system message if not already present
        messages = list(req.messages)
        schema_instruction = (
            f"\n\nYou must respond with a valid JSON object matching this schema:\n{_json.dumps(json_schema, indent=2)}"
        )
        # Append to last user message
        last = messages[-1]
        from ..schemas import Message, MessageRole
        messages[-1] = Message(role=last.role, content=last.content + schema_instruction)
        req = req.model_copy(update={"messages": messages})
        response = await self.generate(req)
        try:
            raw = _json.loads(response.content)
            return schema.model_validate(raw)
        except Exception as e:
            raise NonRetriableError(f"OpenRouter structured parse failed: {e}")
