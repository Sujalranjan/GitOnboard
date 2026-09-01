# RIM Comparison Architecture Correction — Complete Implementation Summary

## Executive Summary

The RIM Comparison research feature has been fundamentally re-architected to properly test the hypothesis: *does giving an LLM a repository knowledge graph help it navigate better than standard retrieval?*

**Status**: ✅ Parts A, C, D COMPLETE & COMMITTED | 📋 Parts B, E DOCUMENTED WITH IMPLEMENTATION GUIDE

---

## What Was Fixed

### The Problem
The original implementation conflated RIM (a knowledge/metadata layer) with source retrieval (a data-access layer):
- **FactStoreExpander** injected relationship-derived file candidates into retrieval
- **_build_context()** pre-fetched 15 files in a tight loop before any LLM call (Azure flooding)
- **Single LLM call** with one giant flat context block
- **No RIM metadata** actually sent to the LLM — only "fetch more files"
- **No fair comparison** — the two sides had different retrieval capabilities

### The Solution

#### Architecture Change
**Before**: Question → Retriever (expand_with_fact_store toggle) → Pre-fetch 15 files → LLM call
**After**: Question → Agentic Loop (identical on both sides) → LLM decides retrieval iteratively → Answer

#### Key Principles Implemented
1. **RIM as metadata, not file selection**
   - RIM metadata block (facts about relationships) sent as system prompt text
   - `query_rim` tool available on RIM side only for on-demand queries
   - FactStoreExpander REMOVED — relationships never auto-inject files

2. **Fair comparison**
   - Both sides use identical agentic loop infrastructure
   - Both sides have identical retrieval tools (read_file, search_repository, get_symbol, etc.)
   - Identical guardrails (12 max turns, 15 max tool calls, 180s timeout, 8KB observation cap)
   - Only difference: RIM side has upfront metadata block + query_rim tool

3. **One file at a time**
   - LLM makes tool calls sequentially
   - One tool call per turn, strictly enforced
   - Retrieval paced by LLM decision-making, not pre-fetched
   - Eliminates Azure blob flooding

4. **Token accounting done right**
   - Provider-reported aggregate tokens (real, authoritative)
   - Local estimated breakdown (system / RIM / source / other buckets)
   - Separate distinction: actual vs estimated throughout UI
   - Token reconciliation diff reported (never forced to reconcile)
   - Per-call latency tracking (llm vs retrieval vs token_counting)

---

## Implementation Status

### ✅ COMPLETED & COMMITTED

#### Part A: Agentic Q&A Loop Infrastructure
**Commit**: 447a878  
**Files**:
- `backend/services/rim_qa_loop.py` (550 lines)
  - `RIMQALoop` class: core agentic loop with guardrails integration
  - `QALoopTurn` & `QALoopResult` dataclasses
  - One-tool-call-per-turn strict enforcement
  - Tracks files_read, symbols_read, rim_entities_accessed
  
- `backend/services/rim_qa_protocol.py` (170 lines)
  - `QAProtocolAdapter`: system prompt builder with decomposed buckets
  - JSON action protocol: `{"action": "tool_call"|"final_answer", ...}`
  - Returns `SystemPromptParts` for token accounting

- `backend/services/rim_tool_dispatch.py` (400 lines)
  - `ToolDispatchTable`: routes tool calls to implementations
  - Exposes tools on baseline (no RIM): read_file, find_files, search_repository, get_symbol, get_callers, get_callees, search_code
  - RIM-exclusive tool: query_rim with TargetEntityResolver
  - Never raises: all exceptions caught → ToolObservation(success=False)

- `backend/services/rim_metadata.py` (350 lines)
  - `build_rim_metadata_block()`: builds upfront facts
  - Uses HybridRetriever for seed identification (NO expansion)
  - Traverses fixed set of one-hop relationships per seed
  - Graceful degradation: explicit "no relationships found" message if sparse
  - Returns `RimMetadataBlock` with text + seed_entities + relationships

#### Part C: Model-Aware Token Counting
**Commit**: b51aa4c  
**Files**:
- `backend/ai/tokencount/` (7 files, ~700 lines)
  - `base.py`: `TokenCountResult` dataclass + `TokenCounter` ABC
  - `heuristic.py`: `HeuristicTokenCounter` (ceil(len/4), always available fallback)
  - `qwen.py`: `QwenTokenCounter` (exact via vendored tokenizer.json, fallback to heuristic)
  - `gemini.py`: `GeminiTokenCounter` (exact via Gemini :countTokens REST API with caching)
  - `openrouter.py`: `OpenRouterTokenCounter` (best-effort, always marked estimated=True)
  - `registry.py`: `count_tokens()` dispatch by provider, never raises
  - `__init__.py`: public API

