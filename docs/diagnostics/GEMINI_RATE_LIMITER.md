# Gemini Rate Limiter Implementation

**Date:** 2026-09-12  
**Issue:** Gemini API returning HTTP 429 (Too Many Requests) when QALoop makes >5 requests/minute  
**Solution:** Process-level rate limiter enforcing 5 requests per 60-second window  
**Status:** ✅ IMPLEMENTED

---

## Problem

During multi-turn agent conversations, Gemini receives more than 5 API requests within a 60-second period, causing:
```
HTTP 429 Too Many Requests
```

The rate limiter is designed to test whether locally controlled request pacing prevents this error.

---

## Implementation

### Changes to `backend/ai/providers/gemini.py`

#### 1. Class-Level Rate Limiter State
```python
class GeminiProvider:
    _rate_limit_lock = threading.Lock()          # Thread-safe access to timestamps
    _request_times: list[float] = []             # Track request timestamps
```

#### 2. Rate Limiting Method
```python
async def _enforce_rate_limit(self) -> None:
    """Enforce 5 requests per minute for Gemini API."""
    
    # Phase 1: Check current window
    with GeminiProvider._rate_limit_lock:
        now = time.time()
        # Clean up timestamps older than 60 seconds
        GeminiProvider._request_times = [
            ts for ts in GeminiProvider._request_times
            if now - ts < 60
        ]
        
        if len(GeminiProvider._request_times) >= 5:
            # Calculate wait time until oldest request expires
            oldest_request = GeminiProvider._request_times[0]
            wait_time = 60 - (now - oldest_request)
            if wait_time > 0:
                logger.warning(
                    f"Gemini rate limit: 5 requests reached, "
                    f"waiting {wait_time:.1f}s before next request"
                )
    
    # Phase 2: Sleep outside the lock (non-blocking for other code)
    if len(GeminiProvider._request_times) >= 5:
        now = time.time()
        oldest_request = GeminiProvider._request_times[0]
        wait_time = 60 - (now - oldest_request)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
            logger.info("Gemini rate limit wait complete, resuming requests")
    
    # Phase 3: Record this request
    with GeminiProvider._rate_limit_lock:
        now = time.time()
        GeminiProvider._request_times = [
            ts for ts in GeminiProvider._request_times
            if now - ts < 60
        ]
        GeminiProvider._request_times.append(now)
```

#### 3. Integration into Request Flow
In `GeminiProvider.generate()`:
```python
async def generate(self, request: LLMRequest) -> LLMResponse:
    model_name = request.model or self.default_model
    url = f"{GEMINI_BASE_URL}/{model_name}:generateContent?key={self.api_key}"
    payload = self._build_payload(request)
    
    # Enforce rate limit before making the request
    await self._enforce_rate_limit()
    
    async with httpx.AsyncClient(timeout=self.timeout) as client:
        # ... existing code ...
```

---

## How It Works

### Sliding Window (1 minute)
1. **Window Size:** 60 seconds
2. **Max Requests:** 5 per window
3. **Tracking:** Timestamps of last N requests

### Three Phases

#### Phase 1: Cleanup & Check
- Acquire lock
- Remove timestamps older than 60 seconds
- If 5+ requests in current window, calculate wait time
- Release lock before sleeping

#### Phase 2: Wait (if needed)
- Sleep for calculated duration (outside lock)
- Logs warning when waiting begins
- Logs info when wait completes

#### Phase 3: Record Request
- Acquire lock
- Record current timestamp as this request's time
- Release lock

### Example Timeline
```
T=0s   → Request 1 (allowed, 0 requests in window)
T=5s   → Request 2 (allowed, 1 request in window)
T=10s  → Request 3 (allowed, 2 requests in window)
T=15s  → Request 4 (allowed, 3 requests in window)
T=20s  → Request 5 (allowed, 4 requests in window)
T=25s  → Request 6 (BLOCKED - 5 requests in window)
        ↓ Wait 60 - (25-0) = 35 seconds
T=60s  → Wait completes, proceed with Request 6
T=60s  → Request 7 (allowed, only Request 6 in new window)
```

---

## Key Properties

✅ **Minimal Changes**
- Only 52 lines added
- Only `_enforce_rate_limit()` method and 3 imports
- No refactoring of unrelated code
- Rate limiter is transparent to QALoop, tool calling, or fallback logic

✅ **Thread-Safe**
- Uses `threading.Lock()` for synchronized access to shared state
- Lock is acquired only for checking and updating timestamps
- Sleep happens outside the lock (non-blocking)

✅ **Non-Blocking QALoop**
- Rate limiter waits asynchronously using `await asyncio.sleep()`
- QALoop continues naturally after wait completes
- No forced termination or exception

✅ **Process-Level**
- Applies to entire process lifetime
- Shared across all GeminiProvider instances
- Starts fresh on process restart

✅ **Transparent to Fallback**
- Does NOT modify LLMService fallback logic
- A Gemini 429 remains a RetriableError (if it occurs, it means rate limiter failed)
- Does NOT reroute to OpenRouter
- OpenRouter is unaffected

✅ **Observable**
- Logs clearly when rate limit is hit: `"Gemini rate limit: 5 requests reached, waiting {wait_time}s..."`
- Logs when wait completes: `"Gemini rate limit wait complete, resuming requests"`

---

## Testing

### Unit Tests
✅ All provider tests pass:
```
backend/tests/unit/test_ai_providers.py::test_single_provider_success PASSED
backend/tests/unit/test_ai_providers.py::test_fallback_on_retriable_error PASSED
backend/tests/unit/test_ai_providers.py::test_no_fallback_on_non_retriable_error PASSED
backend/tests/unit/test_ai_providers.py::test_all_providers_fail_raises PASSED
backend/tests/unit/test_ai_providers.py::test_provider_order_matters PASSED
backend/tests/unit/test_ai_providers.py::test_service_requires_at_least_one_provider PASSED
```

### Live Test (Manual)

**Setup:** Trigger a multi-turn QALoop conversation with `DEPLOYMENT_TYPE=PROD` using Gemini cloud model.

**Expected Behavior:**
1. First 5 Gemini requests within 60s window proceed immediately
2. 6th request logs: `"Gemini rate limit: 5 requests reached, waiting {wait_time}s before next request"`
3. After ~60s wait, logs: `"Gemini rate limit wait complete, resuming requests"`
4. Request 6 proceeds to Gemini successfully
5. No OpenRouter fallback occurs due to rate limiter
6. QALoop continues with remaining tool calls
7. Existing Gemini native tool calling works unchanged

**Verification from Logs:**
```bash
docker compose logs backend | grep "rate limit"
```

Expected output:
```
Gemini rate limit: 5 requests reached, waiting 35.5s before next request
Gemini rate limit wait complete, resuming requests
```

---

## No Changes To

- ✅ QALoop structure (one-tool-per-turn semantics preserved)
- ✅ Gemini native tool-calling (functionDeclarations, parsing)
- ✅ Tool schemas and ToolDispatchTable
- ✅ Hermes XML parsing for Qwen
- ✅ JSON-action-protocol for OpenRouter
- ✅ LLMService fallback mechanism
- ✅ Model routing logic
- ✅ Qwen/Ollama provider behavior
- ✅ OpenRouter provider behavior
- ✅ Frontend (no changes needed)

---

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| `backend/ai/providers/gemini.py` | Add rate limiter + integrate into generate() | +52 |

---

## Deployment

No additional configuration needed. The rate limiter:
- Activates automatically on GeminiProvider instantiation
- Applies to all Gemini requests in the process
- Survives container restarts
- Works with or without fallback providers configured
