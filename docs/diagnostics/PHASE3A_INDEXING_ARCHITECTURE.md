# Phase 3A: Semantic Retrieval Architecture Diagnosis

## Complete Indexing Pipeline

```
Repository Analysis Complete
    ↓
RepositoryModel created (entities + relationships)
    ↓
Analysis saved to database
    ↓
[PARALLEL] Three indexing paths:
    ├─ Path 1: Lexical/BM25 Index Building
    ├─ Path 2: Semantic/Chroma Index Building
    └─ Path 3: FactStore persistence
    ↓
Indexes saved to AnalysisArtifact
    ↓
Ready for retrieval
```

---

## Path 1: Lexical/BM25 Index

**File**: `backend/intelligence/retrieval/retriever.py:63-216`  
**Class**: `HybridRetriever._load_or_build_lexical_index()` + `_build_lexical_index()`

### Building Process

1. **Try to load pre-built index** (line 63-95)
   - Query for AnalysisArtifact with type="bm25_index"
   - If found, deserialize and load (avoids rebuilding)
   - If not found or error, fall back to build

2. **Build BM25 index from FactStore** (line 97-216)
   - Source 1: FactFile entities (line 105-119)
   - Source 2: FactSymbol entities (line 122-143)
   - Source 3: FactRoute entities (line 146-171)
   - Source 4: FactDatabaseObject entities (line 174-198)
   - Source 5: FactCapability entities (line 201-213)

### Indexed Document Structure

For each entity type:

```python
{
    "id": str,                    # Unique ID (fact_id)
    "name": str,                  # Display name
    "qualified_name": str,        # Qualified name
    "type": str,                  # Entity type (file, function, class, route, etc.)
    "file_path": str,             # File location
    "search_text": str,           # Tokenizable searchable text
    "line_start": int,            # Line number
    "line_end": int,              # Line number
    "match_type": str,            # Type of match
    "match_name": str,            # Name for display
    "symbol_id": str,             # Symbol ID (for symbols only)
}
```

### Example Search Text Construction

**File** (line 107):
```python
search_text = f"file path {f.path} {f.language or ''} {f.content_type or ''}"
```

**Symbol** (line 130):
```python
search_text = f"{sym.name} {sym.qualified_name or ''} {sym.symbol_type} {fpath} {signature} {docstring}"
```

**Route** (line 158):
```python
search_text = f"route {r.method} {r.path} {fpath}"
```

### Tokenization

Uses `CodeTokenizer` (from `backend/intelligence/retrieval/lexical.py`)
- Designed for code-specific tokenization
- Handles symbol names, file paths, keywords

### Storage

After building, index is converted to serializable format and stored in:

```
AnalysisArtifact
  analysis_id: int
  type: "bm25_index"
  data: JSON
    - documents: List[str]
    - idf: Dict[str, float]
    - doc_len: List[int]
    - corpus_size: int
    - avg_doc_len: float
```

---

## Path 2: Semantic/Chroma Index

**File**: `backend/intelligence/retrieval/semantic_builder.py`  
**Class**: `SemanticIndexBuilder`

### Building Process

1. **Check prerequisites** (line 36-40)
   - chromadb imported? (ImportError handling)
   - Entities to index? (line 42-44)

2. **Create Chroma collection** (line 47-63)
   - Temporary directory for persistence
   - Cosine similarity metric
   - Create collection "semantic_index"

3. **Prepare documents** (line 65-87)
   - Convert each entity to text (line 73)
   - Extract metadata (line 78)
   - Skip entities with no text (line 74-75)

4. **Generate embeddings** (line 94-98)
   - Chroma automatically embeds documents
   - Batches added to collection
   - No explicit embedding model specified here (uses Chroma default)

5. **Serialize to bytes** (line 100-114)
   - Compress entire Chroma directory to ZIP
   - Ready for storage as blob

### Document Processing

**Input**: Entity from RepositoryModel
```python
entity.type       # EntityType enum (FUNCTION, CLASS, FILE, etc.)
entity.name       # Symbol/file name
entity.qualified_name  # Full qualified name
entity.location.repository_path  # File path
entity.metadata   # Dict with docstring, signature, etc.
```

**Output for text**:
```
"function login src/auth.py auth.login() async def login(user, pass)"
```

