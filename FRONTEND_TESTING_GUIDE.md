# Frontend Integration Testing Guide

This guide walks you through testing the new RIM Comparison UI integration and verifying the architectural changes work correctly end-to-end.

---

## Prerequisites

1. **Backend deployed** — Parts A, C, D code is in production:
   - `uv sync` has been run to install `tokenizers>=0.23.0`
   - Backend service is restarted
   - POST `/api/repos/{repo_name}/rim-comparison/compare` endpoint is accessible

2. **Analysis re-run complete** (Part B) — The test repository has been re-analyzed:
   - Database contains relationships with types CALLS, USES, RENDERS (not just DECLARES/IMPORTS)
   - `get_latest_analysis()` picks up the new analysis ID

3. **Frontend updated** — This PR's changes are merged:
   - TypeScript interfaces updated in `frontend/services/rimComparisonApi.ts`
   - UI component restructured in `frontend/app/repository/[repoName]/rim-comparison/page.tsx`
   - Comparison table has new metrics rows
   - "View LLM Context" and "What Did RIM Add?" sections restructured

---

## Phase 1: Endpoint Verification (Backend Only)

Before testing the UI, verify the backend endpoint responds with the correct structure.

### Step 1.1: Test Endpoint Directly

```bash
curl -X POST \
  http://localhost:8000/api/repos/Deep-Guard-Frontend/rim-comparison/compare \
  -H "Content-Type: application/json" \
  -d '{"question": "How does the login form interact with the authentication service?"}'
```

### Step 1.2: Verify Response Structure

Expected response should have this shape:

```json
{
  "without_rim": {
    "answer": "...",
    "retrieval_metrics": {
      "tool_call_count": <number>,
      "files_retrieved": <number>,
      "symbols_retrieved": <number>,
      "rim_entities_accessed_count": 0,
      "rim_relationship_types_used": [],
      "retrieval_latency_ms": <float>
    },
    "llm_efficiency_metrics": {
      "provider": "ollama",
      "model": "qwen",
      "actual_prompt_tokens": <number>,
      "actual_completion_tokens": <number>,
      "actual_total_tokens": <number>,
      "estimated_system_tokens": <number>,
      "estimated_rim_tokens": 0,
      "estimated_source_tokens": <number>,
      "estimated_other_tokens": <number>,
      "token_estimation_method": "heuristic",
      "token_estimation_is_approximate": true,
      "token_reconciliation_diff": <number>,
      "llm_latency_ms": <float>,
      "retrieval_latency_ms": <float>,
      "token_counting_latency_ms": <float>,
      "total_latency_ms": <float>
    },
    "answer_metrics": {
      "correctness": null,
      "grounding": null,
      "notes": ""
    },
    "rim_metadata_block": null,
    "source_context_block": "...",
    "tool_call_transcript": [
      {
        "turn": 0,
        "tool_name": "search_repository",
        "arguments": {...},
        "observation_summary": "..."
      },
      ...
    ],
    "stop_reason": "completed"
  },
  "with_rim": {
    "answer": "...",
    "retrieval_metrics": {
      "tool_call_count": <number>,
      "files_retrieved": <number>,
      "symbols_retrieved": <number>,
      "rim_entities_accessed_count": <number>,
      "rim_relationship_types_used": ["CALLS", "IMPORTS", ...],
      "retrieval_latency_ms": <float>
    },
    "llm_efficiency_metrics": {
      "provider": "ollama",
      "model": "qwen",
      "actual_prompt_tokens": <number>,
      "actual_completion_tokens": <number>,
      "actual_total_tokens": <number>,
      "estimated_system_tokens": <number>,
      "estimated_rim_tokens": <number>,
      "estimated_source_tokens": <number>,
      "estimated_other_tokens": <number>,
      "token_estimation_method": "heuristic",
      "token_estimation_is_approximate": true,
      "token_reconciliation_diff": <number>,
      "llm_latency_ms": <float>,
      "retrieval_latency_ms": <float>,
      "token_counting_latency_ms": <float>,
      "total_latency_ms": <float>
    },
    "answer_metrics": {
      "correctness": null,
      "grounding": null,
      "notes": ""
    },
    "rim_metadata_block": "...",
    "source_context_block": "...",
    "tool_call_transcript": [
      {
        "turn": 0,
        "tool_name": "search_repository",
        ...
      },
      ...
    ],
    "stop_reason": "completed"
  },
  "repository": "Deep-Guard-Frontend",
  "branch": "main",
  "commit": "...",
  "analysis_id": 3,
  "context_diff": {
    "files_only_without_rim": [...],
    "shared_files": [...],
    "files_only_with_rim": [...]
  },
  "trace": {
    "rim_metadata_seed_entities": [...],
    "rim_metadata_relationships": [...],
    "query_rim_call_log": [...]
  }
}
```

