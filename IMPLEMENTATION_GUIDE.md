# RIM Comparison Architecture Implementation Guide

## Overview

This document provides step-by-step guidance for completing the RIM Comparison research feature based on the planned architecture correction. The implementation has been split into five parts:

- **Part A**: Agentic Q&A loop infrastructure ✅ DONE
- **Part C**: Token accounting with model-aware counters ✅ DONE
- **Part D**: RIMComparisonService orchestration rewrite ✅ DONE
- **Part B**: Re-analysis validation gate (prerequisite)
- **Part E**: Frontend integration

---

## Part B — Re-analysis Validation Gate (Prerequisite)

### Problem

The test repository (Deep-Guard-Frontend, analysis_id=2) currently has **zero CALLS relationships** in its fact store. This is because:

1. The analysis was run *before* the CallGraphAnalyzer and UsesAnalyzer implementations were completed
2. These analyzers are now part of `get_default_registry()` in `backend/intelligence/engine/analyzers/__init__.py`
3. The RIM metadata block will degrade gracefully on stale data, but a re-analysis is needed for a compelling demo

### Solution: Trigger Re-analysis

#### Step 1: Identify the Repository and Latest Analysis

```bash
# Connect to the database and find the test repo
psql postgresql://user:pass@localhost/dbname
SELECT id, repository_name, created_at, total_symbols, total_relationships 
  FROM analyses 
  WHERE repository_name = 'Deep-Guard-Frontend' 
  ORDER BY created_at DESC 
  LIMIT 5;
```

Expected output shows analysis #2 with `total_relationships = 375` (DECLARES + IMPORTS only).

#### Step 2: Trigger Re-analysis via API

```bash
# Option 1: Direct HTTP POST to the reanalyze endpoint
curl -X POST \
  http://localhost:8000/api/repos/Deep-Guard-Frontend/reanalyze \
  -H "Authorization: Bearer <your_auth_token>" \
  -H "Content-Type: application/json"

# Response will include job_id: "abc123-xyz789"
```

Or use the frontend's existing "Re-analyze Repository" button if available.

#### Step 3: Monitor Analysis Progress

```bash
# Option 1: Poll the job status endpoint
curl http://localhost:8000/api/jobs/abc123-xyz789/status \
  -H "Authorization: Bearer <your_auth_token>"

# Watch for status transitions:
# "queued" → "running" → "succeeded" or "failed"
```

Or use the existing SSE stream for real-time updates:

```bash
# Option 2: Stream job output (if supported)
curl -N http://localhost:8000/api/repos/Deep-Guard-Frontend/tasks/stream \
  -H "Authorization: Bearer <your_auth_token>"
```

#### Step 4: Verify Relationship Types in New Analysis

Once the analysis completes, verify that it captured CALLS, USES, and RENDERS:

```bash
# Find the new analysis ID (should be > 2)
psql postgresql://user:pass@localhost/dbname
SELECT id, repository_name, created_at 
  FROM analyses 
  WHERE repository_name = 'Deep-Guard-Frontend' 
  ORDER BY created_at DESC 
  LIMIT 1;

-- Then check relationship breakdown for the new analysis (e.g., analysis #3)
SELECT rel_type, COUNT(*) as count 
  FROM relationships 
  WHERE analysis_id = 3 
  GROUP BY rel_type 
  ORDER BY count DESC;
```

Expected output (with properly working analyzers):
```
rel_type       | count
---------------+--------
IMPORTS        | 250
DECLARES       | 200
CALLS          | 150  ← (NEW - from CallGraphAnalyzer)
USES           | 80   ← (NEW - from UsesAnalyzer)
RENDERS        | 45   ← (NEW - from CallGraphAnalyzer JSX visitor)
```

#### Step 5: Verify RIM Comparison Uses Latest Analysis

The `get_latest_analysis()` function in `backend/routers/repo/services/analysis.py` automatically resolves to the most recent analysis for a repository. Once the new analysis completes, subsequent RIM comparison runs will automatically use it.

