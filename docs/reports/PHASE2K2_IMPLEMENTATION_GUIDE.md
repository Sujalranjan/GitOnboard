# Phase 2K.2: Full E2E Validation Implementation Guide

## Overview

Phase 2K.2 extends Phase 2K.1 (import fixes) to fully validate the complete pipeline through all 8 stages.

**Objectives:**
1. Validate Stages 1-5 with actual results (not assumptions)
2. Re-enable and validate Stages 6-8 (Graph, Context, LLM)
3. Verify end-to-end grounding with real GitOnboard queries
4. Document actual timings, counts, and behavior
5. Identify any remaining blockers or performance issues

## Stage Specifications

### Stage 1: Parse & Analyze
**Component:** `backend.intelligence.engine.orchestration.pipeline.AnalysisEngine`

**Validates:**
- AST parsing (2,421 files)
- Symbol extraction
- Relationship discovery
- Call graph construction

**Expected Results:**
- ~27,870 entities (Phase 2J measurements)
- ~107,463 relationships (Phase 2J measurements)
- ~88 seconds execution time

**Failure Modes:**
- AST parsing errors → check Python version compatibility
- Memory exhaustion → check available RAM
- Timeout → check file scanning speed

---

### Stage 2: FactStore Persistence
**Component:** `backend.intelligence.store.fact_store.save_rim_to_fact_store()`

**Validates:**
- RIM serialization to relational schema
- Database transaction semantics
- All entity types persisted
- All relationship types persisted

**Expected Results:**
- Files: ~2,400 (from Stage 1)
- Symbols: ~25,000+ (functions, classes, methods)
- Relationships: ~107,000+ (from Stage 1)
- Routes: 0+ (if API analyzers found routes)
- Database Objects: 0+ (if database analysis found objects)
- Capabilities: 0+ (if capability detector ran)

**Failure Modes:**
- Foreign key constraint violations → orphaned relationships
- Missing entity types → incomplete RIM serialization
- Transaction deadlock → database contention

---

### Stage 3: BM25 Indexing
**Component:** `backend.intelligence.retrieval.retriever.HybridRetriever` (builds internally)

**Validates:**
- Lexical index construction from FactStore
- Code-aware tokenization
- Document collection and term frequency
- Search index readiness

**Expected Results:**
- Indexed documents: >25,000 (files + symbols + routes + db objects)
- Search functionality works
- Queries return relevant results

**Failure Modes:**
- Empty index → no documents to index
- Tokenization errors → malformed tokens
- Memory issues → index too large

---

### Stage 4: Semantic Indexing
**Component:** `backend.intelligence.retrieval.semantic_builder.SemanticIndexBuilder`

**Validates:**
- Entity-to-text conversion for embedding
- Chroma database creation
- Compression and serialization

**Expected Results:**
- Compressed Chroma database (bytes)
- Non-zero size (typically >100KB)
- Can be serialized to artifact store

**Failure Modes:**
- chromadb not installed → module not found
- No embedding model → embedding fails
- Entity format incompatible → conversion errors

---

### Stage 5: Hybrid Retrieval
**Component:** `backend.intelligence.retrieval.retriever.HybridRetriever.search()`

**Validates:**
- BM25 search execution
- Semantic search (if available)
- Result fusion (RRF)
- Repository-specific query handling

**Test Queries:**
Must test with actual GitOnboard concepts discovered in RIM:
- "authentication" → expect auth modules/functions
- "repository analysis" → expect analysis engine code
- "analysis pipeline" → expect orchestration code
- "API routes" → expect route definitions
- "database models" → expect DB schema/model definitions
- "agent context" → expect agent context assembly code
- "parser" → expect parser implementations
- "symbol resolution" → expect symbol analyzer code

**Failure Modes:**
- No results → empty index or bad tokenization
- All results irrelevant → poor ranking
- Timeouts → inefficient queries

---

### Stage 6: Graph Navigation (NEW)
**Component:** `backend.intelligence.retrieval.graph_traverser.FactStoreGraphTraverser`

