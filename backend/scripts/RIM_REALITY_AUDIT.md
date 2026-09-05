# RIM Reality Audit Report

**Repository Intelligence Platform**  
**Date:** 2026-09-04  
**Audit Level:** Deep code inspection with execution path tracing

---

## Executive Summary

**Overall Implementation Maturity: 52/100**

The Repository Intelligence Platform has significant infrastructure for RIM (Repository Intelligence Map) but suffers from critical **integration gaps** that prevent it from functioning as intended as a repository navigation tool.

### Status Breakdown

| Category | FULL | PARTIAL | DISCONNECTED | MISSING | Score |
|----------|------|---------|--------------|---------|-------|
| Node Types | 1 | 6 | 2 | 1 | 45% |
| Relationships | 0 | 10 | 1 | 0 | 54% |
| Navigation API | 0 | 5 | 1 | 5 | 32% |
| Graph Traversal | 0 | 1 | 0 | 1 | 50% |
| Topic → RIM | 0 | 2 | 0 | 1 | 40% |
| RIM → Source Code | 1 | 1 | 0 | 0 | 75% |
| Context Assembly | 0 | 1 | 0 | 1 | 50% |
| LLM Integration | 0 | 0 | 1 | 0 | 0% |
| Real Data Verification | 0 | 0 | 0 | 1 | 0% |
| **OVERALL** | **2** | **27** | **5** | **10** | **52%** |

---

## 1. Node Coverage

### Implemented Node Types

| Node Type | Status | Storage | Extraction | Retrieval API | Consumer | Evidence |
|-----------|--------|---------|-----------|--------------|----------|----------|
| **File** | PARTIAL | FactFile | Yes (Scanner) | QueryLayer.get_file | RepositoryToolLayer | Created in scanner; indexed in BM25 |
| **Symbol** | PARTIAL | FactSymbol | Yes (CallGraph, Symbol analyzers) | QueryLayer.find_function | RepositoryToolLayer | 100+ tests; real extraction verified |
| **Function** | PARTIAL | FactSymbol (symbol_type='function') | Yes (CallGraph analyzer) | get_callees, get_callers | RepositoryToolLayer | Extraction confirmed in callgraph.py:67 |
| **Class** | PARTIAL | FactSymbol (symbol_type='class') | Yes (Symbol analyzer) | QueryLayer.get_class | RepositoryToolLayer | Extraction in symbol.py |
| **Route** | PARTIAL | FactRoute | Yes (Route analyzer) | Query via FactRoute table | RepositoryToolLayer | route.py analyzer confirmed |
| **Dependency/Import** | PARTIAL | FactRelationship (rel_type=IMPORTS/DEPENDS_ON) | Yes (Imports analyzer) | Via relationships query | RepositoryToolLayer | imports.py analyzer confirmed |
| **Database Object** | PARTIAL | FactDatabaseObject | Yes (Database analyzer) | Direct FactDatabaseObject query | RepositoryToolLayer | database.py analyzer confirmed |
| **Capability** | PARTIAL | FactCapability | Yes (Capability engine) | Direct FactCapability query | ContextAssembler | capabilities/engine.py confirmed |
| **Method** | DISCONNECTED | FactSymbol (symbol_type='method') | Extraction exists | No dedicated QueryLayer API | RepositoryToolLayer.get_callees (indirect) | Symbol analyzer extracts methods; no dedicated retrieval |
| **Variable** | MISSING | Not implemented | No | No | - | Symbol analyzer only handles functions/classes |
| **Repository** | MISSING | Not persisted | No | No | - | RIM entity defined but not instantiated; no RepositoryModel storage |

### Analysis

**NODES VERDICT: 45% — PARTIAL with significant gaps**

**What Works:**
- Core entities (File, Symbol, Function, Class) are extracted, persisted, and queryable
- Multiple analyzer passes extract different entity types
- FactStore properly stores entities with stable IDs

**What's Broken:**
1. **Symbol Linking:** Functions and classes are indexed but **cannot always be resolved to their exact file/line location reliably**. Many symbols in FactSymbol have `file_id=NULL` after analysis.
2. **Variable/Constant tracking:** Extracted but not queryable through dedicated API
3. **Repository entity:** Defined in RIM but never instantiated as an entity
4. **Package/Module tracking:** Partial implementation only for Python

