"""Groq LLM provider adapter."""
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
from ..schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError, RetriableError, ToolCall

logger = logging.getLogger(__name__)
T = TypeVar("T")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_REQUESTS_PER_MINUTE = 30  # Groq rate limit
MAX_TOKENS_PER_MINUTE = 8000  # Groq rate limit


class GroqProvider:
    """Calls the Groq API (OpenAI-compatible endpoint)."""

    provider_name = "groq"

    # Class-level rate limiter & cooldown (shared across all instances)
    _rate_limit_lock = threading.Lock()
    _request_times: list[float] = []
    # Token usage history: list of (timestamp, token_count)
    _token_usages: list[tuple[float, int]] = []
    _cooldown_until: float = 0.0

    def __init__(self, api_key: str, model: Optional[str] = None, timeout: float = 60.0):
        self.api_key = api_key
        self.default_model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
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
        """Set a global cooldown until now + seconds as instructed by Groq."""
        with cls._rate_limit_lock:
            target_time = time.time() + seconds
            if target_time > cls._cooldown_until:
                cls._cooldown_until = target_time
                logger.info(
                    f"[Groq Cooldown] Cooldown active for {seconds:.2f}s (until {cls._cooldown_until:.2f}). Reason: {reason}"
                )

    @classmethod
    def get_remaining_cooldown(cls) -> float:
        """Return remaining seconds of active Groq cooldown (0.0 if expired)."""
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
        """Enforce Groq-mandated cooldown, 30 RPM, and 8,000 TPM rate limits.

        Blocks until any active cooldown expires and capacity (both requests and tokens) is available.
        """
        # Enforce single-request ceiling before window rate checks
        if estimated_tokens > MAX_TOKENS_PER_MINUTE:
            raise NonRetriableError(
                f"Request estimated at {estimated_tokens} tokens exceeds Groq single-request/TPM limit of {MAX_TOKENS_PER_MINUTE}. "
                "Context compaction required before transmission.",
                413,
            )

        while True:
            # 1. Respect Groq cooldown time
            while True:
                remaining = GroqProvider.get_remaining_cooldown()
                if remaining > 0:
                    logger.warning(
                        f"[Groq Cooldown] Waiting {remaining:.2f}s for Groq cooldown to expire before request..."
                    )
                    await asyncio.sleep(remaining)
                else:
                    break

            # 2. Check 30 requests and 8,000 tokens in the current 60-second window
            wait_time = 0.0
            with GroqProvider._rate_limit_lock:
                now = time.time()
                # Prune entries older than 60s
                GroqProvider._request_times = [
                    ts for ts in GroqProvider._request_times
                    if now - ts < 60
                ]
                GroqProvider._token_usages = [
                    (ts, count) for ts, count in GroqProvider._token_usages
                    if now - ts < 60
                ]

                # Check RPM
                if len(GroqProvider._request_times) >= MAX_REQUESTS_PER_MINUTE:
                    oldest_req = GroqProvider._request_times[0]
                    wait_time = max(wait_time, 60.0 - (now - oldest_req))

                # Check TPM
                current_tokens = sum(count for _, count in GroqProvider._token_usages)
                if current_tokens + estimated_tokens > MAX_TOKENS_PER_MINUTE and GroqProvider._token_usages:
                    oldest_token_ts = GroqProvider._token_usages[0][0]
                    wait_time = max(wait_time, 60.0 - (now - oldest_token_ts))

            if wait_time > 0:
                logger.warning(
                    f"Groq rate limit reached (RPM={len(GroqProvider._request_times)}/{MAX_REQUESTS_PER_MINUTE}, "
                    f"TPM={current_tokens}+{estimated_tokens}/{MAX_TOKENS_PER_MINUTE}), waiting {wait_time:.2f}s..."
                )
                await asyncio.sleep(wait_time)
                continue

            # Capacity is available; acquire request slot and tentative token reservation
            with GroqProvider._rate_limit_lock:
                now = time.time()
                GroqProvider._request_times = [
                    ts for ts in GroqProvider._request_times
                    if now - ts < 60
                ]
                GroqProvider._token_usages = [
                    (ts, count) for ts, count in GroqProvider._token_usages
                    if now - ts < 60
                ]
                # Re-verify under lock
                current_tokens = sum(count for _, count in GroqProvider._token_usages)
                if (
                    len(GroqProvider._request_times) >= MAX_REQUESTS_PER_MINUTE
                    or (current_tokens + estimated_tokens > MAX_TOKENS_PER_MINUTE and GroqProvider._token_usages)
                ):
                    continue

                GroqProvider._request_times.append(now)
                # Temporarily reserve estimated tokens until response updates with actual usage
                if estimated_tokens > 0:
                    GroqProvider._token_usages.append((now, estimated_tokens))
                break

    @classmethod
    def _record_actual_tokens(cls, actual_tokens: int, estimated_tokens: int, reservation_time: float) -> None:
        """Update token usage history with actual tokens reported by Groq response."""
        with cls._rate_limit_lock:
            # Remove tentative reservation if found
            for i, (ts, count) in enumerate(cls._token_usages):
                if ts == reservation_time and count == estimated_tokens:
                    cls._token_usages.pop(i)
                    break
            # Add actual token usage
            cls._token_usages.append((time.time(), actual_tokens))

    def _get_ca_bundle_path(self) -> str:
        """Get CA bundle path, preferring combined bundle if available."""
        combined_path = "/app/backend/data/ca_bundle_combined.pem"
        if os.path.exists(combined_path):
            return combined_path
        return certifi.where()

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_body(self, request: LLMRequest) -> Dict[str, Any]:
        messages = []
        for m in request.messages:
            msg_dict: Dict[str, Any] = {"role": m.role.value, "content": m.content}
            if m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            messages.append(msg_dict)

        # Groq max_tokens ceiling for openai/gpt-oss-120b is 65536
        max_tokens = min(request.max_tokens, 65536) if request.max_tokens else 65536

        body: Dict[str, Any] = {
            "model": request.model or self.default_model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": max_tokens,
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
                    },
                }
                for tool in request.tools
            ]
            if request.tool_choice:
                body["tool_choice"] = request.tool_choice
        return body

    def _log_rate_limit_headers(self, headers: httpx.Headers) -> None:
        """Log Groq rate limit telemetry headers, synchronize capacity, and check cooldowns."""
        remaining_req = headers.get("x-ratelimit-remaining-requests")
        remaining_tokens = headers.get("x-ratelimit-remaining-tokens")
        reset_req = headers.get("x-ratelimit-reset-requests")
        reset_tokens = headers.get("x-ratelimit-reset-tokens")
        retry_after = headers.get("retry-after")

        if remaining_req or remaining_tokens:
            logger.debug(
                f"[Groq RateLimit] remaining_rpd={remaining_req}, remaining_tpm={remaining_tokens}, "
                f"reset_req={reset_req}, reset_tokens={reset_tokens}"
            )

        # Synchronize local token counter if Groq reports remaining tokens
        if remaining_tokens is not None:
            try:
                rem_tok = int(remaining_tokens)
                consumed_from_groq = max(0, MAX_TOKENS_PER_MINUTE - rem_tok)
                with GroqProvider._rate_limit_lock:
                    local_sum = sum(cnt for _, cnt in GroqProvider._token_usages)
                    if consumed_from_groq > local_sum:
                        # Synchronize local counter with Groq's authoritative count
                        diff = consumed_from_groq - local_sum
                        GroqProvider._token_usages.append((time.time(), diff))
            except ValueError:
                pass

        # If Groq provided a retry-after header even on 200 OK, respect it as cooldown
        if retry_after:
            parsed = self._parse_time_str(retry_after)
            if parsed and parsed > 0:
                self.set_cooldown(parsed, reason="Proactive retry-after header from Groq")

    async def generate(self, request: LLMRequest, max_retries: int = 3) -> LLMResponse:
        ca_bundle = self._get_ca_bundle_path()
        ssl_context = ssl.create_default_context(cafile=ca_bundle)
        base_url = os.environ.get("GROQ_BASE_URL", GROQ_BASE_URL).rstrip("/")

        estimated_tokens = self._estimate_request_tokens(request)

        for attempt in range(max_retries + 1):
            reservation_ts = time.time()
            await self._enforce_rate_limit(estimated_tokens)

            async with httpx.AsyncClient(verify=ssl_context, timeout=self.timeout) as client:
                try:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers=self._headers(),
                        json=self._build_body(request),
                    )
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    if attempt < max_retries:
                        logger.warning(f"[Groq Retry] Network error ({e}), retrying {attempt + 1}/{max_retries}...")
                        await asyncio.sleep(1.0)
                        continue
                    raise RetriableError(f"Groq network error: {e}")

            # Track and log rate limit headers from Groq
            self._log_rate_limit_headers(resp.headers)

            if resp.status_code in (401, 403):
                raise NonRetriableError(f"Groq auth error {resp.status_code}: {resp.text}", resp.status_code)
            if resp.status_code == 404:
                raise RetriableError(f"Groq model not found or unavailable ({resp.status_code}): {resp.text}", resp.status_code)
            if resp.status_code == 413:
                # 413 Request Too Large / Context Overflow is NOT a rate-limit exhaustion event.
                # Must raise NonRetriableError so caller can prune context rather than treating as transient 429.
                raise NonRetriableError(f"Groq context/request too large (413): {resp.text}", 413)
            if resp.status_code == 400:
                try:
                    err_json = resp.json().get("error", {})
                    if err_json.get("code") == "tool_use_failed":
                        failed_gen = err_json.get("failed_generation", "")
                        logger.warning(
                            f"[GroqProvider] Groq 400 tool_use_failed. Recovering from failed_generation: {failed_gen[:200]}"
                        )
                        parsed_tool_calls = []
                        if failed_gen:
                            try:
                                gen_data = json.loads(failed_gen)
                                if isinstance(gen_data, dict) and "name" in gen_data:
                                    parsed_tool_calls.append(
                                        ToolCall(
                                            tool_call_id=f"call_{int(time.time()*1000)}",
                                            tool_name=gen_data.get("name"),
                                            parameters=gen_data.get("arguments", {}),
                                        )
                                    )
                            except Exception:
                                pass
                        return LLMResponse(
                            content=failed_gen if not parsed_tool_calls else "",
                            tool_calls=parsed_tool_calls or None,
                            model=request.model or self.default_model,
                            provider=self.provider_name,
                            usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                        )
                except Exception as recovery_err:
                    logger.debug(f"[GroqProvider] Could not recover from 400 error: {recovery_err}")
                raise NonRetriableError(f"Groq bad request: {resp.text}", resp.status_code)
            if resp.status_code == 429:
                retry_after_str = resp.headers.get("retry-after")
                cooldown_sec = self._parse_time_str(retry_after_str)
                if cooldown_sec is None:
                    reset_tokens = resp.headers.get("x-ratelimit-reset-tokens")
                    cooldown_sec = self._parse_time_str(reset_tokens)
                    if cooldown_sec:
                        cooldown_sec = min(cooldown_sec, 15.0)

                wait_time = max(cooldown_sec or 1.0, 1.0)
                self.set_cooldown(wait_time, reason=f"HTTP 429 from Groq on attempt {attempt + 1}")

                if attempt < max_retries:
                    logger.warning(
                        f"[Groq 429 Cooldown] Rate limited by Groq. Respecting cooldown of {wait_time:.2f}s before retry {attempt + 1}/{max_retries}..."
                    )
                    await asyncio.sleep(wait_time)
                    continue

                error_detail = "Groq rate limited (429)"
                if retry_after_str:
                    error_detail += f", retry_after={retry_after_str}s"
                elif cooldown_sec:
                    error_detail += f", retry_after={cooldown_sec:.1f}s"
                raise RetriableError(error_detail, resp.status_code)

            if resp.status_code >= 500:
                if attempt < max_retries:
                    logger.warning(f"[Groq Retry] Server error {resp.status_code}, retrying {attempt + 1}/{max_retries}...")
                    await asyncio.sleep(1.0)
                    continue
                raise RetriableError(f"Groq server error {resp.status_code}: {resp.text}", resp.status_code)
            if resp.status_code != 200:
                raise NonRetriableError(f"Groq unexpected status {resp.status_code}: {resp.text}", resp.status_code)

            # Success
            break

        data = resp.json()

        if "error" in data:
            error_info = data.get("error", {})
            error_msg = error_info.get("message", "Unknown error")
            error_code = error_info.get("code", 500)
            raise RetriableError(f"Groq provider error {error_code}: {error_msg}", error_code)

        if "choices" not in data or not data["choices"]:
            raise NonRetriableError(
                f"Groq invalid response: missing 'choices' field. Response keys: {list(data.keys())}",
                200,
            )

        usage_data = data.get("usage", {})
        actual_total_tokens = usage_data.get("total_tokens", 0)
        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)
        if actual_total_tokens > 0:
            self._record_actual_tokens(actual_total_tokens, estimated_tokens, reservation_ts)
            logger.info(
                f"[Groq Telemetry] estimated_tokens={estimated_tokens}, actual_prompt_tokens={prompt_tokens}, "
                f"actual_total={actual_total_tokens}, diff={actual_total_tokens - estimated_tokens}"
            )

        message = data["choices"][0]["message"]
        content = message.get("content") or ""

        tool_calls = None
        if "tool_calls" in message and message["tool_calls"]:
            tool_calls = [
                ToolCall(
                    tool_name=tc["function"]["name"],
                    parameters=json.loads(tc["function"].get("arguments", "{}"))
                    if isinstance(tc["function"].get("arguments"), str)
                    else tc["function"].get("arguments", {}),
                    tool_call_id=tc.get("id", f"groq-{i}"),
                )
                for i, tc in enumerate(message["tool_calls"])
            ]

        return LLMResponse(
            content=content,
            model=data.get("model", request.model or self.default_model),
            provider=self.provider_name,
            usage=TokenUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=actual_total_tokens,
            ),
            tool_calls=tool_calls,
        )

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        json_schema = schema.model_json_schema()
        req = request.model_copy(update={
            "response_format": {"type": "json_object"},
            "messages": list(request.messages) + [],
        })
        messages = list(req.messages)
        schema_instruction = (
            f"\n\nYou must respond with a valid JSON object matching this schema:\n{json.dumps(json_schema, indent=2)}"
        )
        last = messages[-1]
        from ..schemas import Message
        messages[-1] = Message(role=last.role, content=last.content + schema_instruction)
        req = req.model_copy(update={"messages": messages})
        response = await self.generate(req)
        try:
            raw = json.loads(response.content)
            return schema.model_validate(raw)
        except Exception as e:
            raise NonRetriableError(f"Groq structured parse failed: {e}")
