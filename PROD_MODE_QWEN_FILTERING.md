# PROD Mode: Hide Local Qwen Models from Frontend

**Date:** 2026-09-12  
**Issue:** Local Qwen models were visible in frontend when DEPLOYMENT_TYPE=PROD  
**Status:** ✅ FIXED

---

## Problem

When `DEPLOYMENT_TYPE=PROD`, the frontend still showed local Qwen models:
- Qwen 3 4B (Fast)
- Qwen 2.5 Coder 7B (Quality)

These models only work when Ollama is running locally, which isn't available in PROD mode. Users would select them and get confusing errors.

---

## Solution

Updated `frontend/components/LLMConversationFlow.tsx` to:

1. **Filter models based on DEPLOYMENT_TYPE**
   - In PROD mode: Show only cloud models (Gemini, OpenRouter)
   - In LOCAL mode: Show all models (local + cloud)

2. **Set appropriate defaults**
   - In PROD mode: Default to Gemini (cloud-gemini)
   - In LOCAL mode: Default to Qwen 3 4B (qwen3:4b-instruct)

---

## Code Changes

### Before
```typescript
const AVAILABLE_MODELS: ModelOption[] = [
  // All 4 models always available
];

const [selectedModel, setSelectedModel] = useState<string>('qwen3:4b-instruct');
```

### After
```typescript
const ALL_MODELS: ModelOption[] = [
  // All 4 models defined
];

// Filter models based on deployment type
const getAvailableModels = (): ModelOption[] => {
  const isProd = process.env.NEXT_PUBLIC_DEPLOYMENT_TYPE?.toUpperCase() === 'PROD';
  if (isProd) {
    // Hide local Qwen models in PROD mode
    return ALL_MODELS.filter(m => m.category === 'cloud');
  }
  return ALL_MODELS;
};

const AVAILABLE_MODELS = getAvailableModels();

const isProd = process.env.NEXT_PUBLIC_DEPLOYMENT_TYPE?.toUpperCase() === 'PROD';
const [selectedModel, setSelectedModel] = useState<string>(isProd ? 'cloud-gemini' : 'qwen3:4b-instruct');
```

---

## How It Works

The frontend already uses `NEXT_PUBLIC_DEPLOYMENT_TYPE` environment variable (which is set from backend's `DEPLOYMENT_TYPE`). This is a Next.js public environment variable accessible in the browser at build time.

**Model Visibility:**
- **LOCAL mode** (default):
  - ✅ Qwen 3 4B (Fast) - local
  - ✅ Qwen 2.5 Coder 7B - local
  - ✅ Gemini (Cloud) - cloud
  - ✅ OpenRouter (Cloud) - cloud

- **PROD mode** (DEPLOYMENT_TYPE=PROD):
  - ✗ Qwen 3 4B (Fast) - HIDDEN
  - ✗ Qwen 2.5 Coder 7B - HIDDEN
  - ✅ Gemini (Cloud) - visible
  - ✅ OpenRouter (Cloud) - visible

**Default Model Selection:**
- LOCAL: Qwen 3 4B (qwen3:4b-instruct)
- PROD: Gemini (cloud-gemini)

---

## Files Modified

| File | Changes |
|------|---------|
| `frontend/components/LLMConversationFlow.tsx` | Filter models, update defaults |

**Total changes:** 12 lines

---

## Verification

✅ **Frontend builds successfully**
- `npm run build` completes without errors
- TypeScript validation passes
- All routes compile

✅ **Model filtering logic**
- LOCAL mode: All 4 models available
- PROD mode: 2 cloud models only

✅ **Default model selection**
- LOCAL mode defaults to Qwen
- PROD mode defaults to Gemini

---

## Deployment

No additional configuration needed. The filtering is automatic based on the `NEXT_PUBLIC_DEPLOYMENT_TYPE` environment variable, which Next.js reads at build time.

When the frontend is built with `DEPLOYMENT_TYPE=PROD`:
- Qwen models are hidden from the UI
- Users see only cloud model options
- Default selection is Gemini

---

## Related Work

This complements the earlier backend fix that routes model selections correctly:
- Qwen models → OllamaProvider (LOCAL)
- Cloud models → Gemini/OpenRouter chain (PROD)

Together, these changes ensure PROD mode only shows and uses cloud models.
