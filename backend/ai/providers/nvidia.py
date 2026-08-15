"""NVIDIA Free Tier LLM provider adapter (NIM API — OpenAI-compatible)."""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, Type, TypeVar

import httpx

from ..interfaces import LLMProvider
from ..schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError, RetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "meta/llama-3.1-8b-instruct"


class NvidiaProvider:
    """Calls the NVIDIA NIM API (OpenAI-compatible)."""

    provider_name = "nvidia"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 90.0):
        self.api_key = api_key
        self.default_model = model
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_body(self, request: LLMRequest) -> Dict[str, Any]:
        return {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

    async def generate(self, request: LLMRequest) -> LLMResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    f"{NVIDIA_BASE_URL}/chat/completions",
                    headers=self._headers(),
                    json=self._build_body(request),
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                raise RetriableError(f"NVIDIA network error: {e}")

        if resp.status_code in (401, 403):
            raise NonRetriableError(f"NVIDIA auth error {resp.status_code}: {resp.text}", resp.status_code)
        if resp.status_code == 400:
            raise NonRetriableError(f"NVIDIA bad request: {resp.text}", resp.status_code)
        if resp.status_code == 429:
            raise RetriableError(f"NVIDIA rate limited", resp.status_code)
        if resp.status_code >= 500:
            raise RetriableError(f"NVIDIA server error {resp.status_code}", resp.status_code)
        if resp.status_code != 200:
            raise NonRetriableError(f"NVIDIA unexpected status {resp.status_code}: {resp.text}", resp.status_code)

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
        messages = list(request.messages)
        schema_instruction = (
            f"\n\nRespond with a valid JSON object matching this schema:\n{_json.dumps(json_schema, indent=2)}"
        )
        from ..schemas import Message
        last = messages[-1]
        messages[-1] = Message(role=last.role, content=last.content + schema_instruction)
        req = request.model_copy(update={"messages": messages, "response_format": {"type": "json_object"}})
        response = await self.generate(req)
        try:
            raw = _json.loads(response.content)
            return schema.model_validate(raw)
        except Exception as e:
            raise NonRetriableError(f"NVIDIA structured parse failed: {e}")
