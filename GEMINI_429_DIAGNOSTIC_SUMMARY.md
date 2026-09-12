# Gemini HTTP 429 Diagnostic Summary

**Date:** 2026-09-12  
**Issue:** Gemini returns HTTP 429 Too Many Requests on first request (T+0ms)  
**Status:** Diagnostic logging added, but response body not yet captured

---

## Observed Behavior

From logs, Gemini 429 occurs at:
- T=0ms on first QALoop turn
- Before local 5-req/min rate limiter can trigger (0 previous requests in this run)
- On FIRST request of a new question

Example timeline:
```
14:37:58,772 - [router] Using cloud provider chain for model cloud-gemini
14:37:59,425 - HTTP Request: POST gemini-3.6-flash:generateContent "HTTP/1.1 429 Too Many Requests"
14:38:00,135 - HTTP Request: POST openrouter.ai/chat "HTTP/1.1 200 OK"  ← Fallback succeeds
```

This pattern repeats across multiple sessions, showing consistent, immediate 429 responses.

---

## Diagnostic Logging Implementation

Added to `backend/ai/providers/gemini.py`:

1. **`_log_gemini_error(status_code, response_text, response_headers)`** method:
   - Parses JSON error response
   - Extracts: `message`, `status`, `code`
   - For 429 specifically, captures:
     - `quotaFailures[].metric` - which quota is exhausted
     - `quotaFailures[].description` - description of the quota
     - `retryDelay` - how long to wait before retrying
     - `Retry-After` header
     - `ratelimit-reset-after` header

2. **Integration points**:
   - Called for all non-2xx responses (401, 400, 404, 429, 5xx)
   - Logs with `logger.error("[GEMINI_ERROR]")` marker
   - For 429: logs with `[GEMINI_ERROR_429]` marker

3. **Debug logging**:
   - Added `[GEMINI_GENERATE]` at start of `generate()` method
   - Added `[GEMINI_429]` before calling `_log_gemini_error` for 429 cases

---

## Expected Diagnostic Output Format

When Gemini returns 429, expected logs should include:

```
[GEMINI_GENERATE] Starting request to model: gemini-3.6-flash
[GEMINI_429] Response text length: XXX bytes
[GEMINI_ERROR] status_code=429
[GEMINI_ERROR] message='...'
[GEMINI_ERROR] status='RESOURCE_EXHAUSTED'  (or other error status)
[GEMINI_ERROR] code=429  (or numeric error code)
[GEMINI_ERROR] detail_type='type.googleapis.com/google.rpc.QuotaFailure'
[GEMINI_ERROR_429] quota_metric='.../'  (e.g., 'serviceruntime.googleapis.com/quota/requests_per_min')
[GEMINI_ERROR_429] quota_description='...'
[GEMINI_ERROR_429] retry_delay_seconds=X.X
[GEMINI_ERROR] retry_after_header='...' (if present)
```

---

## Next Steps

1. ✅ Diagnostic logging code has been added and deployed
2. ⏳ Need to capture actual 429 response body from Gemini API
3. ⏳ Parse quota failure details to identify:
   - Which quota is being hit (requests/min, tokens/min, requests/day, etc.)
   - What the limit is
   - What the current usage is
   - What the retry delay should be

---

## Technical Notes

- Gemini API returns error details in JSON format
- Error structure: `{ "error": { "message": "...", "status": "...", "details": [...] } }`
- `details` array contains typed objects with quota/retry information
- Quota failures use `type.googleapis.com/google.rpc.QuotaFailure` type
- Retry info uses `type.googleapis.com/google.rpc.RetryInfo` type

---

## Known Context

- GEMINI_API_KEY is configured and the API endpoint is reachable
- HTTP 429 responses are being received from `generativelanguage.googleapis.com`
- Local rate limiter (5 req/min) cannot explain first-request 429
- Fallback to OpenRouter succeeds, confirming other LLMs are working
- Issue persists across multiple QALoop sessions

---

## File Modified

- `backend/ai/providers/gemini.py` - Added `_log_gemini_error()` method and diagnostic logging calls

---

**Awaiting first live capture of Gemini 429 response body with quota details**
