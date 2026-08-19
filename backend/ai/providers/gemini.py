"""Google Gemini LLM provider adapter."""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, Optional, Type, TypeVar

import httpx

from ..interfaces import LLMProvider
from ..schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError, RetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider:
    """Calls the Google Gemini REST API."""

    provider_name = "gemini"

    def __init__(self, api_key: str, model: Optional[str] = None, timeout: float = 60.0):
        self.api_key = api_key
        self.default_model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

    def _build_payload(self, request: LLMRequest) -> Dict[str, Any]:
        contents = []
        system_instruction = None

        for m in request.messages:
            if m.role.value == "system":
                system_instruction = {"parts": [{"text": m.content}]}
            else:
                role = "user" if m.role.value == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": m.content}]
                })

        # Ensure there is at least one content part
        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Hello"}]}]

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            }
        }

        if system_instruction:
            payload["systemInstruction"] = system_instruction

        if request.response_format and request.response_format.get("type") == "json_object":
            payload["generationConfig"]["responseMimeType"] = "application/json"

        return payload

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model_name = request.model or self.default_model
        url = f"{GEMINI_BASE_URL}/{model_name}:generateContent?key={self.api_key}"
        payload = self._build_payload(request)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(url, json=payload)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                raise RetriableError(f"Gemini connection/timeout failed: {e}")

        if resp.status_code in (401, 403):
            raise NonRetriableError(f"Gemini auth error ({resp.status_code}): {resp.text}", resp.status_code)
        if resp.status_code == 400:
            raise NonRetriableError(f"Gemini bad request ({resp.status_code}): {resp.text}", resp.status_code)
        if resp.status_code == 404:
            raise NonRetriableError(f"Gemini model not found: {resp.text}", resp.status_code)
        if resp.status_code == 429:
            raise RetriableError(f"Gemini rate limit exceeded: {resp.text}", resp.status_code)
        if resp.status_code >= 500:
            raise RetriableError(f"Gemini server error ({resp.status_code}): {resp.text}", resp.status_code)

        try:
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RetriableError("Gemini returned empty candidate list")

            parts = candidates[0].get("content", {}).get("parts", [])
            content_text = "".join(p.get("text", "") for p in parts)

            usage_meta = data.get("usageMetadata", {})
            usage = TokenUsage(
                prompt_tokens=usage_meta.get("promptTokenCount", 0),
                completion_tokens=usage_meta.get("candidatesTokenCount", 0),
                total_tokens=usage_meta.get("totalTokenCount", 0),
            )

            return LLMResponse(
                content=content_text,
                model=model_name,
                provider=self.provider_name,
                usage=usage,
            )
        except Exception as e:
            if isinstance(e, (NonRetriableError, RetriableError)):
                raise
            raise RetriableError(f"Failed to parse Gemini response: {e}")

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        req_copy = request.model_copy(deep=True)
        req_copy.response_format = {"type": "json_object"}
        response = await self.generate(req_copy)

        try:
            cleaned = response.content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            return schema.model_validate(parsed)
        except Exception as e:
            logger.error(f"GeminiProvider: Failed to parse structured output into {schema.__name__}: {e}")
            raise NonRetriableError(f"Structured validation failed: {e}")