**Validates:**
- FactStore-based relationship traversal
- Intent-based query classification
- Graph expansion from seed entities
- Performance on real FactStore data

**Test Patterns:**
```
Containment: "What does this module contain?"
Imports Forward: "What does this import?"
Imports Reverse: "What imports this?"
Calls Forward: "What functions does this call?"
Calls Reverse: "What calls this function?"
```

**Measurements:**
- Traversal time (per intent type)
- Entities visited
- Relationships traversed
- Database queries executed

**Expected Performance:**
- Sub-second for depth-1
- <5 seconds for depth-2
- Should be O(relationships) not exponential

---

### Stage 7: Context Assembly (NEW)
**Component:** `backend.agent.context.assembler.ContextAssembler`

**Validates:**
- Repository evidence collection
- Context budget enforcement
- Evidence relevance ranking
- RepositoryContext contract fulfillment

**Test Scenarios:**
```
Query: "What authentication mechanisms?"
Expected: Files/symbols related to auth, API routes for auth, DB auth schema

Query: "How does analysis work?"
Expected: Analysis engine code, orchestration flow, entity/relationship definitions

Query: "Database layer design?"
Expected: DB models, schema definitions, ORM setup, session management
```

**Measurements:**
- Context assembly time
- Token count (must respect budget)
- Evidence count (files, symbols, relationships)
- Completeness status

---

### Stage 8: LLM Integration (NEW)
**Component:** `backend.ai.service.LLMService` + repository context

**Validates:**
- LLM service availability
- Context transmission to LLM
- Response generation with grounding
- Can answer repository-specific questions

**Environmental Requirements:**
- OpenAI API key configured (or other LLM provider)
- Network connectivity
- Rate limit availability

**Test Scenarios:**
```
Q: "What authentication methods does GitOnboard use?"
Must ground in: auth.py, OAuth flows, session handling code

Q: "How does the analysis engine discover symbols?"
Must ground in: SymbolAnalyzer, CallGraphAnalyzer, AST traversal

Q: "What are the main API routes?"
Must ground in: route definitions, handlers, middleware
```

**Validation Criteria:**
- Response contains actual file paths from repository
- Response references actual symbols/functions
- Response mentions actual relationships from RIM
- Not hallucinated generic answers

---

## Test Query Strategy

### Pre-Flight: Discover RIM Concepts

Before running Stage 8, inspect Stage 1 results to identify real concepts:

```bash
# Look for common entity types and names
SELECT name, COUNT(*) FROM entities GROUP BY name ORDER BY COUNT(*) DESC

# Identify common relationships
SELECT type, COUNT(*) FROM relationships GROUP BY type
```

### Test Queries (Sample)

1. **Symbol Query:** Find known symbol from RIM
   ```
   "Where is [symbol name] defined?"
   Expected: File path, line number, code snippet
   ```

2. **File Query:** Find references to known file
   ```
   "What uses [file name]?"
   Expected: Importing modules, dependent code
   ```

3. **Architecture Query:** Use high-level concepts from RIM
   ```
   "How does [conceptual feature] work?"
   Expected: Related files, key functions, data flow
   ```

4. **Dependency Query:** Use relationship types from RIM
   ```
   "What does [module] depend on?"
   Expected: Imports, external calls, DB dependencies
   ```

---

## Execution Plan

### 1. Run Full E2E Validation
```bash
uv run phase2k2_full_e2e_validation.py
```

Expected runtime: 5-10 minutes total
- Stage 1: ~88 seconds
- Stage 2: ~5 seconds
- Stage 3: ~2 seconds
- Stage 4: ~5 seconds
- Stage 5: ~10 seconds
- Stage 6: ~3 seconds (or may timeout)
- Stage 7: ~15 seconds
- Stage 8: ~5 seconds (if LLM available)

### 2. Examine Results
```bash
cat phase2k2_e2e_results.json | jq .
```