### Step 1.3: Verify Key Fields

- ✅ `rim_metadata_block` is NOT null on RIM side, IS null on baseline
- ✅ `tool_call_transcript` is an array with at least 1-2 entries
- ✅ `actual_prompt_tokens` and `actual_completion_tokens` are real numbers (not null)
- ✅ `estimated_*` fields are present and labeled `estimated=true`
- ✅ `token_reconciliation_diff` shows the difference (not forced to zero)
- ✅ `trace.rim_metadata_seed_entities` has entries if the question resolved to entities
- ✅ `trace.query_rim_call_log` has entries if the RIM loop called query_rim

---

## Phase 2: Frontend UI Rendering

Now test the UI to ensure all new sections render correctly.

### Step 2.1: Navigate to RIM Comparison Page

1. Open the application in your browser: `http://localhost:3000`
2. Go to a repository view (e.g., Deep-Guard-Frontend)
3. Click on the "RIM Comparison" tab or link
4. You should see the RIM Comparison research interface

### Step 2.2: Run a Comparison Query

1. In the **"Research Question"** text area, enter:
   ```
   How does the login component interact with the authentication service?
   ```
   (Choose a question that requires exploring multiple files and relationships)

2. Click **"Compare"** button
3. Wait for the comparison to complete (typically 10-30 seconds)

### Step 2.3: Verify Panel Headers Render

You should now see two side-by-side cards:
- **WITHOUT RIM** (left) — "Standard Retrieval"
- **WITH RIM** (right) — "RIM-Enhanced Retrieval"

---

## Phase 3: Verify "View LLM Context" Restructuring

Click the **"View LLM Context"** collapsible in **BOTH** panels.

### Baseline (WITHOUT RIM) Side

You should see three labeled sub-sections with colored left borders:

1. **RIM_METADATA** (blue border)
   - Text should read: `"None (baseline retrieval mode — no repository knowledge graph facts provided)"`
   - No code or relationship facts shown

2. **SOURCE_CONTEXT** (green border)
   - Shows the actual tool observation text that the LLM received
   - Contains code snippets from `read_file` tool calls
   - Format: `[tool_name] <observation_text>`
   - Token count shown: e.g. `(~412 tokens)`

3. **TOOL_CALL_TRANSCRIPT** (purple border)
   - Shows ordered list of tool calls made: `[0] search_repository → "found 3 results"`, `[1] read_file → "Login.tsx lines 1-100"`, etc.
   - Should show 2-6 calls, NOT 15 (proof of one-file-at-a-time retrieval)
   - Each line shows: turn number (yellow), tool name, observation summary

### RIM (WITH RIM) Side

1. **RIM_METADATA** (blue border)
   - Should show relationship facts like:
     ```
     Login.handleLogin CALLS authService.login (src/pages/Login.tsx:42)
     authService.login IMPORTS jwt (src/services/auth.ts:1)
     ...
     ```
   - Real facts from the repository's relationship graph
   - Token count shown: e.g. `(~148 tokens)`

2. **SOURCE_CONTEXT** (green border)
   - Same as baseline — actual tool results text

3. **TOOL_CALL_TRANSCRIPT** (purple border)
   - Same format, may include a `query_rim` tool call if the LLM used it

---

## Phase 4: Verify "What Did RIM Add?" Section

Click the **"What Did RIM Add?"** collapsible on the **RIM side** ONLY.