- `backend/tests/ai/test_token_counter.py` (280 lines)
  - Tests for all counters, fallback paths, dispatch, error handling
  - Verifies actual vs estimated distinction
  - Caching tests for Gemini
  - Integration tests for typical flows

- `pyproject.toml` updated: added `tokenizers>=0.23.0` as explicit dependency

#### Part D: RIM Comparison Service Rewrite
**Commit**: b8cf388  
**Files**:
- `backend/services/rim_comparison_service_v2.py` (600 lines)
  - New `RIMComparisonService.run_comparison()` orchestrating two agentic loops
  - Sequential execution (both sides, baseline first then RIM)
  - Shared primitives: HybridRetriever, RepositoryToolLayer, AgentLoopConfig
  - Token accounting: actual (provider) + estimated (local) breakdown
  - New dataclasses:
    - `RetrievalMetrics`: tool_call_count, rim_entities_accessed_count
    - `LLMEfficiencyMetrics`: provider, model, actual_*, estimated_*, token_reconciliation_diff, latency breakdown
    - `ComparisonSide`: rim_metadata_block, source_context_block, tool_call_transcript, stop_reason
    - `RIMTrace`: rim_metadata_seed_entities, rim_metadata_relationships, query_rim_call_log (separate provenance)

- `backend/routers/repo/rim_comparison_v2.py` (280 lines)
  - Updated Pydantic response models matching new dataclasses
  - RIMComparisonResponse with new structure
  - Endpoint: POST `/repos/{repo_name}/rim-comparison/compare`
  - Secret redaction for source_context_block, rim_metadata_block, tool_call_transcript

### 📋 DOCUMENTED WITH IMPLEMENTATION GUIDE

#### Part B: Re-analysis Validation Gate
**Document**: IMPLEMENTATION_GUIDE.md (Re-analysis section)

*Why this matters*: Test repo (analysis_id=2) predates CallGraphAnalyzer/UsesAnalyzer implementations. Has zero CALLS. RIM metadata block will degrade gracefully but demo needs current data.

**Procedure**:
1. Trigger `POST /repos/Deep-Guard-Frontend/reanalyze`
2. Monitor job until completion
3. Verify via SQL: `SELECT rel_type, COUNT(*) FROM relationships WHERE analysis_id=3 GROUP BY rel_type`
4. Expect CALLS, USES, RENDERS to be non-zero
5. `get_latest_analysis()` auto-picks new analysis

**Troubleshooting table** included for common failure modes

#### Part E: Frontend Integration
**Document**: IMPLEMENTATION_GUIDE.md (Frontend Integration section)

*Scope*: TypeScript interface updates + UI restructuring

**TypeScript Updates**:
- `rimComparisonApi.ts`: New interfaces for RetrievalMetrics, LLMEfficiencyMetrics, ComparisonSide, RIMTrace

**UI Component Changes**:
1. **"View LLM Context" collapsible** (3 sub-sections):
   - RIM_METADATA: rim_metadata_block text (or "None" for baseline)
   - SOURCE_CONTEXT: source_context_block text
   - TOOL_CALL_TRANSCRIPT: ordered list of turns with tool name + observation summary

2. **"What Did RIM Add?" collapsible**:
   - Upfront RIM_METADATA contribution (seed entities + relationships count)
   - On-demand query_rim tool calls (call count + results)
   - Separate provenance lists (addresses reconciliation issue)

3. **Comparison Summary table**:
   - Add "Tool Calls / Iterations" row
   - Add "RIM Entities Accessed" row
   - Add "RIM Relationship Types Used" row
   - Split token rows: actual input/output + estimated system/rim/source/other
   - Each estimated number labeled with "estimated" visual indicator

**Testing**: Response structure example provided with all new fields

---

## Key Metrics Tracked

### Per Comparison Side

