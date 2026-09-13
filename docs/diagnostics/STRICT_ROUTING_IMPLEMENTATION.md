# Strict Provider Routing Implementation

**Date:** 2026-09-12  
**Status:** ✅ COMPLETE

---

## Changes Made

### File Modified: `backend/routers/llm.py` (lines 298-320)

Changed the LLM service construction to use **strict, non-fallback routing** based on explicit model selection:

#### Before:
```python
if model.startswith("qwen"):
    # Ollama-only for Qwen
    ...
else:
    # ALL cloud models used: get_llm_service() → [Gemini, OpenRouter] chain
    llm_service = get_llm_service()
```

#### After:
```python
if model.startswith("qwen"):
    # Ollama-only for Qwen
    ...
elif model == "cloud-gemini":
    # Gemini-only - NO FALLBACK
    gemini_provider = GeminiProvider(api_key=gemini_api_key)
    llm_service = LLMService(providers=[gemini_provider])
elif model == "cloud-openrouter":
    # OpenRouter-only - NO FALLBACK
    openrouter_provider = OpenRouterProvider(api_key=openrouter_api_key)
    llm_service = LLMService(providers=[openrouter_provider])
```

---

## Routing Behavior

### When user selects `cloud-gemini`:
```
✅ Request 1 → Gemini (via GeminiProvider)
✅ Request 2 → Gemini
✅ Request 3 → Gemini
✅ Request 4 → Gemini
✅ Request 5 → Gemini
⏸️  WAIT 60 seconds (rate limiter)
✅ Request 6 → Gemini
...
```

**NO OpenRouter fallback.** If Gemini returns 429, 400, 401, etc., the error is returned directly to the user.

### When user selects `cloud-openrouter`:
```
✅ Request 1 → OpenRouter
✅ Request 2 → OpenRouter
✅ Request 3 → OpenRouter
...
```

**NO Gemini fallback.** OpenRouter-only service.

### When user selects Qwen local model:
```
✅ Request 1 → Ollama (running locally)
✅ Request 2 → Ollama
...
```

**Unchanged behavior.** Ollama-only service with optional fallback to alternate Qwen model.

---

## Rate Limiter (Unchanged)

The existing 5-request-per-minute Gemini rate limiter remains active:
- **Location**: `backend/ai/providers/gemini.py`, `_enforce_rate_limit()` method
- **Behavior**: 
  - Tracks requests in a 60-second sliding window
  - Allows up to 5 requests per window
  - Waits before the 6th request if needed
  - Process-level, thread-safe with `threading.Lock()`
- **Logging**:
  - `[GEMINI_RATE_LIMIT] Request N/5`
  - `[GEMINI_RATE_LIMIT] Limit reached; waiting X seconds`
  - `[GEMINI_RATE_LIMIT] Cooldown complete; continuing`

---

## Error Handling

When `cloud-gemini` is selected:

| Error | Behavior |
|-------|----------|
| HTTP 429 (Quota exhausted) | Return error directly to user |
| HTTP 401/403 (Auth error) | Return error directly to user |
| HTTP 400 (Bad request) | Return error directly to user |
| HTTP 404 (Model not found) | Return error directly to user |
| HTTP 5xx (Server error) | Return error directly to user |
| Network error (timeout, SSL) | Return error directly to user |

**No automatic fallback to OpenRouter.**

The diagnostic logging for each error is preserved in `logs/errors.log`:
- `[GEMINI] Status code: X, response length: Y`
- `[GEMINI_429] Received 429, response text length: Z bytes`
- `[GEMINI_ERROR] message='...'`
- `[GEMINI_ERROR] status='RESOURCE_EXHAUSTED'` (or other error status)
- `[GEMINI_ERROR_429] quota_metric='...'`

---

## Verification Points

✅ **Routing**: 
- `cloud-gemini` creates GeminiProvider-only service
- `cloud-openrouter` creates OpenRouterProvider-only service
- Qwen models use OllamaProvider

✅ **No Fallback**:
- Gemini errors do NOT trigger OpenRouter
- OpenRouter errors do NOT trigger Gemini (if selected)

✅ **Rate Limiting**:
- 5 requests per 60-second window
- Request 6 waits for cooldown
- Logging shows rate limit events

✅ **Existing Behavior Preserved**:
- QALoop one-tool-per-turn semantics unchanged
- Gemini native function calling unchanged
- Ollama/Qwen behavior unchanged

---

## What's Fixed

**Before:**
- User selected `cloud-gemini`
- Gemini hit free tier quota (429)
- System automatically fell back to OpenRouter
- OpenRouter hit SSL certificate error
- User saw OpenRouter error instead of Gemini quota info

**After:**
- User selects `cloud-gemini`
- Gemini hits free tier quota (429)
- Error is returned directly: "Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20"
- User sees Gemini's actual error and can respond appropriately

---

## Next Steps

**To enable Gemini with the free tier limit:**

1. Enable billing on Gemini API key
   - Access: https://console.cloud.google.com/billing
   - Or get a new API key with fresh quota

2. Restart the backend
   - `docker compose restart backend`

3. Select `cloud-gemini` in the frontend
   - 5 requests allowed per 60 seconds
   - Rate limiter will pause between windows
   - Gemini errors return directly (no fallback)

**To use OpenRouter exclusively:**

- Select `cloud-openrouter`
- Service uses only OpenRouterProvider
- No Gemini fallback

**To use Qwen locally:**

- Select any Qwen model (`qwen3:4b-instruct`, etc.)
- Service uses only OllamaProvider
- Requires Ollama running on `http://127.0.0.1:11434`

---

## Implementation Details

**File**: `backend/routers/llm.py`  
**Lines Modified**: 298-320  
**Lines Added**: ~15  
**Lines Removed**: ~5  
**Net Change**: Minimal, focused only on routing logic  

**No changes to:**
- QALoop architecture
- Gemini native tool calling
- Gemini rate limiter
- Ollama/Qwen behavior
- OpenRouter behavior
- Error handling in providers
- Diagnostic logging