**Output for metadata**:
```python
{
    "entity_type": "FUNCTION",
    "entity_name": "login",
    "file_path": "src/auth.py",
    "line_start": 2,
    "line_end": 8,
    "language": "Python"
}
```

### Storage

After building, ZIP archive is stored in:

```
AnalysisArtifact
  analysis_id: int
  type: "semantic_index_db"
  blob_data: bytes (ZIP archive)
```

---

## Path 3: Retrieval Time Index Loading

**File**: `backend/intelligence/retrieval/retriever.py:218-267`  
**Class**: `HybridRetriever._load_semantic_index_from_artifact()`

### Loading Process

1. **Check artifact exists** (line 225-238)
   - Query AnalysisArtifact type="semantic_index_db"
   - If missing: `self.semantic_degradation = "artifact_not_found"`
   - If empty: `self.semantic_degradation = "artifact_empty"`

2. **Extract and load** (line 240-259)
   - Create temp directory
   - Extract ZIP to temp directory
   - Load with `chromadb.PersistentClient()`
   - Get collection "semantic_index"

3. **Error handling** (line 256-267)
   - ImportError: `"chromadb_unavailable"`
   - Load error: `f"load_error: {error[:50]}"`
   - Artifact error: `f"artifact_load_error: {error[:50]}"`

### Degradation Modes

If semantic index unavailable:
- `self.semantic_degradation` tracks reason
- Hybrid retriever continues with lexical + exact only
- No semantic results in hybrid merge

---

## Exact Fact Search

**File**: `backend/intelligence/retrieval/retriever.py:269-XXX`  
**Method**: `_search_exact_facts(query)`

### Search Targets

1. **Exact symbol match** (line 279-295)
   - Query: `FactSymbol.name == query` (exact)
   - Fallback: `FactSymbol.name.ilike(f"%{query}%")` (substring)
   - Limit: 10 results

2. **Exact file match** (line 298+)
   - Query: `FactFile.path` matches
   - Returns files directly

3. **Exact route match**
   - Query: Route method/path combination
   - Returns route definitions

4. **Exact database object match**
   - Query: Database table/column names
   - Returns database entities

### Result Structure

```python
{
    "id": str,
    "symbol_id": str,
    "name": str,
    "match_name": str,
    "type": str,
    "match_type": str,
    "file_path": str,
    "line_start": int,
    "line_end": int,
    "score_type": "exact_fact"
}
```

---

## Hybrid Retrieval Composition

**Class**: `HybridRetriever`

### Components

```python
self.bm25_index         # Built/loaded lexical index
self.chroma_collection  # Loaded semantic Chroma collection
self.db                 # Database session for exact lookups
self.analysis_id        # Scopes all queries to one analysis
```

### Weights

```python
rrf_k = 60              # RRF parameter
lexical_weight = 1.0    # Weight for BM25 results
semantic_weight = 1.0   # Weight for semantic results
exact_weight = 1.2      # Weight for exact matches (highest priority)
```

### Fusion: Reciprocal Rank Fusion

From `backend/intelligence/retrieval/fusion.py`:

```
RRF(doc) = Σ( weight / (k + rank) )
```

where:
- k = rrf_k (60)
- rank = position in result list (1-indexed)
- weight = component weight

Final ranking: highest RRF score wins

---

## Index Status Tracking

**Current Implementation**: AnalysisArtifact

```
analysis
  ├─ artifacts
      ├─ type="bm25_index" → {documents, idf, ...}
      └─ type="semantic_index_db" → blob (ZIP)
```

**Problem**: No explicit "indexing_status"

Inferred status:
- If artifact exists → assumed indexed successfully
- If artifact missing → assumed not indexed
- If artifact empty → assumed failed (but reported as missing)
- If load error → graceful degradation, reported via `semantic_degradation`

**Gap**: Silent failures possible
- Artifact corrupt → load error → degradation
- But upstream just sees "missing artifact"
- Analysis completion doesn't require successful indexing

---

## Current Error Handling

### Silent Degradation Patterns

**Pattern 1**: Missing chromadb library
```python
except ImportError:
    logger.warning("chromadb not available")
    return None  # Silently skip semantic indexing
```

**Pattern 2**: Missing or corrupt artifact
```python
if not artifact:
    self.semantic_degradation = "artifact_not_found"
    return  # Continue with lexical only
```

