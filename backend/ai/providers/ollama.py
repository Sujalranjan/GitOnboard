"""Local Ollama provider adapter (OpenAI-compatible /api/chat endpoint)."""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, Type, TypeVar

import httpx

from ..interfaces import LLMProvider
from ..schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError, RetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")

DEFAULT_MODEL = "qwen2.5-coder:7b"


class OllamaProvider:
    """Calls a local Ollama instance (assumed reachable at base_url)."""

    provider_name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = DEFAULT_MODEL, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.default_model = model
        self.timeout = timeout

    def _build_body(self, request: LLMRequest) -> Dict[str, Any]:
        return {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

    async def generate(self, request: LLMRequest) -> LLMResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=self._build_body(request),
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                raise RetriableError(f"Ollama connection failed: {e}")

        if resp.status_code == 400:
            raise NonRetriableError(f"Ollama bad request: {resp.text}", resp.status_code)
        if resp.status_code >= 500:
            raise RetriableError(f"Ollama server error {resp.status_code}", resp.status_code)
        if resp.status_code != 200:
            raise NonRetriableError(f"Ollama unexpected {resp.status_code}: {resp.text}", resp.status_code)

        data = resp.json()
        content = data.get("message", {}).get("content", "")
        return LLMResponse(
            content=content,
            model=data.get("model", self.default_model),
            provider=self.provider_name,
            usage=TokenUsage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            ),
        )

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        import json as _json
        json_schema = schema.model_json_schema()
        messages = list(request.messages)
        schema_instruction = (
            f"\n\nRespond ONLY with a valid JSON object matching:\n{_json.dumps(json_schema, indent=2)}"
        )
        from ..schemas import Message
        last = messages[-1]
        messages[-1] = Message(role=last.role, content=last.content + schema_instruction)
        req = request.model_copy(update={"messages": messages})
        response = await self.generate(req)
        try:
            # Strip markdown code fences if Ollama wraps output
            raw_text = response.content.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            raw = _json.loads(raw_text)
            return schema.model_validate(raw)
        except Exception as e:
            raise NonRetriableError(f"Ollama structured parse failed: {e}")
