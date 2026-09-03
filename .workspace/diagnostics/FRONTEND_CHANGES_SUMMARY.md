# Frontend Changes Summary — RIM Comparison UI Integration

## Overview

The frontend UI for RIM Comparison has been restructured to align with the new agentic loop architecture. The key changes introduce transparency into:
- How files are retrieved iteratively (via tool transcript)
- What RIM actually contributed (separate metadata vs on-demand queries)
- Token accounting (actual vs estimated distinction)

---

## Major UI Changes

### 1. "View LLM Context" — Now Three Distinct Sections

**BEFORE:** Single flat `<pre>` block showing concatenated context.

**AFTER:** Three clearly separated sub-sections with colored left borders:

```
View LLM Context
│
├─ RIM_METADATA (blue border)
│  └─ Shows: Relationship facts (RIM side) OR "None" (baseline)
│
├─ SOURCE_CONTEXT (green border)
│  └─ Shows: Actual tool observation text received by LLM
│
└─ TOOL_CALL_TRANSCRIPT (purple border)
   └─ Shows: Ordered list of LLM tool calls per turn
      Example:
      [0] search_repository → found 3 results
      [1] read_file → Login.tsx lines 1-100
      [2] get_symbol → handleLogin signature
```

**Why this matters:**
- Demonstrates one-file-at-a-time retrieval (not 15 pre-fetched files)
- Proves RIM metadata is truly separate from source code
- Shows iterative decision-making (LLM decides what to read next)

---

### 2. "What Did RIM Add?" — Split into Upfront vs On-Demand

**BEFORE:** Mixed list of seed entities, relationships, discovered files.

**AFTER:** Two clearly labeled contributions:

```
What Did RIM Add?
│
├─ From Upfront RIM_METADATA Block
│  ├─ Seed Entities: [Login, authService, authenticate]
│  └─ 3 relationships discovered
│
└─ From query_rim Tool Calls (2 calls)
   ├─ handleLogin (CALLS) → 2 results
   └─ authenticate (IMPORTS) → 1 result
```

**Why this matters:**
- Shows what was pre-computed vs what was on-demand
- Explains LLM's iterative exploration strategy
- Demonstrates RIM as metadata layer, not file-selection mechanism

---

### 3. Comparison Summary Table — New Metrics Rows

**BEFORE:** Simple input/output/total token counts.

**AFTER:** Expanded table with 4 new rows:

```
Metric                           | WITHOUT RIM | WITH RIM | Difference
─────────────────────────────────┼─────────────┼──────────┼────────────
Tool Calls / Iterations          | 3           | 3        | —
Files Retrieved                  | 2           | 2        | —
Symbols Retrieved                | 5           | 6        | +1
RIM Entities Accessed            | 0           | 2        | +2
Input Tokens (Actual)            | 1240        | 1340     | +100
Est. System Tokens (estimated)   | 280         | 280      | —
Est. RIM Metadata Tokens (est.)  | 0           | 142      | +142
Est. Source Tokens (estimated)   | 450         | 450      | —
Output Tokens (Actual)           | 320         | 350      | +30
Total Latency (ms)               | 2845        | 2920     | +75
```

**Visual changes:**
- Estimated rows have gray background + gray text + "(estimated)" label
- Actual rows use normal dark text
- New rows show retrieval iteration count and RIM contribution

**Why this matters:**
- Tool call count (not hidden) proves iterative loop, not single pre-fetch
- Estimated breakdown is explicitly labeled, never confused with actual
- Users see the cost-benefit of RIM: metadata tokens vs. reduced file reads

---

### 4. Retrieval Metrics Box — Added Tool Calls

**BEFORE:**
```
Files: 2
Symbols: 5
Retrieval: 1234ms
RIM rels: 3
```

**AFTER:**
```
Tool Calls: 3        ← NEW
Files: 2
Symbols: 5
Retrieval: 1234ms
RIM Entities: 2      ← Changed label
```

**Why this matters:**
- Shows user how many "thinking steps" the LLM took
- Iteration count is the primary proof of agentic architecture

