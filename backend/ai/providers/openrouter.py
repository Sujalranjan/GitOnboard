"""OpenRouter LLM provider adapter."""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, Type, TypeVar

import httpx

from ..interfaces import LLMProvider
from ..schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError, RetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/free"


class OpenRouterProvider:
    """Calls the OpenRouter API (OpenAI-compatible endpoint)."""

    provider_name = "openrouter"

    def __init__(self, api_key: str, model: Optional[str] = None, timeout: float = 60.0):
        import os
        self.api_key = api_key
        self.default_model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

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
        return body

    async def generate(self, request: LLMRequest) -> LLMResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.default_model),
            provider=self.provider_name,
            usage=TokenUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
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