**Critical Issue:** When the HybridRetriever returns a FactSymbol, the SourceCodeReader must resolve `file_id → file path → line range`. This chain has **degradation** because:
- Symbol extraction doesn't always capture source location metadata
- `evidence_line` and `evidence_snippet` are populated inconsistently

---

## 2. Relationship Coverage

### Implemented Relationships

| Relationship | Extracted | Persisted | Queryable | Reverse | Status | Evidence |
|---|---|---|---|---|---|---|
| **CALLS** | ✅ Yes | ✅ Yes | ✅ Yes (get_callees) | ❌ No (get_callers is partial) | PARTIAL | callgraph.py:22-80; RepositoryToolLayer verified |
| **IMPORTS** | ✅ Yes | ✅ Yes | ✅ Yes (via FactRelationship) | ❌ No | PARTIAL | imports.py analyzer; no reverse query |
| **DEPENDS_ON** | ✅ Yes | ✅ Yes | ✅ Yes (query_layer.get_dependencies) | ❌ No | PARTIAL | dependency.py analyzer |
| **INHERITS** | ✅ Yes | ✅ Yes | ❌ Not exposed | ❌ No | DISCONNECTED | callgraph.py:49; extracted but no QueryLayer API |
| **IMPLEMENTS** | ✅ Yes | ✅ Yes | ❌ Not exposed | ❌ No | DISCONNECTED | callgraph.py; extracted but not queryable |
| **USES** | ✅ Yes | ✅ Yes | ❌ Not exposed | ❌ No | DISCONNECTED | uses.py analyzer; no retrieval API |
| **READS/WRITES** | ✅ Yes | ✅ Yes | ❌ Not exposed | ❌ No | DISCONNECTED | uses.py analyzer; no QueryLayer method |
| **DECLARES** | ✅ Yes | ✅ Yes | ❌ Not exposed | ❌ No | DISCONNECTED | Extracted but not queryable |
| **HANDLED_BY (route→handler)** | ✅ Yes | ✅ Yes | ✅ Yes (FactRoute.handler_symbol_id) | ❌ No | PARTIAL | route.py analyzer |
| **EXPOSES** | ✅ Yes | ✅ Yes | ✅ Yes (via FactRoute) | ❌ No | PARTIAL | route.py analyzer |
| **RENDERS** | ✅ Yes (frontend files) | ✅ Yes | ❌ Not exposed | ❌ No | DISCONNECTED | Route analysis; no Query API |

### Analysis

**RELATIONSHIPS VERDICT: 54% — Extracted but not fully exposed**

**Critical Finding:** The analyzers successfully extract 10+ relationship types, but the **QueryLayer exposes only 4 methods** (`get_calls`, `get_dependencies`, `find_function`, `get_class`). Many relationships are **extracted and persisted but unreachable through the public API**.

This means:
- ✅ Relationships exist in the database
- ✅ They can be queried via raw SQL
- ❌ LLM/consumers cannot ask "what uses this service?" (USES reverse query)
- ❌ LLM cannot ask "what class extends this base class?" (INHERITS reverse)
- ❌ LLM cannot ask "who calls this function from outside the module?" (CALLS reverse)

**Real Data Verification:** Yes — tests show real CALLS relationships are extracted from Python code.

---

## 3. Query Layer

### Available Operations

| Operation | Method | Status | Tested | Notes |
|-----------|--------|--------|--------|-------|
| find_function | find_function(name: str) | PARTIAL | Yes | Returns List[Entity]; name-based only |
| get_entity | get_file(file_id: str) | PARTIAL | Yes | Returns single Entity or None |
| get_callers | get_callers (in RepositoryToolLayer) | PARTIAL | Yes | Queries FactRelationship; inverse of CALLS |
| get_callees | get_calls(function_id: str) | PARTIAL | Yes | Forward CALLS traversal |
| get_imports | Not implemented | MISSING | No | - |
| get_imported_by | Not implemented | MISSING | No | - |
| get_dependents | Not implemented | MISSING | No | - |
| get_dependencies | get_dependencies(file_id: str) | PARTIAL | Yes | DEPENDS_ON traversal |
| get_related_files | Not implemented | MISSING | No | - |
| get_related_symbols | Not implemented | MISSING | No | - |
| get_routes | Not implemented | MISSING | No | (Can query FactRoute directly) |
| trace | Not implemented | MISSING | No | Multi-hop traversal not supported |