(This section is hidden on the WITHOUT RIM side since there's nothing to add.)

### Sub-section 1: "From Upfront RIM_METADATA Block"

Shows the entities and relationships that came from the initial RIM metadata block:

- **Seed Entities** list: e.g.
  ```
  • Login (ClassSymbol)
  • authService (VariableSymbol)
  • authenticate (FunctionSymbol)
  ```
- **Relationships discovered**: X relationships

Example text:
```
From Upfront RIM_METADATA Block

Seed Entities:
• Login (ClassSymbol)
• authService (ObjectSymbol)

3 relationships discovered
```

### Sub-section 2: "From query_rim Tool Calls (N calls)"

Shows any on-demand lookups the LLM made during the loop:

- If the LLM called `query_rim` tool, entries show:
  ```
  • handleLogin (CALLS) → 2 results
  • authenticate (IMPORTS) → 1 result
  ```
- If N is 0, text shows: `"(No on-demand query_rim calls made)"`

---

## Phase 5: Verify Comparison Summary Table

Scroll to the **"Comparison Summary"** table. It should have these new rows:

| Metric | WITHOUT RIM | WITH RIM | Difference |
|--------|------------|---------|------------|
| **Tool Calls / Iterations** | 3 | 3 | — |
| **Files Retrieved** | 2 | 2 | — |
| **Symbols Retrieved** | 5 | 6 | +1 |
| **RIM Entities Accessed** | 0 | 2 | +2 |
| **Input Tokens (Actual)** | 1240 | 1340 | +100 |
| **Est. System Tokens** _(estimated)_ | 280 | 280 | — |
| **Est. RIM Metadata Tokens** _(estimated)_ | 0 | 142 | +142 |
| **Est. Source Tokens** _(estimated)_ | 450 | 450 | — |
| **Output Tokens (Actual)** | 320 | 350 | +30 |
| **Total Latency (ms)** | 2845.0 | 2920.0 | +75.0 |

### Key Checks

✅ **"Tool Calls / Iterations"** row appears (NEW)
✅ **"RIM Entities Accessed"** row appears (NEW)
✅ **Estimated rows** are visually distinct (grayed out, lighter background, labeled "(estimated)")
✅ **Actual rows** (Input/Output Tokens) use real numbers from provider
✅ Estimated rows never force reconciliation to zero — show the difference

---

## Phase 6: Verify Retrieval Metrics Box

Look at the **"Retrieval Metrics"** box in both panels (left side of each panel).

Should show:
```
Tool Calls: 3
Files: 2
Symbols: 5
Retrieval: 1234ms
RIM Entities: 2  (RIM side only)
```

✅ **"Tool Calls"** field appears (NEW)

---

## Phase 7: Verify LLM Efficiency Box

Look at the **"LLM Efficiency"** box in both panels.

Should show:
```
Input Tokens (Actual): 1240
Output Tokens (Actual): 320
(Est. breakdown: system 280 + source 450 + rim 142)
────────────────────
LLM Time: 1200ms
Retrieval Time: 600ms
Total Time: 2845ms
```

### Key Checks

✅ **"Input Tokens (Actual)"** and **"Output Tokens (Actual)"** labels are clear
✅ **Estimated breakdown** shown on a separate line in gray
✅ RIM side shows `+ rim XXX` in the breakdown
✅ Baseline side shows only `system + source`, no RIM number

---

## Phase 8: Verify "Research Summary" Narrative

Scroll to the bottom. The **"Research Summary"** card should have bullet points like:

✅ Example output:
```
→ RIM metadata block contained 3 relationship(s), with 0 on-demand query_rim call(s).

→ Both sides made 3 (baseline) vs 3 (RIM) tool calls to explore the repository.

→ RIM reduced actual token usage by 50 (3.8%).

→ WITH RIM was 105ms slower.
```

### Key Checks

- Mentions RIM metadata relationships found (could be 0)
- Mentions on-demand query_rim calls (could be 0)
- Shows tool call counts for both sides
- Mentions actual token usage difference (from `actual_total_tokens`)
- Shows latency difference

---

## Phase 9: Edge Cases & Graceful Degradation

Test these scenarios to verify graceful handling:

### Scenario A: Repository with Sparse Data

Run a query against the baseline pre-reanalysis analysis (analysis_id=2) if it still exists.

Expected behavior:
- ✅ RIM_METADATA shows: `"RIM_METADATA: No structural facts could be resolved for this question in this repository's index."`
- ✅ No error, query completes normally
- ✅ "What Did RIM Add?" shows: `"(No seed entities resolved)"`

### Scenario B: Query Requiring No Tool Calls

Ask a very short question: `"What is this repository?"`

Expected behavior:
- ✅ Both sides might complete with 1 tool call or 0
- ✅ tool_call_transcript might be empty `[]`
- ✅ UI shows: `"(no tool calls made)"`

### Scenario C: Query with No Relationships

Ask about a simple file: `"List all functions in login.ts"`

Expected behavior:
- ✅ RIM_METADATA might show no relationships even if login.ts is resolved
- ✅ query_rim_call_log stays empty or minimal
- ✅ No error, UI gracefully shows empty lists

---

## Phase 10: Visual Comparison & Regression Check

### Answer Quality

1. Do both sides produce reasonable answers?
2. Is the RIM side's answer different/better/similar to the baseline?
3. (Subjective — use Evaluation section to score)

### Context Splitting

1. Is RIM_METADATA truly separate from SOURCE_CONTEXT?
2. Does SOURCE_CONTEXT show only tool-observation text (no relationship facts)?
3. Does TOOL_CALL_TRANSCRIPT show one call per turn?

### No Azure Flooding

1. tool_call_transcript should show 2-6 calls, NOT 15
2. Each turn should show only one tool call
3. Files are read one at a time based on LLM decisions

### Token Reconciliation

For BOTH sides, check:
```
actual_prompt_tokens =? estimated_system + estimated_rim + estimated_source + estimated_other ± reconciliation_diff
```

Example:
- actual = 1340
- estimated_total = 280 + 0 + 450 + 568 = 1298
- reconciliation_diff = 1340 - 1298 = 42

This is expected. The difference reflects:
- LLM provider's exact tokenization (authoritative)
- Local heuristic estimation (ceil(len/4), approximate)

✅ Reconciliation_diff is reported, not forced to zero

---

## Common Issues & Troubleshooting

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| Endpoint returns 404 or 500 | Backend changes not deployed or router not registered | Restart backend, check logs for `rim_comparison_v2` router registration |
| RIM_METADATA is null on RIM side | Analysis missing relationships or build_rim_metadata_block failed silently | Check backend logs; re-run re-analysis (Part B) |
| tool_call_transcript is empty | No tool calls made or parsing failed | Check stop_reason (might be "max_turns" or "max_observation_bytes") |
| Estimated tokens are 0 | Token counter failed silently, fell back to heuristic but returned 0 | Check backend token counter logs; verify tokenizers package is installed |
| UI shows error when collapsibles expand | Missing field in API response | Check API response matches full schema from Phase 1 |
| Comparison takes >60 seconds | Both loops running sequentially as expected; may be slow for complex repos | Normal — sequential execution per architecture. Monitor retrieval_latency_ms and llm_latency_ms |

---

## Final Checklist

- [ ] Endpoint returns correct response structure (Phase 1)
- [ ] "View LLM Context" shows three sub-sections with correct content (Phase 3)
- [ ] Baseline shows `rim_metadata_block = null`, RIM side shows actual facts (Phase 3)
- [ ] "What Did RIM Add?" shows upfront + on-demand contributions separately (Phase 4)
- [ ] Comparison Summary table has all new rows including Tool Calls and estimated tokens (Phase 5)
- [ ] Estimated rows are visually distinct with gray styling and "(estimated)" label (Phase 5)
- [ ] tool_call_transcript shows 2-6 calls, NOT 15 (proof of no pre-fetching) (Phase 3, Phase 8)
- [ ] RIM_METADATA contains relationship facts, not code (Phase 3)
- [ ] SOURCE_CONTEXT contains actual tool observation text (Phase 3)
- [ ] Both sides show actual_prompt_tokens and actual_completion_tokens (not null) (Phases 6-7)
- [ ] Token reconciliation_diff is reported without forcing to zero (Phase 7, Phase 9)
- [ ] Sparse/null data degrades gracefully with explicit "no data" messages (Phase 9)
- [ ] No TypeScript errors in browser console
- [ ] Run `npm run lint` in frontend directory — no new warnings

---

## Demo Talking Points

When demonstrating to stakeholders:

1. **"One file at a time"**: Point to TOOL_CALL_TRANSCRIPT, show turns incrementally (not 15 at once)
2. **"Metadata separate from source"**: Show RIM_METADATA vs SOURCE_CONTEXT in three distinct sections
3. **"Fair comparison"**: Show tool_call_count is similar on both sides; only difference is metadata + query_rim tool
4. **"Token accounting"**: Show actual vs estimated; explain reconciliation_diff as inherent approximation
5. **"What RIM actually added"**: Point to "What Did RIM Add?" showing upfront relationships and on-demand calls
6. **"No Azure flooding"**: Contrast with old architecture (15 pre-fetched files); new has 2-6 iterative calls

---

## Next Steps After Verification

Once all checks pass:

1. **Merge frontend PR** to main
2. **Update deployment documentation** to include "Deploy backend Parts A/C/D, run uv sync, restart service, run re-analysis"
3. **Document findings** in research notes (did RIM help? Did token usage change? Did iteration improve answer quality?)
4. **(Optional) Run full test suite** against multiple repositories to collect data
5. **(Optional) Add integration tests** to CI/CD to prevent regression of new response structure

---

**Good luck! 🚀**
