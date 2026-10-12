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
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


MAX_REQUESTS_PER_MINUTE = 20


class OpenRouterProvider:
    """Calls the OpenRouter API (OpenAI-compatible endpoint)."""

    provider_name = "openrouter"

    # Class-level rate limiter & cooldown (shared across all instances)
    _rate_limit_lock = threading.Lock()
    _request_times: list[float] = []
    _cooldown_until: float = 0.0

    def __init__(self, api_key: str, model: Optional[str] = None, timeout: float = 120.0):
        import os
        self.api_key = api_key
        self.default_model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
        self.timeout = float(os.environ.get("OPENROUTER_TIMEOUT", str(timeout)))

    @classmethod
    def _parse_time_str(cls, val: Optional[str]) -> Optional[float]:
        """Parse time string like '1', '2.5', '27.645s', '1m26.4s', or '500ms' into seconds."""
        if not val:
            return None
        val = val.strip().lower()
        try:
            return float(val)
        except ValueError:
            pass

        import re
        total_seconds = 0.0
        m_match = re.search(r'(\d+(?:\.\d+)?)m(?!s)', val)
        if m_match:
            total_seconds += float(m_match.group(1)) * 60.0
        s_match = re.search(r'(\d+(?:\.\d+)?)s', val)
        if s_match:
            total_seconds += float(s_match.group(1))
        ms_match = re.search(r'(\d+(?:\.\d+)?)ms', val)
        if ms_match:
            total_seconds += float(ms_match.group(1)) / 1000.0

        return total_seconds if total_seconds > 0 else None

    @classmethod
    def set_cooldown(cls, seconds: float, reason: str = "") -> None:
        """Set a global cooldown until now + seconds as instructed by OpenRouter."""
        with cls._rate_limit_lock:
            target_time = time.time() + seconds
            if target_time > cls._cooldown_until:
                cls._cooldown_until = target_time
                logger.info(
                    f"[OpenRouter Cooldown] Cooldown active for {seconds:.2f}s (until {cls._cooldown_until:.2f}). Reason: {reason}"
                )

    @classmethod
    def get_remaining_cooldown(cls) -> float:
        """Return remaining seconds of active OpenRouter cooldown (0.0 if expired)."""
        with cls._rate_limit_lock:
            remaining = cls._cooldown_until - time.time()
            return max(remaining, 0.0)

    async def _enforce_rate_limit(self) -> None:
        """Enforce OpenRouter-mandated cooldown and 20 requests per minute rate limit.

        Blocks until any active cooldown expires and a request slot is available.
        """
        while True:
            # 1. Respect OpenRouter cooldown time
            while True:
                remaining = OpenRouterProvider.get_remaining_cooldown()
                if remaining > 0:
                    logger.warning(
                        f"[OpenRouter Cooldown] Waiting {remaining:.2f}s for OpenRouter cooldown to expire before request..."
                    )
                    await asyncio.sleep(remaining)
                else:
                    break

            # 2. Check 20 requests in the current 60-second window
            wait_time = 0.0
            with OpenRouterProvider._rate_limit_lock:
                now = time.time()
                OpenRouterProvider._request_times = [
                    ts for ts in OpenRouterProvider._request_times
                    if now - ts < 60
                ]

                if len(OpenRouterProvider._request_times) >= MAX_REQUESTS_PER_MINUTE:
                    oldest_request = OpenRouterProvider._request_times[0]
                    wait_time = max(wait_time, 60.0 - (now - oldest_request))

            if wait_time > 0:
                logger.warning(
                    f"OpenRouter rate limit reached (RPM={len(OpenRouterProvider._request_times)}/{MAX_REQUESTS_PER_MINUTE}), waiting {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)
                continue

            # Acquire request slot under lock
            with OpenRouterProvider._rate_limit_lock:
                now = time.time()
                OpenRouterProvider._request_times = [
                    ts for ts in OpenRouterProvider._request_times
                    if now - ts < 60
                ]
                if len(OpenRouterProvider._request_times) >= MAX_REQUESTS_PER_MINUTE:
                    continue

                OpenRouterProvider._request_times.append(now)
                break

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
        # Build messages, preserving native tool_calls from previous responses
        messages = []
        for m in request.messages:
            msg_dict = {"role": m.role.value, "content": m.content}
            # Include native tool_calls if present (for tool call continuation)
            if m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            messages.append(msg_dict)

        body: Dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": messages,
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

    async def generate(self, request: LLMRequest, max_retries: int = 3) -> LLMResponse:
        ca_bundle = self._get_ca_bundle_path()
        ssl_context = ssl.create_default_context(cafile=ca_bundle)

        for attempt in range(max_retries + 1):
            # Enforce rate limit before making the request
            await self._enforce_rate_limit()

            async with httpx.AsyncClient(verify=ssl_context, timeout=self.timeout) as client:
                try:
                    resp = await client.post(
                        f"{OPENROUTER_BASE_URL}/chat/completions",
                        headers=self._headers(),
                        json=self._build_body(request),
                    )
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    if attempt < max_retries:
                        logger.warning(f"[OpenRouter Retry] Network error ({e}), retrying {attempt + 1}/{max_retries}...")
                        await asyncio.sleep(1.0)
                        continue
                    raise RetriableError(f"OpenRouter network error: {e}")

            if resp.status_code in (401, 403):
                raise NonRetriableError(f"OpenRouter auth error {resp.status_code}: {resp.text}", resp.status_code)
            if resp.status_code == 404:
                raise RetriableError(f"OpenRouter model not found or unavailable ({resp.status_code}): {resp.text}", resp.status_code)
            if resp.status_code == 413:
                raise NonRetriableError(f"OpenRouter context/request too large (413): {resp.text}", 413)
            if resp.status_code == 400:
                raise NonRetriableError(f"OpenRouter bad request: {resp.text}", resp.status_code)
            if resp.status_code == 429:
                retry_after_str = resp.headers.get("retry-after")
                cooldown_sec = self._parse_time_str(retry_after_str)
                wait_time = max(cooldown_sec or 1.0, 1.0)
                self.set_cooldown(wait_time, reason=f"HTTP 429 from OpenRouter on attempt {attempt + 1}")

                if attempt < max_retries:
                    logger.warning(
                        f"[OpenRouter 429 Cooldown] Rate limited by OpenRouter. Respecting cooldown of {wait_time:.2f}s before retry {attempt + 1}/{max_retries}..."
                    )
                    await asyncio.sleep(wait_time)
                    continue

                error_detail = "OpenRouter rate limited (429)"
                if retry_after_str:
                    error_detail += f", retry_after={retry_after_str}s"
                elif cooldown_sec:
                    error_detail += f", retry_after={cooldown_sec:.1f}s"
                raise RetriableError(error_detail, resp.status_code)
            if resp.status_code >= 500:
                if attempt < max_retries:
                    logger.warning(f"[OpenRouter Retry] Server error {resp.status_code}, retrying {attempt + 1}/{max_retries}...")
                    await asyncio.sleep(1.0)
                    continue
                raise RetriableError(f"OpenRouter server error {resp.status_code}", resp.status_code)
            if resp.status_code != 200:
                raise NonRetriableError(f"OpenRouter unexpected status {resp.status_code}: {resp.text}", resp.status_code)

            # Success
            break


        data = resp.json()

        # Check for error payload at HTTP 200 (OpenRouter can return errors with success status)
        if "error" in data:
            error_info = data.get("error", {})
            error_msg = error_info.get("message", "Unknown error")
            error_code = error_info.get("code", 500)
            # Treat provider errors as retriable (they may recover)
            raise RetriableError(f"OpenRouter provider error {error_code}: {error_msg}", error_code)

        if "choices" not in data:
            raise NonRetriableError(f"OpenRouter invalid response: missing 'choices' field. Response keys: {list(data.keys())}", 200)

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

        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)
        total_tokens = usage_data.get("total_tokens", 0)
        logger.info(
            f"[OpenRouter Telemetry] model={data.get('model')}, prompt_tokens={prompt_tokens}, "
            f"completion_tokens={completion_tokens}, total_tokens={total_tokens}"
        )

        return LLMResponse(
            content=content,
            model=data.get("model", self.default_model),
            provider=self.provider_name,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
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