---

### 5. LLM Efficiency Box — Token Breakdown Separated

**BEFORE:**
```
Input Tokens: 1240
Output Tokens: 320
Total: 1560
LLM Time: 1200ms
Total Time: 2845ms
```

**AFTER:**
```
Input Tokens (Actual): 1240
Output Tokens (Actual): 320
(Est. breakdown: system 280 + source 450 + rim 142)
───────────────────────
LLM Time: 1200ms
Retrieval Time: 600ms
Total Time: 2845ms
```

**Visual changes:**
- Actual tokens clearly labeled
- Estimated breakdown on separate gray line
- Retrieval time now separately tracked
- No attempt to reconcile estimates with actual (difference reported as-is)

**Why this matters:**
- Actual numbers are from the LLM provider (authoritative)
- Estimated breakdown shows where tokens went (system prompt? RIM metadata? source code? tool protocol?)
- Reconciliation difference shows inherent approximation error

---

## Response Structure Changes

### New Fields in `ComparisonSide`

| Field | Type | Purpose |
|-------|------|---------|
| `rim_metadata_block` | `string \| null` | RIM facts (null for baseline) |
| `source_context_block` | `string` | Actual tool observations received by LLM |
| `tool_call_transcript` | `Array<{turn, tool_name, arguments, observation_summary}>` | Ordered turns showing iteration |
| `stop_reason` | `string` | Why the loop stopped (completed, max_turns, etc.) |

### Changed Fields in `RetrievalMetrics`

| Field | Change | Type |
|-------|--------|------|
| `tool_call_count` | NEW | `number` |
| `rim_entities_accessed_count` | NEW | `number` |
| `rim_relationship_types_used` | NEW | `string[]` |

### Changed Fields in `LLMEfficiencyMetrics`

| Field | Was | Now | Type |
|-------|-----|-----|------|
| `input_tokens` | `number \| null` | Removed | — |
| `output_tokens` | `number \| null` | Removed | — |
| `total_tokens` | `number \| null` | Removed | — |
| `actual_prompt_tokens` | — | NEW | `number` |
| `actual_completion_tokens` | — | NEW | `number` |
| `actual_total_tokens` | — | NEW | `number` |
| `estimated_system_tokens` | — | NEW | `number` |
| `estimated_rim_tokens` | — | NEW | `number` |
| `estimated_source_tokens` | — | NEW | `number` |
| `estimated_other_tokens` | — | NEW | `number` |
| `token_estimation_method` | — | NEW | `string` |
| `token_estimation_is_approximate` | — | NEW | `boolean` |
| `token_reconciliation_diff` | — | NEW | `number` |
| `token_counting_latency_ms` | — | NEW | `float` |
| `retrieval_latency_ms` | — | NEW | `float` |

### Changed Trace Structure

**BEFORE:** `RIMExecutionTrace` with mixed fields.

**AFTER:** `RIMTrace` with separate provenance:
```typescript
{
  rim_metadata_seed_entities: [],        // Upfront metadata seed resolution
  rim_metadata_relationships: [],        // Upfront one-hop relationships
  query_rim_call_log: []                 // On-demand query_rim calls
}
```

---

## Expected Visual Differences (Before vs After)

### Query: "How does the login component call the auth service?"

#### BEFORE (Old Architecture)

```
WITHOUT RIM: 
- Context Block (huge, 15 pre-fetched file snippets):
  [file1.tsx] Login.tsx line 1-80: ...code...
  [file2.tsx] auth.ts line 1-60: ...code...
  [file15.tsx] other.ts line 1-40: ...code...

WITH RIM:
- Context Block (same 15 files, maybe different order):
  [file1.tsx] ...code...
  ...
- RIM Relationships: [complex, mixed with candidates]

Token accounting:
  Input: 5200 | Output: 280 | Total: 5480
```

#### AFTER (New Architecture)

