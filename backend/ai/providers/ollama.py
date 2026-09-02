"""Local Ollama provider adapter (OpenAI-compatible /api/chat endpoint)."""
from __future__ import annotations
import json
import logging
import os
import time
from typing import Any, Dict, Type, TypeVar

import httpx

from ..interfaces import LLMProvider
from ..schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError, RetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")


class OllamaProvider:
    """Calls a local Ollama instance (assumed reachable at base_url)."""

    provider_name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = DEFAULT_MODEL, timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.default_model = model
        self.timeout = timeout

    def _build_body(self, request: LLMRequest, force_json: bool = False) -> Dict[str, Any]:
        # Respect request.model if provided, otherwise use provider's assigned default
        model_name = request.model or self.default_model
        body = {
            "model": model_name,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if force_json:
            body["format"] = "json"
        return body

    async def generate(self, request: LLMRequest) -> LLMResponse:
        # Respect request.model if provided, otherwise use provider's assigned default
        model_name = request.model or self.default_model
        logger.info(f"[LLM_LIFECYCLE] OllamaProvider: Sending request to {self.base_url}/api/chat (model: {model_name}, timeout={self.timeout}s)...")
        t0 = time.time()
        timeout_config = httpx.Timeout(timeout=self.timeout, connect=10.0, read=self.timeout, write=10.0)
        
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=self._build_body(request),
                )
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as e:
                elapsed = time.time() - t0
                logger.warning(f"[LLM_LIFECYCLE] OllamaProvider: Network/timeout/OOM error after {elapsed:.2f}s: {e}")
                raise RetriableError(f"Ollama connection/timeout/OOM failed: {e}")

        elapsed = time.time() - t0
        logger.info(f"[LLM_LIFECYCLE] OllamaProvider: HTTP response received (status={resp.status_code}, elapsed={elapsed:.2f}s)")

        if resp.status_code == 400:
            raise NonRetriableError(f"Ollama bad request: {resp.text}", resp.status_code)
        if resp.status_code >= 500:
            raise RetriableError(f"Ollama server error {resp.status_code}", resp.status_code)
        if resp.status_code != 200:
            raise NonRetriableError(f"Ollama unexpected {resp.status_code}: {resp.text}", resp.status_code)

        data = resp.json()
        content = data.get("message", {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count", 0)
        eval_tokens = data.get("eval_count", 0)
        total_tokens = prompt_tokens + eval_tokens

        logger.info(f"[LLM_LIFECYCLE] OllamaProvider: Successfully extracted text ({len(content)} chars, {total_tokens} tokens)")

        return LLMResponse(
            content=content,
            model=data.get("model", self.default_model),
            provider=self.provider_name,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=eval_tokens,
                total_tokens=total_tokens,
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
