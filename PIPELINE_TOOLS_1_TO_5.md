# Pipeline Tools 1-5: Identification & Verification Status

## Overview

The 5 core pipeline tools that extract and process repository knowledge:

| # | Tool | File Location | Status | Tests |
|---|------|---------------|---------|----|
| 1 | **Symbol Inspection** | `/backend/intelligence/inspection/symbol_inspector.py` | ✅ Implemented | Need verification |
| 2 | **File Retrieval** | `/backend/routers/repo/structure.py` | ✅ Fixed | 15 tests (Phase 2L) |
| 3 | **Graph Query** | `/backend/routers/repo/graph.py` | ✅ Fixed | 39 tests (Phase 2L) |
| 4 | **Symbol Search** | `/backend/routers/repo/symbols.py` | ✅ Implemented | Need verification |
| 5 | **Context Assembly** | `/backend/intelligence/engine/orchestration/stage7_context_assembly.py` | ⚠️ Found issue | See Phase 2L.7 |

---

## Tool #1: Symbol Inspection

**Location:** `/backend/intelligence/inspection/symbol_inspector.py`

**Purpose:** Get symbol metadata and source code using analysis isolation

**Functions:**
1. `inspect_file()` - Get file structure WITHOUT reading full source
2. `inspect_symbol()` - Get metadata about ONE symbol
3. `read_symbol()` - Read exact source code of a symbol
4. `read_lines()` - Read specific line range from a file
5. `read_file()` - Read entire file

**Status:** ✅ Implemented with comprehensive documentation

---

## Tool #2: File Retrieval

**Location:** `/backend/routers/repo/structure.py`  
**Endpoint:** `GET /{repo_name}/files/{file_path}`

**Purpose:** Retrieve file contents from analyzed repository (FactStore)

**Changes (Commit `aafeae5`):**
- ✅ Removed GitHub API fallback (files must exist in FactStore)
- ✅ Added strict file existence validation
- ✅ Validate line range parameters upfront
- ✅ Return 404 for nonexistent files
- ✅ Explicit error codes: 400/404/500

**Tests:** 15 validation tests, 100% passing ✅

---

## Tool #3: Graph Query

**Location:** `/backend/routers/repo/graph.py`  
**Endpoint:** `GET /{repo_name}/graph/{node_id}`

**Purpose:** Traverse repository relationship graph

**Changes (Commit `aafeae5`):**
- ✅ Added node_id existence validation
- ✅ Parameter validation (direction, depth, max_nodes, relationship_type)
- ✅ Return 404 for invalid nodes
- ✅ Clear distinction: 404 for invalid vs 200 with empty for valid-but-empty

**Tests:** 39 validation tests, 100% passing ✅

---

## Tool #4: Symbol Search

**Location:** `/backend/routers/repo/symbols.py`  
**Endpoint:** `POST /{repo_name}/symbols/explain`

**Purpose:** Search and explain symbols in repository

**Implementation:**
- `explain_symbol()` - Get detailed explanation of a symbol using LLM
- Uses FactSymbol for symbol lookup
- Includes signature, documentation, usage context

**Status:** ✅ Implemented, but **verification status unclear**

---

## Tool #5: Context Assembly

**Location:** `/backend/intelligence/engine/orchestration/stage7_context_assembly.py`  
**Phase:** Stage 7 in the research pipeline

**Purpose:** Assemble multi-layer context for LLM queries

**Current Status:** ⚠️ **ISSUE FOUND**

From Phase 2L.7 Critical Findings:
- Stage 7 (Context Assembly): ❌ FAILED — 0 files/0 symbols selected for all 10 questions
- Result: 0 bytes of source code delivered to LLM
- Root cause: Graph navigation found 0 entities (cascading failure from Stage 6)

**Before/After Context Assembly:**
```
Before: 0 entities from Graph Navigation (Stage 6)
          ↓
Context Assembly Stage 7
          ↓
After: 0 files, 0 symbols selected
```

---

## Verification Status Summary

| Tool | Implementation | Validation | Error Handling | Analysis Isolation | LLM Ready |
|------|-----------------|------------|----------------|--------------------|-----------|
| #1 - Symbol Inspection | ✅ Yes | ⚠️ Need test | ✅ Has error handling | ✅ Yes | ⚠️ Need test |
| #2 - File Retrieval | ✅ Yes | ✅ 15 tests pass | ✅ Explicit errors | ✅ Yes | ✅ Yes |
| #3 - Graph Query | ✅ Yes | ✅ 39 tests pass | ✅ Explicit errors | ✅ Yes | ✅ Yes |
| #4 - Symbol Search | ✅ Yes | ⚠️ Need test | ⚠️ Unknown | ⚠️ Unknown | ⚠️ Need test |
| #5 - Context Assembly | ✅ Yes | ❌ Failed (0/10) | ⚠️ Unknown | ⚠️ Unknown | ❌ No |

---

## What Needs To Be Done

### For Tools #1, #4:
- [ ] Write integration tests with real repository data
- [ ] Verify error handling
- [ ] Verify analysis isolation
- [ ] Test with natural language queries

### For Tool #5:
- [ ] Debug Stage 6 (Graph Navigation) - why 0 entities found?
- [ ] Fix cascading failure from Stage 6 → Stage 7
- [ ] Re-run Phase 2L.7 validation after fix
- [ ] Verify context assembly produces non-zero output

---

## Next Steps

1. **Create integration test** for Tools #1, #4, #5
2. **Run on real repository** (repo_id=1, completed analysis)
3. **Verify each tool's output:**
   - Tool #1: Returns file/symbol metadata
   - Tool #4: Returns symbol explanation
   - Tool #5: Selects files and symbols for context
4. **Test tool chaining** (Tool #1 → #3 → #4 → #5)
5. **Document findings** in verification report

---

## Reference: Phase 2L.7 Discovery

Full analysis in `/tmp/phase2l7_benchmark/PHASE2L7_FINAL_REPORT.md`

**Key Finding:** Tools #2 and #3 work, but Tool #5 receives 0 input from Tool #3, causing cascading failure. This is a **Stage 6 issue**, not a Stage 7 issue.

**Before Phase 2M validation,** Tools #1-5 must be verified to work correctly.
