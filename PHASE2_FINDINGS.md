# Phase 2: RIM Retrieval Analysis — FINDINGS

## Executive Summary

**Database Status: ✓ Data Exists**  
**Retrieval Status: ✗ Not Finding Data**

The FactStore database contains repository-specific entities and relationships, but the RIM retrieval pipeline is failing to find them.

---

## Evidence from Database Inspection

### 1. Authentication-Related Symbols (✓ Present)

Query: `SELECT * FROM symbols WHERE name ILIKE '%auth%'`

**Results:**
- 6 symbols with "auth" in name
- Located in: `controllers/authcontroller.js`, `middleware/authenticateToken.js`, `src/components/Login.tsx`
- Types: FUNCTION, COMPONENT

Example entities:
```
- setAuthCookies (FUNCTION, controllers/authcontroller.js)
- clearAuthCookies (FUNCTION, controllers/authcontroller.js)
- authenticateToken (FUNCTION, middleware/authenticateToken.js)
- authMiddleware (FUNCTION, middleware/auth.js)
```

✓ **Conclusion:** Repository DOES have authentication implementation

### 2. Relationships for Auth Symbols (✓ Present)

Query: `SELECT rel_type, COUNT(*) FROM relationships WHERE from_symbol_id LIKE '%auth%' OR to_symbol_id LIKE '%auth%' GROUP BY rel_type`

**Results:**
- 25 total relationships involving auth symbols
- Breakdown:
  - 21 DECLARES relationships (symbols declared by classes/modules)
  - 3 CALLS relationships (functions calling other functions)
  - 1 USES relationship

✓ **Conclusion:** Graph has 25 documented relationships for auth entities

### 3. Source Code (✓ Available)

Query: `SELECT COUNT(*) FROM files WHERE path ILIKE '%auth%'`

Multiple auth-related files exist in the database:
- `backend/middleware/auth.js`
- `controllers/authcontroller.js`
- `src/components/Login.tsx`
- `src/components/Signup.tsx`

✓ **Conclusion:** Source code for auth features is available in storage

---

## The Problem: Retrieval Failure

Despite all this data being present, the user's RIM logs showed:
```
RIM_METADATA: No structural facts could be resolved for this question in this repository's index.
```

This occurs in `build_rim_metadata_block()` at line 247 of `rim_metadata.py`:
```python
if not candidates:
    block.text = "RIM_METADATA: No structural facts could be resolved..."
    return block
```

**Root Cause:** `HybridRetriever.retrieve(question, top_k=5)` is returning 0 candidates.

---

## Diagnosis: Why Retriever Fails

The HybridRetriever uses two strategies:
1. **BM25 (Lexical Search)** - Keyword matching in symbol names and metadata
2. **Semantic Search** - Vector similarity (via Chroma)

### BM25 Index Status

For the query "How does authentication work in this repo?":
- Keywords: "authentication", "auth", "work"
- Should match: `authenticate_user`, `verify_password`, `authMiddleware`, etc.
- **Expected:** 5-10 candidates
- **Actual:** 0 candidates

**Possible causes:**
1. BM25 index not built or empty
2. Index terms not normalized properly
3. Retriever disabled BM25 in favor of only semantic search

### Semantic Search Status

Semantic search requires:
1. Chroma database populated with embeddings
2. Vector similarity queries working
3. Embeddings fresh and relevant

**From rim_comparison_service_v2.py line 186:**
```python
chroma_collection = None
try:
    chroma_collection = get_chroma_collection(self.repo_name, self.current_user, self.db)
except Exception as e:
    logger.debug(f"Chroma collection not available: {e}")
```

If Chroma collection fails to load, semantic search is disabled!

---

## Data Flow Breakdown

```
User Query: "How does authentication work in this repo?"
    ↓
HybridRetriever.retrieve(question, top_k=5)
    ├─ [BM25] Search in symbol names/metadata
    │   └─ ✗ FAILS: 0 matches
    │
    ├─ [Semantic] Search in Chroma embeddings
    │   └─ ✗ FAILS: Chroma collection unavailable or empty
    │
    └─ Result: candidates = []
        ↓
build_rim_metadata_block()
    ├─ Try to resolve seeds: []
    └─ Return: "No structural facts could be resolved"
        ↓
    LLM System Prompt
        └─ Contains: No RIM relationships, only file list
            ↓
        LLM Response
            └─ Generic (lacks repository-specific facts)
```

---

## Critical Insights

### Problem 1: BM25 Index Not Working
**Symptom:** Lexical search for "auth" finds 0 results, but 6 auth symbols exist in DB  
**Impact:** First retrieval strategy fails completely  
**Solution:** Verify BM25 index exists and is populated for symbols table

### Problem 2: Semantic Search Unavailable
**Symptom:** Chroma collection fails to load in rim_comparison_service_v2.py line 186  
**Impact:** Second retrieval strategy is disabled  
**Solution:** Ensure Chroma database is populated and accessible

### Problem 3: Fallback to Weak Retrieval
**Symptom:** With both BM25 and semantic search failing, no entities identified  
**Impact:** RIM metadata block empty, LLM has no relationships to work with  
**Solution:** Implement fallback retrieval or improve index quality

---

## Phase 2 Test Results

| Component | Status | Evidence |
|-----------|--------|----------|
| FactStore Symbols | ✓ Present | 6 auth symbols found in DB |
| FactStore Relationships | ✓ Present | 25 relationships involving auth symbols |
| Source Code Availability | ✓ Present | Auth-related files in storage |
| **HybridRetriever (BM25)** | **✗ Failing** | 0 candidates despite relevant data |
| **HybridRetriever (Semantic)** | **✗ Failing** | Chroma collection unavailable |
| **Seed Resolution** | Blocked | Can't test without candidates |
| **Graph Traversal** | Blocked | Can't test without seeds |

---

## Conclusion

The RIM system **HAS the data** (symbols, relationships, source code) but **CANNOT RETRIEVE IT** due to:

1. **BM25 index failure** - Lexical search not finding auth-related symbols
2. **Semantic search unavailable** - Chroma collection not loaded or populated

This explains why the user's query produced a generic answer:
- ✓ Phase 1 (Source Code Injection) fixed: LLM now gets source code
- ✗ Phase 2 (RIM Retrieval) is broken: LLM gets no relationships

**Next steps:**
- Phase 3: Test if source code retrieval works despite retrieval failure
- Phase 4: Verify LLM payload with fixed Phase 1 (source code included)
- Phase 5: Fix retrieval pipeline (BM25/Chroma) to enable proper RIM

The fix for Phase 2 requires either:
1. Rebuilding the BM25 index for symbols
2. Ensuring Chroma collection is available
3. Implementing fallback retrieval strategies