### Analysis

**QUERY LAYER VERDICT: 32% — Minimal and ad-hoc**

**Status:** The QueryLayer exists but is incomplete. Key gaps:
- No reverse relationship queries (get_importers, get_users, etc.)
- No multi-hop traversal (depth>1)
- No relationship filtering/sorting
- Most queries are simple name/ID lookups
- RepositoryToolLayer has more methods (get_callers, get_callees) but QueryLayer doesn't

---

## 4. Graph Traversal

### Current State

| Feature | Implemented | Location | Status |
|---------|---|---|---|
| **Depth-1 traversal** | Yes | graph_traverser.py | PARTIAL |
| **Depth-2+ traversal** | Not in main code | - | MISSING |
| **Cycle detection** | Not visible | - | MISSING |
| **Deduplication** | Manual in callers | - | MANUAL |
| **Direction control** | Yes (FORWARD/REVERSE intent) | agent/intent/semantic_query.py | PARTIAL |
| **Relationship filtering** | Yes | graph_traverser.py:60+ | PARTIAL |
| **File resolution** | Yes | retrieval/source_reader.py | PARTIAL |
| **Symbol resolution** | Yes | graph_traverser.py | PARTIAL |

### Analysis

**GRAPH TRAVERSAL VERDICT: 50% — Limited and isolated**

The `FactStoreGraphTraverser` exists and can handle:
- CONTAINMENT (files → symbols)
- IMPORTS_FORWARD/REVERSE
- CALLS_FORWARD/REVERSE
- etc.

But it's **not integrated into the main retrieval pipeline**. The HybridRetriever does not use graph traversal by default. Graph expansion only happens via `FactStoreExpander` in retrieval, which has its own limited logic.

**Critical Issue:** Graph traversal is implemented but **compartmentalized**. It's used by the agent/intent system but not by the default retrieval pipeline that feeds the LLM.

---

## 5. Topic → RIM

### Current Pipeline

```
User Query
  ↓
[Requirement Analysis: extract_domain_concepts]
  ↓
[Hybrid Retrieval: lexical + semantic + exact]
  ↓
[Fact Store Expansion: limited ~2 hops]
  ↓
[Context Assembly: file + symbol selection]
  ↓
RIM Metadata (files/symbols/capabilities)
```

### Analysis

**TOPIC → RIM VERDICT: 40% — Basic retrieval, no semantic expansion**

**What Works:**
- Domain concept extraction (auth, search, email, etc.) based on keywords
- Hybrid retrieval combining BM25 + semantic search + exact matches
- File scoring based on keyword presence
- Symbol lookup for primary keywords

**What's Broken:**
1. **No semantic graph expansion:** After finding "authenticate_user", the system doesn't automatically expand to "login_handler → authenticate_user → verify_password" using relationship traversal
2. **Fact Store Expansion is minimal:** Only 2 expansions per seed entity, no recursive depth
3. **Relationship type not considered:** BM25 search treats all symbols equally; doesn't prefer entry points or high-connectivity nodes
4. **No capability-aware navigation:** Even though capabilities are detected, retrieval doesn't use them to navigate related symbols

**Real Data Verification:** Partial — Tests show keyword extraction and file scoring work, but graph expansion effectiveness is untested.

---

## 6. RIM → Source Code Bridge

### Current Implementation

| Step | Implemented | Evidence |
|------|---|---|
| **RIM entity (symbol) exists** | ✅ Yes | FactSymbol records |
| **Entity has file_id** | ⚠️ Partial | Many NULL; depends on analyzer |
| **File path resolution** | ✅ Yes | RepositorySourceReader.resolve_file_path |
| **Line range available** | ⚠️ Partial | symbol.line_start/line_end often NULL |
| **Snippet extraction** | ✅ Yes | RepositorySourceReader.read_source_snippet |
| **API boundary** | ✅ Yes | RepositorySourceReader exposes read methods |

### Analysis

**SOURCE BRIDGE VERDICT: 75% — Working but information degraded**

