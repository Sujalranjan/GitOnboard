# Model Routing Fix - Summary

**Date:** 2026-09-12  
**Issue:** When user selects "Qwen 3 4B (Fast)", backend sends model ID to Gemini, causing 404 error  
**Status:** ✅ FIXED

---

## Root Cause

The router was passing all selected model IDs to the LLMService, which in PROD mode only has `[GeminiProvider, OpenRouterProvider]` registered. When a local Qwen model was selected, it got sent to Gemini (which doesn't know about local models), causing:

```
404 models/qwen3:4b-instruct is not found for API version v1beta
```

---

## The Fix

**File Modified:** `backend/routers/llm.py` (lines 299-321)

**Logic:**
1. Check if selected model starts with "qwen"
2. If YES → Create OllamaProvider-only service for that model
3. If NO → Use default cloud provider chain (Gemini → OpenRouter)
4. Normalize cloud sentinel strings ("cloud-gemini", "cloud-openrouter") to None

**Code Flow:**

```python
# OLD: Always uses cloud service regardless of selected model
llm_service = get_llm_service()  # Returns [Gemini, OpenRouter]

# NEW: Route based on model type
if model.startswith("qwen"):
    # Local model - use Ollama
    llm_service = LLMService(providers=[OllamaProvider(model)])
else:
    # Cloud model - use default chain
    llm_service = get_llm_service()  # Returns [Gemini, OpenRouter]
```

---

## Routing Table

| Model Selected | Provider Used | Behavior |
|---|---|---|
| Qwen 3 4B (qwen3:4b-instruct) | OllamaProvider | Routes to local Ollama with qwen3:4b-instruct |
| Qwen Coder 7B (qwen2.5-coder:7b) | OllamaProvider (primary) + OllamaProvider (fallback) | Routes to Ollama, fallback to coder variant |
| Gemini (Cloud) (cloud-gemini) | GeminiProvider | Normalized to None, uses GEMINI_MODEL env var |
| OpenRouter (Cloud) (cloud-openrouter) | GeminiProvider → OpenRouterProvider | Normalized to None, uses OPENROUTER_MODEL env var |

---

## Verification

### ✅ Routing Logic Tests
- [x] Qwen 3 4B → OllamaProvider
- [x] Qwen Coder 7B → OllamaProvider + fallback
- [x] cloud-gemini → Gemini chain
- [x] cloud-openrouter → OpenRouter chain

### ✅ Model Normalization
- [x] "cloud-gemini" → None (allows env var)
- [x] "cloud-openrouter" → None (allows env var)
- [x] Local models → passed through unchanged

### ✅ Backward Compatibility
- [x] Gemini native tool-calling still works
- [x] OpenRouter JSON protocol still works
- [x] Qwen/Hermes parsing still works
- [x] One-tool-per-turn semantics preserved

---

## Files Modified

| File | Lines | Changes |
|------|-------|---------|
| backend/routers/llm.py | 297-321 | Model-based service routing logic |
| backend/routers/llm.py | 289-292 | Cloud sentinel normalization |
| backend/routers/llm.py | 372 | Use normalized model_for_llm |

**Total Change:** ~40 lines in 1 file (focused, minimal fix)

---

## What Was NOT Changed

- ✅ No changes to QALoop
- ✅ No changes to providers (Gemini, OpenRouter, Ollama)
- ✅ No changes to tool-calling logic
- ✅ No changes to Hermes/JSON parsing
- ✅ No new providers created
- ✅ No architecture changes

---

## Testing

All tests verify:
1. ✅ Qwen models route to Ollama correctly
2. ✅ Cloud models use the Gemini/OpenRouter chain
3. ✅ Model string normalization works
4. ✅ No regressions in existing functionality
5. ✅ Provider instances created correctly
6. ✅ LLMService initialized with correct providers

---

## Before and After

### Before (Broken)
```
User selects: Qwen 3 4B (qwen3:4b-instruct)
            ↓
Router passes to QALoop: model="qwen3:4b-instruct"
            ↓
QALoop calls: llm_service.generate(model="qwen3:4b-instruct")
            ↓
LLMService tries providers: [GeminiProvider, OpenRouterProvider]
            ↓
GeminiProvider gets request with model="qwen3:4b-instruct"
            ↓
❌ Gemini API: 404 Model not found
```

### After (Fixed)
```
User selects: Qwen 3 4B (qwen3:4b-instruct)
            ↓
Router detects: model.startswith("qwen") = True
            ↓
Router creates: LLMService(providers=[OllamaProvider])
            ↓
LLMService tries providers: [OllamaProvider(model="qwen3:4b-instruct")]
            ↓
OllamaProvider handles request correctly
            ↓
✅ Response from local Ollama model
```

---

## Deployment

No configuration changes needed. The fix works with existing settings:
- DEPLOYMENT_TYPE=PROD
- GEMINI_API_KEY=...
- OPENROUTER_API_KEY=...
- OLLAMA_MODEL=qwen3:4b-instruct
- OLLAMA_FALLBACK_MODEL=qwen2.5-coder:7b

---

## Edge Cases Handled

1. **Fallback model same as primary:** Only creates one Ollama provider
2. **No fallback model configured:** Creates single provider
3. **User switches between Qwen and Cloud:** Correct provider chain created each time
4. **OLLAMA_BASE_URL not configured:** Uses sensible default (http://127.0.0.1:11434)

---

## Status: ✅ READY FOR DEPLOYMENT

The fix:
- ✅ Solves the model routing bug
- ✅ Maintains all existing functionality
- ✅ Does not require code changes elsewhere
- ✅ Has comprehensive verification
- ✅ Follows minimal-change principle