**Pattern 3**: ZIP extraction failure
```python
except Exception as e:
    self.semantic_degradation = f"load_error: ..."
    # No explicit failure - just skip semantic
```

### Log Level Issues

- Errors logged as `.warning()` or `.debug()`
- No `.error()` for indexing failure
- Result: indexing failure not visible in error aggregation
- Retrieval degradation may not be detected

---

## Metadata Preservation

### Through BM25

Metadata stored in BM25 document:
```python
{
    "id": fact_id,
    "symbol_id": sym_id,  # Key to look up in FactStore
    "file_path": file_path,  # Can read_file from this
    "line_start": line,
    "line_end": line,
    "type": symbol_type,  # Can filter by type
}
```

**Traceability**: 
- BM25 result has symbol_id → can query FactSymbol
- FactSymbol has file_id → can read file
- FactSymbol has metadata → can access docstring, signature

### Through Chroma

Metadata stored in Chroma:
```python
{
    "entity_type": "FUNCTION",
    "entity_name": "login",
    "file_path": "src/auth.py",
    "line_start": 2,
    "line_end": 8,
    "language": "Python"
}
```

**Traceability**: 
- Chroma result ID maps to entity_id in RepositoryModel
- Entity metadata includes file_path
- Can look up FactFile by path to read content

### Through Exact Search

Direct FactStore access:
```python
{
    "symbol_id": fact_symbol_id,  # Direct reference
    "file_path": path,  # Direct file path
    "line_start": line,
    "line_end": line,
    "type": symbol_type  # Direct type
}
```

**Traceability**: Strongest - direct FactStore IDs

---

## Repository Isolation

### Query Scoping

All queries filtered by `analysis_id`:

**BM25**:
```python
# When building, only indexes entities for this analysis_id
symbols = self.db.query(FactSymbol).filter(
    FactSymbol.analysis_id == self.analysis_id
)
```

**Chroma**:
```python
# Loaded per analysis_id
artifact = self.db.query(AnalysisArtifact).filter(
    AnalysisArtifact.analysis_id == self.analysis_id
)
```

**Exact Search**:
```python
symbols = self.db.query(FactSymbol).filter(
    FactSymbol.analysis_id == self.analysis_id
)
```

### Verification

- Every index creation uses analysis_id
- Every artifact lookup uses analysis_id
- Chroma collections isolated per analysis (separate artifacts)

**Status**: ✓ Repository isolation enforced

---

## Known Limitations

1. **No explicit indexing status tracking**
   - Can't query "is repository indexed?"
   - Indexing failure not logged as error

2. **Chromadb optional**
   - If not installed, semantic search skipped
   - No warning to user that semantic search unavailable
   - Graceful degradation but silent

3. **BM25 cache stale risk**
   - If analysis updated but artifact not rebuilt, stale index used
   - No versioning/invalidation on FactStore changes

4. **Chroma load on retrieval**
   - Chroma collection loaded into memory at HybridRetriever init
   - Multiple queries cause multiple loads
   - No caching between requests

5. **No index size metrics**
   - Can't query "how many documents indexed?"
   - Can't verify index completeness

6. **Error classification**
   - semantic_degradation uses string codes
   - Not structured for querying/reporting
   - Hard to aggregate across analyses

---

## Summary

### Architecture: Sound

- Three independent indexing paths (lexical, semantic, exact)
- Hybrid retrieval with RRF merging
- Proper repository scoping
- Metadata preserved through all paths
- Graceful degradation when semantic unavailable

### Correctness: Good

- Lexical indexing: Complete coverage
- Semantic indexing: Complete coverage (when available)
- Exact search: Direct FactStore lookups
- Source traceability: Valid IDs in all paths

### Observability: Issues

- Silent degradation possible
- Indexing status not queryable
- Errors not propagated to analysis status
- No metrics on indexed document count

### Risk Areas

- If chromadb fails silently, user unaware
- If artifact corrupt, load fails silently
- If FactStore changed, BM25 cache stale
- No way to rebuild index on demand

---

## Questions for Phase 3B-3N

1. When analysis completes, does indexing always complete?
2. Can indexing fail silently?
3. What are actual indexed document counts?
4. Do semantic results accurately reflect real relationships?
5. Does BM25 find all relevant symbols for a query?
6. Are there stale index cases?
7. Can all retrieval results lead to actual source?