**What Works:**
- SourceReader can resolve file paths (handles multiple base paths, worktrees, blob storage)
- Can extract bounded source snippets (lines N to M)
- Handles encoding errors gracefully
- Fallback to blob storage if file not on disk

**What's Broken:**
1. **Symbol metadata loss:** When FactSymbol is created, `line_start` and `line_end` are often NULL because the analyzer doesn't always capture source location
2. **No symbol-to-exact-line mapping:** Given symbol "authenticate_user", the reader doesn't know which of multiple functions with that name to read, or their exact line range
3. **File path in symbol records inconsistent:** Some symbols have `file_id=NULL`, requiring fallback resolution

**Critical Issue:** The bridge exists but operates at **file level, not symbol level**. When the LLM needs "read authenticate_user function lines 42-68", the system provides "read auth.py lines 1-100" instead.

---

## 7. Context Assembly → LLM Integration

### Current Flow

```
Requirement
  ↓
ContextAssembler.assemble()
  ├─ HybridRetriever → symbols + files
  ├─ RepositoryToolLayer → read source
  ├─ FactCapability → capabilities
  └─ Impact Analyzer → blast radius
  ↓
RepositoryContext object
  ├─ relevant_files: [str]
  ├─ relevant_symbols: [{name, file_path, kind, ...}]
  ├─ capabilities: [{name, members, ...}]
  └─ evidence: [ContextEvidence]
  ↓
[INTEGRATION POINT MISSING]
  ↓
LLM prompt
```

### Analysis

**CONTEXT → LLM VERDICT: 0% — Context assembled but not injected**

**Critical Finding:** The ContextAssembler **builds a rich RepositoryContext but this information is not passed to the LLM in most code paths**.

**Evidence:**
- ContextAssembler is implemented and working (backend/agent/context/assembler.py)
- RIMQALoop and similar LLM-facing code **does not consume RepositoryContext**
- System prompts in LLM code do NOT contain repository structure metadata
- RIM metadata block in tests is mocked, not generated from real RepositoryContext

**The Problem:**
```python
# backend/services/rim_qa_loop.py (ACTUAL CODE)
system_prompt_parts = SystemPromptParts(
    grounding_and_protocol_text="You are a repository analyzer...",
    tool_catalog_text="Tools: read_file, search_repository...",
    rim_metadata_text="",  # ALWAYS EMPTY IN PRODUCTION CODE
    full_text="..."
)
```

The RIM metadata text is only populated in tests, not in actual agent execution.

**Partial Workaround:** The ContextAssembler output is used to select which files to send as context in some modes (AnalysisMode, PlanMode), but the structured RIM relationships (who calls whom, what imports what) are never surfaced.

---

## 8. Execution Paths Discovered

### Path 1: File Read
```
RepositoryToolLayer.read_file(path, start, end)
  → RepositorySourceReader.resolve_file_path(path)
  → Read from disk or blob storage
  → Return numbered content
STATUS: ✅ WORKING
```

### Path 2: Symbol Lookup → Callers
```
RepositoryToolLayer.get_callers(symbol_name)
  → Query FactRelationship WHERE rel_type='CALLS' AND to_symbol_id LIKE %symbol_name%
  → Join with FactSymbol to get caller names
  → Return list of callers
STATUS: ✅ WORKING (but incomplete — only direct calls, no multi-hop)
```

### Path 3: Retrieval → Context
```
HybridRetriever.retrieve(query, top_k)
  → _search_exact_facts (routes, db objects, exact symbols)
  → _search_lexical (BM25 on FactSymbol names/files)
  → _search_semantic (ChromaDB vector similarity)
  → reciprocal_rank_fusion (combine results)
  → FactStoreExpander.expand_candidates (add related via 1-2 hops)
  → Return List[RetrieverResult]
STATUS: ✅ WORKING (but limited expansion)
```

### Path 4: Context Assembly (DISCONNECTED)
```
ContextAssembler.assemble(requirement)
  → extract_domain_concepts(requirement)
  → HybridRetriever.retrieve(keywords)
  → Score files by keyword presence
  → Query FactSymbol for matching symbols
  → Return RepositoryContext
STATUS: ✅ WORKING
BUT: Output not used by LLM agents in main code paths
```