Check:
- Stage status (success/fail/partial/blocked)
- Actual timings vs expectations
- Entity/relationship counts
- Search result counts
- Graph traversal metrics

### 3. Diagnose Failures
If any stage fails:
1. Check error message in JSON
2. Run stage in isolation for detailed logs
3. Verify dependencies (DB, API keys, libraries)
4. Check resource constraints (memory, disk, connections)

### 4. Validate Grounding (Stage 8+)
If Stage 8 succeeds:
1. Manually verify LLM response accuracy
2. Check that response contains repository file paths
3. Verify response mentions real symbols/functions
4. Compare against actual RIM data

---

## Passing Criteria

### Stages 1-5: Validation Success
- All stages must reach "success" status
- Entity/relationship counts must be non-zero
- Search must return results for all test queries
- Timings must be <120 seconds total

### Stage 6: Graph Navigation
- Must complete without errors
- Must return non-empty traversal results
- Must execute in <30 seconds per traversal

### Stage 7: Context Assembly
- Must return non-empty context
- Token budget must be respected
- Evidence count >0

### Stage 8: LLM Integration
- Either: service unavailable (skipped) OR response contains repository grounding
- No hallucinated file paths
- Response references real RIM concepts

---

## Performance Baselines

From Phase 2J:
- Stage 1 (Analysis): 88.51 seconds
- Full entity/relationship counts verified

Expected Phase 2K.2 additions:
- Stage 2 (FactStore): <10 seconds
- Stage 3 (BM25): <5 seconds
- Stage 4 (Semantic): <10 seconds (or partial/skipped)
- Stage 5 (Retrieval): <20 seconds
- Stage 6 (Graph): <30 seconds
- Stage 7 (Context): <20 seconds
- Stage 8 (LLM): <10 seconds (if available)

**Total Expected:** ~200-250 seconds

---

## Known Issues & Workarounds

### Issue: Chromadb Not Available
**Symptom:** Stage 4 returns None  
**Cause:** chromadb not installed  
**Workaround:** Make optional; continue to Stage 5 without semantic search

### Issue: Graph Traversal Slow (>60 seconds)
**Symptom:** Stage 6 timeout  
**Cause:** Possible N+1 queries or large traversal  
**Workaround:** Check database query logs; may need indexing

### Issue: LLM API Key Missing
**Symptom:** Stage 8 skipped or blocked  
**Cause:** `OPENAI_API_KEY` not configured  
**Workaround:** Configure key or skip LLM validation

### Issue: Context Assembly Fails
**Symptom:** Stage 7 returns error  
**Cause:** Missing ContextAssembler or contract changes  
**Workaround:** Check backend.agent.context imports; verify contracts module

---

## Deliverables

### 1. Results File
`phase2k2_e2e_results.json` — Machine-readable results

### 2. Report
`PHASE2K2_FULL_E2E_VALIDATION_REPORT.md` — Comprehensive analysis

### 3. Logs
Check stdout for detailed logs per stage

### 4. Verdict
One of:
- `FULL_E2E_VALIDATED` — All 8 stages pass
- `E2E_PARTIALLY_VALIDATED` — Stages 1-5 pass, 6+ have issues
- `E2E_BLOCKED` — Critical blockers in stages 1-5

---

## Next Steps (Phase 2K.3+)

### If Full E2E Passes
1. Document architecture completeness
2. Set up automated E2E regression testing
3. Begin Phase 3 (Advanced features)
4. Optimize identified bottlenecks

### If Stages 1-5 Pass, 6+ Fail
1. Investigate Stage 6+ failures separately
2. Consider blocking on Graph/Context if not critical
3. Focus LLM grounding validation

### If Critical Stages Fail
1. Diagnose root cause per stage
2. May require production code fixes (not just validation)
3. Create targeted hotfix for blocking issue

---

**Status:** Ready for Phase 2K.2 execution  
**Expected Completion:** ~5-10 minutes runtime  
**Follow-up:** Phase 2K.3 (Optimization & Hardening)