**Retrieval Metrics**:
- `tool_call_count`: number of LLM tool-call turns
- `files_retrieved`: distinct files actually read
- `symbols_retrieved`: distinct symbols looked up
- `rim_entities_accessed_count`: how many query_rim calls resolved an entity
- `rim_relationship_types_used`: [CALLS, IMPORTS, ...] list
- `retrieval_latency_ms`: tool execution time

**Token Breakdown** (actual + estimated):
- `actual_prompt_tokens`: real from provider (authoritative)
- `actual_completion_tokens`: real from provider
- `estimated_system_tokens`: system prompt + protocol instructions
- `estimated_rim_tokens`: RIM metadata block only (0 for baseline)
- `estimated_source_tokens`: tool observation text
- `estimated_other_tokens`: question + tool catalog
- `token_reconciliation_diff`: actual - estimated_total (never forced to zero)
- `token_estimation_method`: "heuristic" (or "qwen_tokenizer"/"gemini_api" when available)
- `token_estimation_is_approximate`: true (all estimates labeled explicitly)

**Latency Breakdown**:
- `llm_latency_ms`: LLM call time summed across turns
- `retrieval_latency_ms`: tool execution time
- `token_counting_latency_ms`: tokenizer call time (Gemini API overhead)
- `total_latency_ms`: full side execution time

**RIM Contribution** (RIM side only):
- `rim_metadata_block`: text of upfront facts (or null for baseline)
- `tool_call_transcript`: exact sequence of tool calls made
- `trace.rim_metadata_seed_entities`: entities resolved from question
- `trace.rim_metadata_relationships`: relationships found in traversal
- `trace.query_rim_call_log`: log of on-demand query_rim calls

---

## Code Organization

### Backend Services
```
backend/services/
  rim_qa_loop.py              → RIMQALoop (core agentic loop)
  rim_qa_protocol.py          → QAProtocolAdapter (prompts + JSON parsing)
  rim_tool_dispatch.py        → ToolDispatchTable (tool routing)
  rim_metadata.py             → build_rim_metadata_block() (metadata assembly)
  rim_comparison_service_v2.py → RIMComparisonService (orchestration)
```

### Token Counting
```
backend/ai/tokencount/
  __init__.py                 → Public API
  base.py                     → TokenCountResult + TokenCounter ABC
  heuristic.py                → HeuristicTokenCounter (fallback)
  qwen.py                     → QwenTokenCounter (Qwen models)
  gemini.py                   → GeminiTokenCounter (Gemini API)
  openrouter.py               → OpenRouterTokenCounter (OpenRouter)
  registry.py                 → count_tokens() dispatch
```

### Routers & Endpoints
```
backend/routers/repo/
  rim_comparison_v2.py        → POST /repos/{repo_name}/rim-comparison/compare
                                Updated response models + endpoint
```

### Tests
```
backend/tests/ai/
  test_token_counter.py       → Token counter unit tests + integration tests
```

---

## Data Flow Diagram

```
User Question
├─ Baseline Loop                    ├─ RIM Loop
│  ├─ Tools:                        │  ├─ Tools (+ query_rim):
│  │  ├─ read_file                  │  │  ├─ read_file
│  │  ├─ find_files                 │  │  ├─ find_files
│  │  ├─ search_repository          │  │  ├─ search_repository
│  │  ├─ get_symbol                 │  │  ├─ get_symbol
│  │  ├─ search_code                │  │  ├─ search_code
│  │  ├─ get_callers/callees        │  │  ├─ get_callers/callees
│  │  └─ (no RIM)                   │  │  ├─ query_rim ← RIM-exclusive
│  │                                │  │  └─ (same retrieval capability)
│  ├─ LLM Calls:                    │  ├─ LLM Calls (with RIM metadata):
│  │  ├─ Turn 1: search...          │  │  ├─ Turn 1: search...
│  │  ├─ Turn 2: read...            │  │  ├─ Turn 2: read...
│  │  ├─ Turn 3: get_symbol...      │  │  ├─ Turn 3: query_rim...
│  │  ├─ Turn 4: answer             │  │  ├─ Turn 4: answer
│  │  └─ (up to 12 turns)           │  │  └─ (up to 12 turns)
│  │                                │  │
│  └─ Output:                       │  └─ Output:
│     ├─ answer: "..."              │     ├─ answer: "..."
│     ├─ tool_call_count: 3         │     ├─ tool_call_count: 3
│     ├─ files_read: [...]          │     ├─ files_read: [...]
│     ├─ rim_entities_accessed: 0   │     ├─ rim_entities_accessed: 1
│     └─ tokens: {...}              │     └─ tokens: {...}
│                                   │
└──────────────────┬────────────────┘
                   │
           Comparison Result
           ├─ without_rim: {ComparisonSide}
           ├─ with_rim: {ComparisonSide}
           ├─ context_diff: {files_only_without, shared, files_only_with}
           └─ trace: {RIMTrace}
               ├─ rim_metadata_seed_entities
               ├─ rim_metadata_relationships
               └─ query_rim_call_log
```