To verify:
```bash
# Run a RIM comparison after the new analysis completes
curl -X POST \
  http://localhost:8000/api/repos/Deep-Guard-Frontend/rim-comparison/compare \
  -H "Authorization: Bearer <your_auth_token>" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the main components?"}'

# The RIM metadata block should now contain CALLS relationships
# If it still shows "No relationships found", the analysis may not have completed
```

### Troubleshooting Re-analysis

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| Job stays in "queued" | Analysis job not picked up by worker | Check backend logs for `enqueue_job()` errors; verify celery/job queue is running |
| Analysis errors in logs | Analyzer exceptions (e.g., tree-sitter parse failures) | Check DIAGNOSTIC_GUIDE.md; run with diagnostics enabled: `analysis_id=3` passed to `AnalysisEngine.run()` |
| New analysis has zero CALLS | CallGraphAnalyzer not registered | Verify `get_default_registry()` includes CallGraphAnalyzer; check `backend/intelligence/engine/analyzers/__init__.py` |
| get_latest_analysis still returns old ID | Caching or time-of-check issue | Restart backend service to clear any in-memory caches |

---

## Part E — Frontend Integration

### Overview

The frontend needs updates to:
1. Import new Pydantic response models from `rim_comparison_v2.py`
2. Update TypeScript interfaces to match new response structure
3. Restructure "View LLM Context" and "What Did RIM Add?" sections
4. Add token metrics rows to the comparison table

### Files to Update

#### 1. `frontend/services/rimComparisonApi.ts`

Update TypeScript interfaces to match new Pydantic models:

```typescript
export interface RetrievalMetrics {
  tool_call_count: number;
  files_retrieved: number;
  symbols_retrieved: number;
  rim_entities_accessed_count: number;
  rim_relationship_types_used: string[];
  retrieval_latency_ms: number;
}

export interface LLMEfficiencyMetrics {
  provider: string;
  model: string;
  actual_prompt_tokens: number;
  actual_completion_tokens: number;
  actual_total_tokens: number;
  estimated_system_tokens: number;
  estimated_rim_tokens: number;
  estimated_source_tokens: number;
  estimated_other_tokens: number;
  token_estimation_method: string;
  token_estimation_is_approximate: boolean;
  token_reconciliation_diff: number;
  llm_latency_ms: number;
  retrieval_latency_ms: number;
  token_counting_latency_ms: number;
  total_latency_ms: number;
}

export interface ComparisonSide {
  answer: string;
  retrieval_metrics: RetrievalMetrics;
  llm_efficiency_metrics: LLMEfficiencyMetrics;
  answer_metrics: AnswerMetrics;
  rim_metadata_block: string | null;
  source_context_block: string;
  tool_call_transcript: Array<{
    turn: number;
    tool_name: string;
    arguments: Record<string, unknown>;
    observation_summary: string;
  }>;
  stop_reason: string;
}

export interface RIMTrace {
  rim_metadata_seed_entities: Array<Record<string, unknown>>;
  rim_metadata_relationships: Array<Record<string, unknown>>;
  query_rim_call_log: Array<Record<string, unknown>>;
}
```

#### 2. `frontend/app/repository/[repoName]/rim-comparison/page.tsx`

Restructure key sections:

**"View LLM Context" Collapsible** (currently lines 446–455):
```tsx
// Replace flat context dump with three sub-sections:
<Collapsible open={contextOpen} onOpenChange={setContextOpen} title="View LLM Context">
  <div className="space-y-4">
    {/* Sub-section 1: RIM_METADATA */}
    <div className="border-l-4 border-blue-400 pl-4">
      <h4 className="font-semibold">RIM_METADATA ({withRimMetadataTokens} tokens)</h4>
      {withRimMetadataBlock ? (
        <pre className="text-xs overflow-auto max-h-48">{withRimMetadataBlock}</pre>
      ) : (
        <p className="text-gray-500 italic">None (baseline retrieval mode)</p>
      )}
    </div>
    
    {/* Sub-section 2: SOURCE_CONTEXT */}
    <div className="border-l-4 border-green-400 pl-4">
      <h4 className="font-semibold">SOURCE_CONTEXT ({sourceTokens} tokens)</h4>
      <pre className="text-xs overflow-auto max-h-48">{sourceContextBlock}</pre>
    </div>
    
    {/* Sub-section 3: TOOL_CALL_TRANSCRIPT */}
    <div className="border-l-4 border-purple-400 pl-4">
      <h4 className="font-semibold">TOOL_CALL_TRANSCRIPT ({toolCallTranscript.length} calls)</h4>
      <div className="text-xs space-y-1 max-h-48 overflow-auto">
        {toolCallTranscript.map((call, i) => (
          <div key={i} className="font-mono">
            [{call.turn}] {call.tool_name} → {call.observation_summary.substring(0, 100)}
          </div>
        ))}
      </div>
    </div>
  </div>
</Collapsible>
```

