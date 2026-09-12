"""Google Gemini LLM provider adapter."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import ssl
import threading
import time
from typing import Any, Dict, Optional, Type, TypeVar

import certifi
import httpx

from ..interfaces import LLMProvider
from ..schemas import LLMRequest, LLMResponse, TokenUsage, ToolCall, NonRetriableError, RetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.6-flash"


class GeminiProvider:
    """Calls the Google Gemini REST API."""

    provider_name = "gemini"

    # Class-level rate limiter (shared across all instances)
    _rate_limit_lock = threading.Lock()
    _request_times: list[float] = []

    def __init__(self, api_key: str, model: Optional[str] = None, timeout: float = 60.0):
        self.api_key = api_key
        self.default_model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

    def _log_gemini_error(self, status_code: int, response_text: str, response_headers: dict) -> None:
        """Log detailed Gemini error information for diagnostics."""
        logger.error(f"[GEMINI_ERROR] status_code={status_code}")

        # Try to parse JSON error response
        try:
            error_data = json.loads(response_text)

            # Log basic error info
            if "error" in error_data:
                error = error_data["error"]
                if isinstance(error, dict):
                    message = error.get("message", "")
                    code = error.get("code", "")
                    status = error.get("status", "")

                    logger.error(f"[GEMINI_ERROR] message={message!r}")
                    logger.error(f"[GEMINI_ERROR] status={status}")
                    logger.error(f"[GEMINI_ERROR] code={code}")

                    # For 429, extract quota details
                    if status_code == 429 and "details" in error:
                        details = error.get("details", [])
                        if isinstance(details, list):
                            for detail in details:
                                if isinstance(detail, dict) and "@type" in detail:
                                    detail_type = detail.get("@type", "")
                                    logger.error(f"[GEMINI_ERROR] detail_type={detail_type}")

                                    # Parse QuotaFailure details
                                    if "quotaFailures" in detail:
                                        quota_failures = detail.get("quotaFailures", [])
                                        if isinstance(quota_failures, list):
                                            for quota_failure in quota_failures:
                                                if isinstance(quota_failure, dict):
                                                    metric = quota_failure.get("metric", "")
                                                    description = quota_failure.get("description", "")
                                                    logger.error(f"[GEMINI_ERROR_429] quota_metric={metric!r}")
                                                    logger.error(f"[GEMINI_ERROR_429] quota_description={description!r}")

                                    # Parse RetryInfo details
                                    if "retryDelay" in detail:
                                        retry_delay = detail.get("retryDelay", {})
                                        if isinstance(retry_delay, dict):
                                            seconds = retry_delay.get("seconds", 0)
                                            nanos = retry_delay.get("nanos", 0)
                                            total_seconds = seconds + (nanos / 1_000_000_000)
                                            logger.error(f"[GEMINI_ERROR_429] retry_delay_seconds={total_seconds}")
            else:
                logger.error(f"[GEMINI_ERROR] response_text={response_text[:500]}")
        except json.JSONDecodeError:
            logger.error(f"[GEMINI_ERROR] response_text={response_text[:500]}")

        # Log relevant headers
        if "retry-after" in response_headers:
            logger.error(f"[GEMINI_ERROR] retry_after_header={response_headers['retry-after']}")
        if "ratelimit-reset-after" in response_headers:
            logger.error(f"[GEMINI_ERROR] ratelimit_reset_after={response_headers['ratelimit-reset-after']}")

    async def _enforce_rate_limit(self) -> None:
        """Enforce 10 requests per minute for Gemini API.

        Blocks until a request slot is available in the current 1-minute window.
        """
        with GeminiProvider._rate_limit_lock:
            now = time.time()
            # Remove timestamps older than 1 minute
            GeminiProvider._request_times = [
                ts for ts in GeminiProvider._request_times
                if now - ts < 60
            ]

            if len(GeminiProvider._request_times) >= 10:
                # Hit the limit, calculate wait time
                oldest_request = GeminiProvider._request_times[0]
                wait_time = 60 - (now - oldest_request)
                if wait_time > 0:
                    logger.warning(
                        f"Gemini rate limit: 10 requests reached, waiting {wait_time:.1f}s before next request"
                    )
                    # Release lock before sleeping to allow other code to proceed

        # Sleep outside the lock
        if len(GeminiProvider._request_times) >= 10:
            now = time.time()
            oldest_request = GeminiProvider._request_times[0]
            wait_time = 60 - (now - oldest_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                logger.info("Gemini rate limit wait complete, resuming requests")

        # Record this request
        with GeminiProvider._rate_limit_lock:
            now = time.time()
            GeminiProvider._request_times = [
                ts for ts in GeminiProvider._request_times
                if now - ts < 60
            ]
            GeminiProvider._request_times.append(now)

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

        if request.tools:
            payload["tools"] = [{
                "functionDeclarations": [
                    {"name": t.name, "description": t.description, "parameters": t.parameters}
                    for t in request.tools
                ]
            }]

        return payload

    def _get_ca_bundle_path(self) -> str:
        """Get CA bundle path, preferring combined bundle if available."""
        combined_path = "/app/backend/data/ca_bundle_combined.pem"
        if os.path.exists(combined_path):
            return combined_path
        return certifi.where()

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model_name = request.model or self.default_model
        url = f"{GEMINI_BASE_URL}/{model_name}:generateContent?key={self.api_key}"
        payload = self._build_payload(request)
        logger.info("[GEMINI_GENERATE] Starting request to model: %s", model_name)

        # Enforce rate limit before making the request
        await self._enforce_rate_limit()

        # Create SSL context with proper certificate verification
        # Use combined CA bundle that includes both certifi and Kaspersky root (for HTTPS inspection)
        ca_bundle = self._get_ca_bundle_path()
        ssl_context = ssl.create_default_context(cafile=ca_bundle)

        async with httpx.AsyncClient(verify=ssl_context, timeout=self.timeout) as client:
            try:
                resp = await client.post(url, json=payload)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                raise RetriableError(f"Gemini connection/timeout failed: {e}")

            # Convert headers to dict for logging (MUST be inside context manager)
            try:
                headers_dict = dict(resp.headers) if resp.headers else {}
            except Exception as e:
                headers_dict = {}
                logger.error("[GEMINI] Failed to convert headers: %s", e)

            logger.error("[GEMINI] Status code: %d, response length: %d", resp.status_code, len(resp.text))

            if resp.status_code in (401, 403):
                logger.error("[GEMINI] Processing auth error")
                self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                raise NonRetriableError(f"Gemini auth error ({resp.status_code}): {resp.text}", resp.status_code)
            if resp.status_code == 400:
                logger.error("[GEMINI] Processing 400 error")
                self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                raise NonRetriableError(f"Gemini bad request ({resp.status_code}): {resp.text}", resp.status_code)
            if resp.status_code == 404:
                logger.error("[GEMINI] Processing 404 error")
                self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                raise NonRetriableError(f"Gemini model not found: {resp.text}", resp.status_code)
            if resp.status_code == 429:
                logger.error("[GEMINI_429] Received 429, response text length: %d bytes", len(resp.text))
                logger.error("[GEMINI_429] Response text (first 500 chars): %s", resp.text[:500])
                self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                raise RetriableError(f"Gemini rate limit exceeded: {resp.text}", resp.status_code)
            if resp.status_code >= 500:
                logger.error("[GEMINI] Processing 5xx error: %d", resp.status_code)
                self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                raise RetriableError(f"Gemini server error ({resp.status_code}): {resp.text}", resp.status_code)

        try:
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RetriableError("Gemini returned empty candidate list")

            parts = candidates[0].get("content", {}).get("parts", [])
            content_text = "".join(p.get("text", "") for p in parts if "text" in p)
            function_call_parts = [p["functionCall"] for p in parts if "functionCall" in p]

            usage_meta = data.get("usageMetadata", {})
            usage = TokenUsage(
                prompt_tokens=usage_meta.get("promptTokenCount", 0),
                completion_tokens=usage_meta.get("candidatesTokenCount", 0),
                total_tokens=usage_meta.get("totalTokenCount", 0),
            )

            tool_calls = None
            if function_call_parts:
                tool_calls = [
                    ToolCall(
                        tool_name=fc.get("name", ""),
                        parameters=fc.get("args", {}) or {},
                        tool_call_id=f"gemini-{i}",
                    )
                    for i, fc in enumerate(function_call_parts)
                ]

            return LLMResponse(
                content=content_text,
                model=model_name,
                provider=self.provider_name,
                usage=usage,
                tool_calls=tool_calls,
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