---

## Guardrails Configuration

Both sides use identical loop configuration:

```python
AgentLoopConfig(
    max_agent_turns=12,           # 12 decision points max
    max_tool_calls=15,            # 15 retrieval operations max
    max_command_executions=0,     # No terminal commands
    max_execution_seconds=180,    # 3-minute timeout per side
    max_observation_bytes=8000,   # 8KB result cap (prevents context explosion)
    max_repeated_tool_calls=3     # Stop repetition loops
)
```

---

## Known Limitations & Future Work

### Current Limitations
1. **Token tokenizer file**: Qwen tokenizer must be vendored; gracefully falls back to heuristic if missing
2. **Gemini API overhead**: countTokens endpoint adds latency; results cached within single comparison run
3. **No concurrent loops**: Sequential execution (baseline first, then RIM) to preserve DB session safety
4. **Heuristic estimation**: All local token estimates use ceil(len/4); marked explicitly as estimated

### Future Enhancements
1. **Parallel loop execution**: Run both sides concurrently once DB session management supports it
2. **Cached tokenizers**: Pre-warm Qwen tokenizer on service startup
3. **Cost tracking**: Integrate with provider billing APIs for real cost accounting
4. **Relationship types UI**: Add filter/facet for relationship types in "What Did RIM Add?"
5. **Multi-turn conversations**: Extend loop to support follow-up questions in same context

---

## Deployment Checklist

- [ ] **Backend deployment**:
  - [ ] Deploy Parts A, C, D code (committed)
  - [ ] Run `uv sync` to install tokenizers>=0.23.0
  - [ ] Restart backend service
  - [ ] Verify `/repos/{repo}/rim-comparison/compare` endpoint responds

- [ ] **Analysis validation (Part B)**:
  - [ ] Trigger re-analysis of test repo (Deep-Guard-Frontend)
  - [ ] Verify new analysis has CALLS/USES/RENDERS (SQL query)
  - [ ] Confirm `get_latest_analysis()` picks up new analysis_id

- [ ] **Frontend deployment (Part E)**:
  - [ ] Update TypeScript interfaces (rimComparisonApi.ts)
  - [ ] Restructure "View LLM Context" collapsible (3 sub-sections)
  - [ ] Restructure "What Did RIM Add?" (separate provenance)
  - [ ] Add token breakdown table rows
  - [ ] Test with sample queries
  - [ ] Verify tool transcript shows iteration (not 15 pre-fetched files)

- [ ] **Testing**:
  - [ ] Query needing 2+ files runs without Azure flooding
  - [ ] Tool call transcript shows 2-6 calls, not 15
  - [ ] RIM metadata block shows relationships (if analysis has them)
  - [ ] Baseline shows rim_metadata_block=null
  - [ ] Token reconciliation makes sense (actual ≈ estimated_breakdown)
  - [ ] "What Did RIM Add?" shows both upfront + on-demand contributions

---

## References

- **Plan document**: `/home/dheeraj/.claude/plans/async-percolating-pnueli.md`
- **Implementation guide**: `IMPLEMENTATION_GUIDE.md` (this repo)
- **Diagnostic guide**: `DIAGNOSTIC_GUIDE.md` (for analyzer debugging)
- **Engineering rules**: `CLAUDE.md` (global standards)

---

## Contact & Issues

For questions or issues:
1. Check IMPLEMENTATION_GUIDE.md troubleshooting sections
2. Enable diagnostics: `analysis_id=<id>` passed to `AnalysisEngine.run()`
3. Review diagnostic reports: `python -m backend.intelligence.diagnostics.analyzer <report.json>`
4. File issues referencing this architecture decision

---

**Status**: ✅ Implementation 80% complete (A/C/D done, B/E documented)  
**Next**: Follow IMPLEMENTATION_GUIDE.md to finish Parts B & E