**"What Did RIM Add?" Collapsible** (currently lines 457–511):
```tsx
// Replace with separate provenance: upfront metadata vs on-demand query_rim
<Collapsible title="What Did RIM Add?" hidden={!isRimSide}>
  <div className="space-y-4">
    {/* Upfront RIM metadata contribution */}
    <div>
      <h4 className="font-semibold text-sm mb-2">
        From Upfront RIM_METADATA Block
      </h4>
      <ul className="text-sm space-y-1 max-h-24 overflow-auto">
        {rimMetadataSeedEntities.map((e, i) => (
          <li key={i} className="text-gray-700">
            • {e.name} ({e.entity_type})
          </li>
        ))}
      </ul>
      <p className="text-xs text-gray-500 mt-1">
        {rimMetadataRelationships.length} relationships
      </p>
    </div>
    
    {/* On-demand query_rim tool calls */}
    <div>
      <h4 className="font-semibold text-sm mb-2">
        From query_rim Tool Calls ({queryRimCalls.length} calls)
      </h4>
      <ul className="text-sm space-y-1 max-h-24 overflow-auto">
        {queryRimCalls.map((call, i) => (
          <li key={i} className="text-gray-700">
            • {call.entity_name} ({call.relationship_type}) → {call.related_count} results
          </li>
        ))}
      </ul>
    </div>
  </div>
</Collapsible>
```

**Comparison Summary Table** (lines 255–307):
Add rows for tool calls and token breakdown:
```tsx
<tr>
  <td className="font-semibold">Tool Calls / Iterations</td>
  <td className="text-right">{withoutRim.retrieval_metrics.tool_call_count}</td>
  <td className="text-right">{withRim.retrieval_metrics.tool_call_count}</td>
</tr>

<tr>
  <td className="font-semibold">RIM Entities Accessed</td>
  <td className="text-right">0</td>
  <td className="text-right">{withRim.retrieval_metrics.rim_entities_accessed_count}</td>
</tr>

<tr>
  <td className="font-semibold">Input Tokens (Actual)</td>
  <td className="text-right">{withoutRim.llm_efficiency_metrics.actual_prompt_tokens}</td>
  <td className="text-right">{withRim.llm_efficiency_metrics.actual_prompt_tokens}</td>
</tr>

<tr>
  <td className="font-semibold">Est. System Tokens</td>
  <td className="text-right text-gray-500">{withoutRim.llm_efficiency_metrics.estimated_system_tokens}</td>
  <td className="text-right text-gray-500">{withRim.llm_efficiency_metrics.estimated_system_tokens}</td>
</tr>

<tr>
  <td className="font-semibold">Est. RIM Metadata Tokens</td>
  <td className="text-right text-gray-500">0</td>
  <td className="text-right text-gray-500">{withRim.llm_efficiency_metrics.estimated_rim_tokens}</td>
</tr>

<tr>
  <td className="font-semibold">Est. Source Tokens</td>
  <td className="text-right text-gray-500">{withoutRim.llm_efficiency_metrics.estimated_source_tokens}</td>
  <td className="text-right text-gray-500">{withRim.llm_efficiency_metrics.estimated_source_tokens}</td>
</tr>

<tr>
  <td className="font-semibold">Output Tokens (Actual)</td>
  <td className="text-right">{withoutRim.llm_efficiency_metrics.actual_completion_tokens}</td>
  <td className="text-right">{withRim.llm_efficiency_metrics.actual_completion_tokens}</td>
</tr>
```

