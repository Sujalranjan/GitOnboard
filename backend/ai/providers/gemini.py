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
DEFAULT_MODEL = "gemini-3.8-flash"


MAX_REQUESTS_PER_MINUTE = 5
MAX_TOKENS_PER_MINUTE = 250000


class GeminiProvider:
    """Calls the Google Gemini REST API."""

    provider_name = "gemini"

    # Class-level rate limiter & cooldown (shared across all instances)
    _rate_limit_lock = threading.Lock()
    _request_times: list[float] = []
    _token_usages: list[tuple[float, int]] = []
    _cooldown_until: float = 0.0

    def __init__(self, api_key: str, model: Optional[str] = None, timeout: float = 60.0):
        self.api_key = api_key
        self.default_model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

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
        """Set a global cooldown until now + seconds as instructed by Gemini."""
        with cls._rate_limit_lock:
            target_time = time.time() + seconds
            if target_time > cls._cooldown_until:
                cls._cooldown_until = target_time
                logger.info(
                    f"[Gemini Cooldown] Cooldown active for {seconds:.2f}s (until {cls._cooldown_until:.2f}). Reason: {reason}"
                )

    @classmethod
    def get_remaining_cooldown(cls) -> float:
        """Return remaining seconds of active Gemini cooldown (0.0 if expired)."""
        with cls._rate_limit_lock:
            remaining = cls._cooldown_until - time.time()
            return max(remaining, 0.0)

    @classmethod
    def _estimate_request_tokens(cls, request: LLMRequest) -> int:
        """Roughly estimate prompt token size of a request before dispatch."""
        chars = sum(len(m.content or "") for m in request.messages)
        if request.tools:
            chars += sum(len(t.name) + len(t.description) + len(str(t.parameters)) for t in request.tools)
        return max(int(chars / 3.5), 1)

    async def _enforce_rate_limit(self, estimated_tokens: int = 0) -> None:
        """Enforce Gemini-mandated cooldown, 5 RPM, and 250K TPM rate limits.

        Blocks until any active cooldown expires and capacity is available.
        """
        while True:
            # 1. Respect Gemini cooldown time
            while True:
                remaining = GeminiProvider.get_remaining_cooldown()
                if remaining > 0:
                    logger.warning(
                        f"[Gemini Cooldown] Waiting {remaining:.2f}s for Gemini cooldown to expire before request..."
                    )
                    await asyncio.sleep(remaining)
                else:
                    break

            # 2. Check 5 requests and 250,000 tokens in the current 60-second window
            wait_time = 0.0
            with GeminiProvider._rate_limit_lock:
                now = time.time()
                # Prune entries older than 60s
                GeminiProvider._request_times = [
                    ts for ts in GeminiProvider._request_times
                    if now - ts < 60
                ]
                GeminiProvider._token_usages = [
                    (ts, count) for ts, count in GeminiProvider._token_usages
                    if now - ts < 60
                ]

                # Check RPM
                if len(GeminiProvider._request_times) >= MAX_REQUESTS_PER_MINUTE:
                    oldest_req = GeminiProvider._request_times[0]
                    wait_time = max(wait_time, 60.0 - (now - oldest_req))

                # Check TPM
                current_tokens = sum(count for _, count in GeminiProvider._token_usages)
                if current_tokens + estimated_tokens > MAX_TOKENS_PER_MINUTE and GeminiProvider._token_usages:
                    oldest_token_ts = GeminiProvider._token_usages[0][0]
                    wait_time = max(wait_time, 60.0 - (now - oldest_token_ts))

            if wait_time > 0:
                logger.warning(
                    f"Gemini rate limit reached (RPM={len(GeminiProvider._request_times)}/{MAX_REQUESTS_PER_MINUTE}, "
                    f"TPM={current_tokens}+{estimated_tokens}/{MAX_TOKENS_PER_MINUTE}), waiting {wait_time:.2f}s..."
                )
                await asyncio.sleep(wait_time)
                continue

            # Capacity is available; acquire request slot and tentative token reservation
            with GeminiProvider._rate_limit_lock:
                now = time.time()
                GeminiProvider._request_times = [
                    ts for ts in GeminiProvider._request_times
                    if now - ts < 60
                ]
                GeminiProvider._token_usages = [
                    (ts, count) for ts, count in GeminiProvider._token_usages
                    if now - ts < 60
                ]
                # Re-verify under lock
                current_tokens = sum(count for _, count in GeminiProvider._token_usages)
                if (
                    len(GeminiProvider._request_times) >= MAX_REQUESTS_PER_MINUTE
                    or (current_tokens + estimated_tokens > MAX_TOKENS_PER_MINUTE and GeminiProvider._token_usages)
                ):
                    continue

                GeminiProvider._request_times.append(now)
                # Temporarily reserve estimated tokens until response updates with actual usage
                if estimated_tokens > 0:
                    GeminiProvider._token_usages.append((now, estimated_tokens))
                break

    @classmethod
    def _record_actual_tokens(cls, actual_tokens: int, estimated_tokens: int, reservation_time: float) -> None:
        """Update token usage history with actual tokens reported by Gemini response."""
        with cls._rate_limit_lock:
            # Remove tentative reservation if found
            for i, (ts, count) in enumerate(cls._token_usages):
                if ts == reservation_time and count == estimated_tokens:
                    cls._token_usages.pop(i)
                    break
            # Add actual token usage
            cls._token_usages.append((time.time(), actual_tokens))

    def _extract_retry_delay(self, response_text: str, response_headers: dict) -> Optional[float]:
        """Extract retry delay seconds from Gemini 429 response body or headers."""
        # 1. Check retry-after header
        retry_after = response_headers.get("retry-after")
        if retry_after:
            parsed = self._parse_time_str(retry_after)
            if parsed and parsed > 0:
                return parsed

        # 2. Check ratelimit-reset-after header
        reset_after = response_headers.get("ratelimit-reset-after")
        if reset_after:
            parsed = self._parse_time_str(reset_after)
            if parsed and parsed > 0:
                return parsed

        # 3. Check JSON error details
        try:
            error_data = json.loads(response_text)
            error = error_data.get("error", {})
            if isinstance(error, dict):
                details = error.get("details", [])
                if isinstance(details, list):
                    for detail in details:
                        if isinstance(detail, dict) and "retryDelay" in detail:
                            retry_delay = detail.get("retryDelay", {})
                            if isinstance(retry_delay, dict):
                                seconds = float(retry_delay.get("seconds", 0))
                                nanos = float(retry_delay.get("nanos", 0))
                                total_seconds = seconds + (nanos / 1_000_000_000)
                                if total_seconds > 0:
                                    return total_seconds
        except Exception:
            pass

        return None

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
                "maxOutputTokens": min(request.max_tokens or 8192, 8192),
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

    async def generate(self, request: LLMRequest, max_retries: int = 3) -> LLMResponse:
        model_name = request.model or self.default_model
        url = f"{GEMINI_BASE_URL}/{model_name}:generateContent?key={self.api_key}"
        payload = self._build_payload(request)
        logger.info("[GEMINI_GENERATE] Starting request to model: %s", model_name)

        ca_bundle = self._get_ca_bundle_path()
        ssl_context = ssl.create_default_context(cafile=ca_bundle)
        estimated_tokens = self._estimate_request_tokens(request)

        for attempt in range(max_retries + 1):
            reservation_ts = time.time()
            # Enforce rate limit & cooldown before making the request
            await self._enforce_rate_limit(estimated_tokens)

            async with httpx.AsyncClient(verify=ssl_context, timeout=self.timeout) as client:
                try:
                    resp = await client.post(url, json=payload)
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    if attempt < max_retries:
                        logger.warning(f"[Gemini Retry] Network error ({e}), retrying {attempt + 1}/{max_retries}...")
                        await asyncio.sleep(1.0)
                        continue
                    raise RetriableError(f"Gemini connection/timeout failed: {e}")

                # Convert headers to dict for logging (MUST be inside context manager)
                try:
                    headers_dict = dict(resp.headers) if resp.headers else {}
                except Exception as e:
                    headers_dict = {}
                    logger.error("[GEMINI] Failed to convert headers: %s", e)

                logger.debug("[GEMINI] Status code: %d, response length: %d", resp.status_code, len(resp.text))

                if resp.status_code in (401, 403):
                    logger.error("[GEMINI] Processing auth error")
                    self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                    raise NonRetriableError(f"Gemini auth error ({resp.status_code}): {resp.text}", resp.status_code)
                if resp.status_code == 404:
                    logger.error("[GEMINI] Processing 404 error")
                    self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                    raise NonRetriableError(f"Gemini model not found: {resp.text}", resp.status_code)
                if resp.status_code == 413:
                    raise NonRetriableError(f"Gemini context/request too large (413): {resp.text}", 413)
                if resp.status_code == 400:
                    logger.error("[GEMINI] Processing 400 error")
                    self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                    raise NonRetriableError(f"Gemini bad request ({resp.status_code}): {resp.text}", resp.status_code)
                if resp.status_code == 429:
                    logger.warning("[GEMINI_429] Received 429, response text length: %d bytes", len(resp.text))
                    self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                    retry_sec = self._extract_retry_delay(resp.text, headers_dict)
                    wait_time = max(retry_sec or 1.0, 1.0)
                    self.set_cooldown(wait_time, reason=f"HTTP 429 from Gemini on attempt {attempt + 1}")

                    if attempt < max_retries:
                        logger.warning(
                            f"[Gemini 429 Cooldown] Rate limited by Gemini. Respecting cooldown of {wait_time:.2f}s before retry {attempt + 1}/{max_retries}..."
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    error_detail = "Gemini rate limit exceeded (429)"
                    if retry_sec:
                        error_detail += f", retry_after={retry_sec:.1f}s"
                    raise RetriableError(error_detail, resp.status_code)
                if resp.status_code >= 500:
                    logger.error("[GEMINI] Processing 5xx error: %d", resp.status_code)
                    self._log_gemini_error(resp.status_code, resp.text, headers_dict)
                    if attempt < max_retries:
                        logger.warning(f"[Gemini Retry] Server error {resp.status_code}, retrying {attempt + 1}/{max_retries}...")
                        await asyncio.sleep(1.0)
                        continue
                    raise RetriableError(f"Gemini server error ({resp.status_code}): {resp.text}", resp.status_code)
                if resp.status_code != 200:
                    raise NonRetriableError(f"Gemini unexpected status {resp.status_code}: {resp.text}", resp.status_code)

                # Success break out of retry loop
                break

        try:
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RetriableError("Gemini returned empty candidate list")

            parts = candidates[0].get("content", {}).get("parts", [])
            content_text = "".join(p.get("text", "") for p in parts if "text" in p)
            function_call_parts = [p["functionCall"] for p in parts if "functionCall" in p]

            usage_meta = data.get("usageMetadata", {})
            actual_total_tokens = usage_meta.get("totalTokenCount", 0)
            prompt_tokens = usage_meta.get("promptTokenCount", 0)
            completion_tokens = usage_meta.get("candidatesTokenCount", 0)
            if actual_total_tokens > 0:
                self._record_actual_tokens(actual_total_tokens, estimated_tokens, reservation_ts)
                logger.info(
                    f"[Gemini Telemetry] estimated_tokens={estimated_tokens}, actual_prompt_tokens={prompt_tokens}, "
                    f"actual_total={actual_total_tokens}, diff={actual_total_tokens - estimated_tokens}"
                )

            usage = TokenUsage(
                prompt_tokens=usage_meta.get("promptTokenCount", 0),
                completion_tokens=usage_meta.get("candidatesTokenCount", 0),
                total_tokens=actual_total_tokens,
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