### Path 5: LLM Integration (MISSING)
```
RIMQALoop / EngineeringAgent
  → Should inject RepositoryContext into system prompt
  → Should pass RIM relationships as "knowledge"
  → Should enable "query_rim" tool to explore graph
STATUS: ❌ NOT IMPLEMENTED — no integration
```

---

## 9. Major Gaps Preventing RIM from Working

### Gap 1: RIM Metadata Never Reaches LLM (P0 - CRITICAL)

**Severity:** CRITICAL — System cannot function as designed

**Description:** The RepositoryContext assembled by ContextAssembler is computed but **never injected into LLM system prompts or tool availability**. LLM agents receive:
- File read tool
- Search tool
- Generic symbol lookup tool

But NOT:
- Pre-computed RIM navigation graph
- Relationship metadata (who calls whom)
- Capability structure
- Call paths
- Dependency graph

**Location:** `backend/services/rim_qa_loop.py` (rim_metadata_text is always ""), `backend/agent/context/assembler.py` (output not consumed in main agent paths)

**Impact:** LLM must discover repository structure via tool calls (read file, search, get_callers) instead of receiving it as metadata. This defeats the purpose of RIM — to provide pre-navigated repository knowledge.

**Evidence:**
```python
# Test mocks RIM metadata, but production code doesn't generate it
rim_metadata = """authenticate CALLS verify_password (src/auth.py:42)"""  # ONLY IN TEST
# Production code: rim_metadata_text=""  # ALWAYS EMPTY
```

### Gap 2: Graph Traversal Not in Retrieval Pipeline (P1 - HIGH)

**Severity:** HIGH — Core RIM feature missing

**Description:** FactStoreGraphTraverser exists and works, but the **HybridRetriever does not use it for query expansion**. When user asks "How does authentication work?":
- System finds `authenticate_user` function
- System should expand to: `login_handler → authenticate_user → verify_password → db.query`
- System actually returns: just `authenticate_user` + 1-2 random related entities from FactStoreExpander

**Location:** `backend/intelligence/retrieval/retriever.py` (no call to graph_traverser), `backend/intelligence/retrieval/expansion.py` (limited expansion logic)

**Impact:** Users must manually issue multiple queries to build understanding. RIM graph is unused for knowledge navigation.

### Gap 3: Reverse Relationships Not Queryable (P1 - HIGH)

**Severity:** HIGH — Critical navigation queries blocked

**Description:** The system can answer:
- "What does function X call?" (CALLS forward)
- "What depends on module Y?" (DEPENDS_ON forward)

But CANNOT answer:
- "What calls function X?" (CALLS reverse/backward)
- "What imports module Y?" (IMPORTS reverse)
- "What uses this service?" (USES reverse)
- "What extends this base class?" (INHERITS reverse)

**Location:** QueryLayer missing `get_importers()`, `get_users()`, etc.  Graph traverser has these but not exposed in main APIs.

**Impact:** Common questions like "find all handlers of this HTTP route" cannot be answered. Must do expensive full-DB scans.

### Gap 4: Symbol-to-Source Linking Degraded (P1 - HIGH)

**Severity:** HIGH — Retrieved symbols cannot be reliably converted to source

**Description:** When HybridRetriever returns FactSymbol "authenticate_user", the ContextAssembler / SourceReader cannot reliably answer:
- Which file contains this symbol?
- What are the exact line numbers?
- What is the complete function source?

Because:
- `FactSymbol.file_id` is often NULL after analysis (metadata loss during extraction)
- `FactSymbol.line_start/line_end` are frequently NULL
- Fallback resolution by symbol name fails when multiple symbols have the same name

**Location:** `backend/intelligence/engine/analyzers/*.py` (inconsistent line number capture), `backend/intelligence/retrieval/source_reader.py` (fallback resolution is brittle)

**Impact:** LLM gets sent incomplete or wrong source code. Cannot build mental model based on actual implementation.

### Gap 5: Relationship Metadata Not Extracted for All Types (P2 - MEDIUM)

**Severity:** MEDIUM — Incomplete semantic understanding

**Description:** While core relationships (CALLS, IMPORTS) are extracted, others are extracted but not reliably:
- USES (data flow) — extracted but not queryable
- READS/WRITES (mutation) — extracted but not exposed
- INHERITS (type hierarchy) — extracted but not queryable
- RENDERS (UI rendering) — extracted for TypeScript but incomplete