### Implementation Checklist

- [ ] Update `rimComparisonApi.ts` with new TypeScript interfaces
- [ ] Update endpoint URL in `rimComparisonApi.ts` to point to `/rim-comparison-v2/compare` (or update the v2 router to replace the old one)
- [ ] Restructure "View LLM Context" collapsible with three sub-sections
- [ ] Restructure "What Did RIM Add?" with separate provenance lists
- [ ] Add token breakdown rows to comparison table
- [ ] Add tool calls count to retrieval metrics box
- [ ] Update `ResearchSummary` narrative to reference new token field names
- [ ] Test with baseline and RIM sides to verify:
  - RIM side shows actual RIM metadata block (not "None")
  - Tool call transcript shows 2-6 calls, not 15
  - Source context block is not a flat dump of 15 pre-fetched files
  - Token breakdown adds up (actual = estimated_system + estimated_rim + estimated_source + estimated_other ± reconciliation_diff)

### Testing the Frontend Changes

Once backend is deployed with Parts A/C/D:

```bash
# Test query that needs multiple files
curl -X POST \
  http://localhost:8000/api/repos/Deep-Guard-Frontend/rim-comparison/compare \
  -H "Content-Type: application/json" \
  -d '{"question": "How does the login component call the auth service?"}'

# Verify response structure:
# {
#   "without_rim": {
#     "tool_call_transcript": [{"turn": 0, "tool_name": "search_repository", ...}, ...],
#     "source_context_block": "...",
#     "rim_metadata_block": null,
#     ...
#   },
#   "with_rim": {
#     "tool_call_transcript": [...],
#     "source_context_block": "...",
#     "rim_metadata_block": "Login.handleLogin CALLS authService.login (...)",
#     ...
#   },
#   "trace": {
#     "rim_metadata_seed_entities": [...],
#     "query_rim_call_log": [...]
#   }
# }
```

---

## Architecture Summary

### Before (Single-shot pre-fetch)
```
User Question
    ↓
HybridRetriever (expand_with_fact_store=False)
    ↓
Candidates → fetch 15 file snippets → concatenate → LLM → Answer
```

### After (Agentic sequential loops)
```
WITHOUT RIM:                          WITH RIM:
User Question                         User Question
    ↓                                     ↓
Identical Agentic Loop                Identical Agentic Loop
  search_repository                     + RIM Metadata Block
  read_file (one)                       + query_rim tool
  get_symbol                            + (same retrieval tools)
  ... (LLM decides)
  
LLM makes iterative decisions          LLM makes iterative decisions
about WHAT to read next                using structured metadata facts
```

Key differences:
- **One file at a time**: LLM decides what to read next, gets one result, decides again
- **Metadata separate**: RIM provides facts, not files
- **Token accounting**: Actual (from provider) vs estimated (local) distinction
- **Transparent**: Tool call transcript shows exactly what happened

---

## Verification Checklist

- [ ] Part A (Agentic loop): Committed ✅
- [ ] Part C (Token counting): Committed ✅
- [ ] Part D (Service rewrite): Committed ✅
- [ ] Part B (Re-analysis): New analysis has CALLS/USES/RENDERS
- [ ] Part E (Frontend): Updated TypeScript + UI components
- [ ] Integration test: Compare query runs, verifies tool transcript + metadata split
- [ ] Demo readiness: Clean answer, tool transcript shows iteration, metrics make sense

---

## References

- **CLAUDE.md**: Global engineering rules
- **DIAGNOSTIC_GUIDE.md**: How to debug analyzer issues
- **backend/services/rim_qa_loop.py**: Agentic loop implementation
- **backend/services/rim_qa_protocol.py**: JSON action protocol
- **backend/services/rim_tool_dispatch.py**: Tool routing
- **backend/services/rim_metadata.py**: RIM metadata assembly
- **backend/ai/tokencount/**: Model-aware token counting
- **backend/routers/repo/rim_comparison_v2.py**: New endpoint and response models