```
WITHOUT RIM:
- RIM_METADATA: None (baseline retrieval mode)
- SOURCE_CONTEXT:
  [search_repository] found 3 matches: Login.tsx, auth.ts, authController.ts
  [read_file] Login.tsx lines 1-80: import { authenticate } from './auth'...
  [get_symbol] authenticate function: export async function authenticate(...)
- TOOL_CALL_TRANSCRIPT:
  [0] search_repository → found 3 results
  [1] read_file → Login.tsx lines 1-80
  [2] get_symbol → authenticate signature

WITH RIM:
- RIM_METADATA:
  Login.handleLogin CALLS authenticate (src/pages/Login.tsx:42)
  authenticate IMPORTS jwt (src/services/auth.ts:1)
  authenticate ROUTE_HANDLER POST /api/login
- SOURCE_CONTEXT: (same as baseline, tool observations)
- TOOL_CALL_TRANSCRIPT:
  [0] search_repository → found 3 results
  [1] query_rim → authenticate relationships
  [2] read_file → auth.ts lines 1-60

Token accounting:
  Input (Actual): 1240
  (Est: system 280 + source 450 + rim 142)
  Output (Actual): 320
  Reconciliation: diff = -12 (estimate is 12 tokens high)
```

---

## Key Insights for Users

### "One File at a Time" Proof

Look at TOOL_CALL_TRANSCRIPT:
- **Before**: Invisible; context was pre-fetched in a tight loop
- **After**: Visible; shows LLM made 3 calls, read 2-3 files, decided what to explore next

### "RIM is Metadata, Not File Selection"

Look at RIM_METADATA vs SOURCE_CONTEXT:
- **Before**: RIM metadata was mixed with file candidates; hard to separate
- **After**: RIM_METADATA is pure facts (relationships), SOURCE_CONTEXT is pure code

### "Actual vs Estimated Tokens"

Look at LLM Efficiency box:
- **Before**: Single total_tokens number; no breakdown
- **After**: Actual (authoritative) + estimated breakdown (system/rim/source/other) with reconciliation diff

### "No Azure Flooding"

Look at tool_call_transcript length:
- **Before**: Implied 15 file reads in invisible loop
- **After**: Explicit 2-6 calls shown, LLM controlled pacing

---

## Testing Focus Areas

When testing, pay attention to:

1. **Tool Transcript Length**: Should be 2-6 calls, not 15 ✅
2. **RIM Metadata Content**: Should contain relationship facts, not code ✅
3. **Estimated Styling**: Gray background, gray text, labeled "(estimated)" ✅
4. **Reconciliation**: Diff is reported, not zero-forced ✅
5. **Graceful Degradation**: Sparse repos show "no relationships found", not errors ✅

---

## Implementation Notes for Developers

### Updated Files

- `frontend/services/rimComparisonApi.ts` — TypeScript interfaces
- `frontend/app/repository/[repoName]/rim-comparison/page.tsx` — Component restructure

### Removed Fields

The following old fields are **no longer used** and should be removed from any code still referencing them:

- `retrieved_files`
- `retrieved_symbols`
- `context_block`
- `RIMExecutionTrace` (replaced by `RIMTrace`)

### New Field Validation

Ensure API calls always include:
- `rim_metadata_block` (null or string)
- `source_context_block` (string)
- `tool_call_transcript` (array)
- All `actual_*` and `estimated_*` token fields

---

## Migration Checklist

- [ ] TypeScript interfaces updated
- [ ] API endpoint returns new response structure
- [ ] "View LLM Context" shows 3 sub-sections
- [ ] "What Did RIM Add?" shows upfront + on-demand
- [ ] Token rows show actual vs estimated distinction
- [ ] Tool calls row appears in summary table
- [ ] No undefined errors in browser console
- [ ] Lint passes: `npm run lint`
- [ ] Manual test run completed (see FRONTEND_TESTING_GUIDE.md)

---

## Questions?

Refer to:
- **FRONTEND_TESTING_GUIDE.md** — How to test each change
- **IMPLEMENTATION_GUIDE.md** (Part E) — TypeScript code examples
- **RIM_COMPARISON_ARCHITECTURE_SUMMARY.md** — Architecture overview