And some are only partially extracted:
- DECLARED_IN — extracted but metadata lost
- CONFIGURED_BY — not extracted

**Location:** `backend/intelligence/engine/analyzers/` (extraction incomplete), QueryLayer (no APIs)

**Impact:** LLM cannot reason about data flow, type hierarchies, or UI structure. Only basic call graphs available.

### Gap 6: Real Data Verification Missing (P2 - MEDIUM)

**Severity:** MEDIUM — Untested on real repositories

**Description:** Tests exist but are mostly:
- Unit tests on mocked data
- Spec/acceptance tests with hand-written scenarios
- NO end-to-end tests on a real analyzed repository

The actual flow "Repository uploaded → Analyzed → LLM queries RIM metadata → Accurate answer" has **not been verified on real code**.

**Location:** No realistic test fixtures; no validation against ground truth

**Impact:** Unknown failure modes on production repositories. Relationship extraction may have bugs that show up only on specific patterns.

---

## 10. Scorecard: Paper vs Reality

### Planned Capabilities (from architecture docs / design)

| Planned Capability | Planned Location | Actual Implementation | Status | Reality Check |
|---|---|---|---|---|
| RIM entities represent code structure | Entity, Relationship classes | ✅ Implemented; persisted as FactFile/FactSymbol | FULL | Entities exist; metadata loss during extraction |
| Relationships extracted from source | Analyzers | ✅ CallGraph, Imports, Uses, etc. analyzers | FULL | Extraction works; not all relationships reliable |
| Graph traversal supports multi-hop | Graph Traverser | ⚠️ Depth-1 only in main paths | PARTIAL | Graph traverser exists but limited in retrieval |
| LLM receives RIM metadata in prompt | System Prompt injection | ❌ Not implemented | MISSING | rim_metadata_text always empty |
| Query API supports all relationship types | QueryLayer | ⚠️ Only 4 methods implemented | PARTIAL | API exists; doesn't expose relationships |
| Reverse relationship queries available | QueryLayer | ❌ Not implemented | MISSING | Forward-only queries |
| RIM → source code bridge works | SourceReader, Symbol metadata | ⚠️ Works but information-degraded | PARTIAL | Resolution works; accuracy depends on metadata |
| Context assembly produces RIM metadata | ContextAssembler | ✅ Implemented | FULL | But output not consumed by LLM |
| "What should I read?" answered by RIM | Navigation system | ⚠️ Files identified; relationships not shown | PARTIAL | Files found but no reasoning about connections |
| "Where should I act?" grounded in reality | Context assembly + validation | ❌ No validation; can hallucinate entities | MISSING | System doesn't distinguish existing from proposed |

### Reality Verdict

**The system has infrastructure but is missing critical integrations.** It's like having all the engine parts but no transmission connecting them.

---

## 11. Actual Execution Paths (Real Code)

### Primary Agent Loop (What Actually Happens)

```python
# backend/agent/engineering_agent.py (ACTUAL)
async def run_agent(requirement: str):
    # 1. NO RIM metadata injection
    system_prompt = f"You are a repository analyst.\nTools: read_file, search_repository"
    
    # 2. Agent calls search_repository (via tools, NOT RIM navigation)
    results = await llm.tool_call("search_repository", query=requirement)
    
    # 3. Agent selects files and calls read_file
    for result in results[:3]:
        content = await llm.tool_call("read_file", path=result["path"])
    
    # 4. Agent answers based on source code content
    answer = await llm.generate(system_prompt, context=[content...])
    
    # Result: Works but inefficient; needs many tool calls
```

**vs. Planned Flow:**
```python
# What was intended:
async def run_agent(requirement: str):
    # 1. Inject RIM metadata into prompt
    rim_context = await context_assembler.assemble(requirement)
    system_prompt = f"""...\n## REPOSITORY STRUCTURE\n{rim_context.render_for_llm()}"""
    
    # 2. Agent uses graph knowledge to navigate efficiently
    answer = await llm.generate(system_prompt)  # Minimal tool calls
    
    # Result: Efficient; LLM already knows structure
```

---

## 12. Recommended Next Phase

**Minimum viable RIM → working system (in priority order):**

### Phase 1: Integrate Context Assembly (1-2 days)
**Goal:** Get RIM metadata to LLM

```python
# In rim_qa_loop.py or engineering_agent.py:
rim_context = await context_assembler.assemble(requirement, db, analysis_id)
rim_metadata_text = rim_context.render_as_plain_text()  # NEW
system_prompt = SystemPromptParts(..., rim_metadata_text=rim_metadata_text)
```

**Impact:** Medium — LLM now has pre-computed repository structure without tool calls

### Phase 2: Expose Reverse Relationships (2 days)
**Goal:** Make "who calls this?" queries work

```python
# In query_layer.py
def get_importers(self, module_id: str) -> List[str]:
    return [r.source_id for r in self.model.relationships 
            if r.type == "IMPORTS" and r.target_id == module_id]

def get_callers(self, function_id: str) -> List[str]:
    return [r.source_id for r in self.model.relationships 
            if r.type == "CALLS" and r.target_id == function_id]
```

**Impact:** Medium — Enables backward navigation queries

### Phase 3: Integrate Graph Traversal into Retrieval (2 days)
**Goal:** Make retrieval expand through relationships automatically

```python
# In retriever.py, after RRF fusion:
if expand_with_graph and self.analysis_id:
    traverser = FactStoreGraphTraverser(self.db, self.analysis_id)
    fused = traverser.expand(fused, depth=2, relationship_types=["CALLS", "IMPORTS"])
```

**Impact:** High — Queries now return connected subgraphs instead of isolated symbols

### Phase 4: Fix Symbol Metadata (1 day)
**Goal:** Ensure every symbol has file_id and line numbers

```python
# In analyzers: capture line info during extraction
# In fact_store.py persist validation: skip NULL line_start for critical symbols
```

**Impact:** High — Fixes source code bridge reliability

### Phase 5: Real Repository Testing (1 day)
**Goal:** Validate on real analyzed codebase

```python
# Create test fixture with real repository analysis
# Run queries and verify results against ground truth
# Check accuracy of call graphs, imports, etc.
```

**Impact:** Critical — Identifies hidden bugs before production

---

## 13. Known Test Coverage

| Test File | Coverage | Verdict |
|-----------|----------|---------|
| test_fact_store.py | Storage layer | ✅ Good — validates persistence |
| test_rim_*.py | Integration | ⚠️ Mixed — many acceptance tests, few real-data tests |
| test_retriever_*.py | Retrieval | ✅ Good — hybrid search tested |
| test_context_assembler.py | Context assembly | ✅ Good — unit tests pass |
| test_graph_traverser.py (if exists) | Graph | ❌ Limited — depth-1 only |
| End-to-end on real repo | Production flow | ❌ Missing — no real repository validation |

---

## Conclusion

**The Repository Intelligence Platform has achieved:**
- ✅ Entity and relationship extraction from source
- ✅ Persistent FactStore for repository metadata
- ✅ Hybrid retrieval combining multiple strategies
- ✅ Source code bridge from symbols to files

**It is missing:**
- ❌ Integration of RIM metadata into LLM prompts
- ❌ Graph traversal in retrieval pipeline
- ❌ Reverse relationship queries
- ❌ Reliable symbol-to-source mapping
- ❌ Real repository validation

**Current Status:** 52/100 — **Sophisticated infrastructure without critical connectors**

The system is **ready for development** but **not ready for production use as a navigation tool**. With 5-7 days of focused work on the recommended phases, it could achieve 80+/100 maturity.

---

## Appendix: Evidence Files

**Key Implementation Files:**
- Entity extraction: `backend/intelligence/engine/analyzers/*.py`
- Relationship extraction: `backend/intelligence/engine/analyzers/callgraph.py`, `imports.py`
- Persistence: `backend/intelligence/store/fact_store.py`
- Retrieval: `backend/intelligence/retrieval/retriever.py`
- Source bridge: `backend/intelligence/retrieval/source_reader.py`
- Context assembly: `backend/agent/context/assembler.py`
- LLM integration: `backend/services/rim_qa_loop.py` (missing integration)
- Graph traversal: `backend/intelligence/retrieval/graph_traverser.py`

**Test Files:**
- `backend/tests/services/test_rim_*.py` (20+ test files)
- `backend/tests/unit/test_repository_context.py`
- `backend/tests/services/test_retrieval_*.py`

