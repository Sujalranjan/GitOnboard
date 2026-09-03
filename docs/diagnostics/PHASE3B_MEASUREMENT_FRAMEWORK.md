# Phase 3B: Clean Repository Indexing Measurement Framework

## Objective

Capture hard numbers for a clean, end-to-end repository analysis without any architectural changes.

## Test Repository Selection

**Repository**: Current working directory (Repository Intelligence Platform)
**Characteristics**:
- Python backend + TypeScript frontend
- Contains: functions, classes, imports, relationships
- Contains: authentication/login patterns (target domain)
- Medium complexity for realistic measurement
- Already used in Phase 1 & 2 (comparable baseline)

## Measurement Checkpoint: Repository Analysis

### Capture Points

Before analysis starts, record:

```
ANALYSIS_START_TIMESTAMP: <time>
REPOSITORY_PATH: /home/dheeraj/repository_intelligence_platform
REPOSITORY_LANGUAGE: Python, TypeScript
```

During analysis pipeline:

1. **File Discovery**
   ```
   Total files found: X
   Python files: X
   TypeScript files: X
   JavaScript files: X
   Other: X
   ```

2. **Symbol Extraction** (from logs)
   ```
   Functions extracted: X
   Classes extracted: X
   Methods extracted: X
   Variables extracted: X
   Other symbols: X
   Total symbols: X
   ```

3. **Relationships**
   ```
   CALLS relationships: X
   IMPORTS relationships: X
   CONTAINS relationships: X
   INHERITS relationships: X
   Other relationships: X
   Total relationships: X
   ```

4. **FactStore Entities**
   ```
   FactFile records: X
   FactSymbol records: X
   FactRelationship records: X
   FactRoute records: X
   FactDatabaseObject records: X
   FactCapability records: X
   ```

**Extraction Point**: Query database after analysis completes but before retrieval/indexing

```sql
SELECT analysis_id, COUNT(*) FROM files 
WHERE analysis_id = ? GROUP BY analysis_id;

SELECT symbol_type, COUNT(*) FROM symbols 
WHERE analysis_id = ? GROUP BY symbol_type;

SELECT rel_type, COUNT(*) FROM relationships 
WHERE analysis_id = ? GROUP BY rel_type;

SELECT COUNT(*) FROM symbols WHERE analysis_id = ?;
-- Compare to retrieval document count
```

## Measurement Checkpoint: BM25 Indexing

### Capture Points

**Entry Point**: Before `_build_lexical_index()` or artifact load

```python
# Add to HybridRetriever.__init__()
logger.info(f"[BM25 BUILD START] analysis_id={self.analysis_id}")

# In _build_lexical_index()
logger.info(f"[BM25 ENTITY COUNT] files={len(files)} symbols={len(symbols)} routes={len(routes)} db_objs={len(db_objs)} caps={len(caps)}")

# After docs collection
logger.info(f"[BM25 DOCUMENTS] total={len(docs)}")

# After indexing
logger.info(f"[BM25 INDEX BUILT] corpus_size={self.bm25_index.corpus_size} avg_len={self.bm25_index.avg_doc_len}")
```

**Expected Output**:
```
[BM25 BUILD START] analysis_id=123
[BM25 ENTITY COUNT] files=87 symbols=482 routes=23 db_objs=12 caps=8
[BM25 DOCUMENTS] total=612
[BM25 INDEX BUILT] corpus_size=612 avg_len=4.2
```

**Manual Inspection**:
```python
# After HybridRetriever init
if hasattr(retriever, 'bm25_index') and retriever.bm25_index:
    print(f"BM25 corpus_size: {retriever.bm25_index.corpus_size}")
    print(f"BM25 document count: {len(retriever.bm25_index.documents)}")
    print(f"BM25 avg_doc_len: {retriever.bm25_index.avg_doc_len}")
    
    # Categorize documents
    doc_types = {}
    for doc in retriever.bm25_index.documents:
        doc_type = doc.get('match_type', 'unknown')
        doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
    print(f"BM25 by type: {doc_types}")
```

**Extraction**: Print actual counts and breakdown

## Measurement Checkpoint: Chroma/Semantic Indexing

### Capture Points

**Entry Point**: In `SemanticIndexBuilder.build_index()`

```python
# Add logging
logger.info(f"[CHROMA BUILD START] entities_count={len(model_entities)}")

# After document preparation
logger.info(f"[CHROMA DOCS] prepared={len(documents)} after_filter")

# After embedding
logger.info(f"[CHROMA EMBEDDED] count={len(documents)}")

# After serialization
logger.info(f"[CHROMA SERIALIZED] size={len(result)} bytes")
```

**Expected Output**:
```
[CHROMA BUILD START] entities_count=612
[CHROMA DOCS] prepared=612 after_filter
[CHROMA EMBEDDED] count=612
[CHROMA SERIALIZED] size=8457392 bytes
```

**Manual Inspection** (after retriever init):
```python
if hasattr(retriever, 'chroma_collection') and retriever.chroma_collection:
    try:
        count = retriever.chroma_collection.count()
        print(f"Chroma document count: {count}")
    except Exception as e:
        print(f"Chroma count failed: {e}")
else:
    print(f"Chroma unavailable: {retriever.semantic_degradation}")
```

**Extraction**: Print actual counts and degradation reason if applicable

## Measurement Checkpoint: Indexing Counts Comparison

### Create Table

```
Layer                    Count    Status
─────────────────────────────────────────
Files analyzed           87       ✓
Symbols extracted        482      ✓
Relationships            921      ✓
FactStore facts          612      ✓
BM25 documents           612      ✓
Chroma documents         612      ✓
Embeddings generated     612      ✓
Analysis complete        YES      ✓
```

**Analysis**:
- Files analyzed = FactFile count ✓
- Symbols extracted = FactSymbol count ✓
- Relationships = FactRelationship count ✓
- BM25 docs = files + symbols + routes + db_objs + caps = 87 + 482 + 23 + 12 + 8 = 612 ✓
- Chroma docs = all entities = 612 ✓

## Measurement Checkpoint: Retrieval Path Testing

### Test 1: Exact Fact Search

```python
from backend.intelligence.retrieval.retriever import HybridRetriever

retriever = HybridRetriever(db=session, analysis_id=analysis_id)

# Direct exact search
exact_results = retriever._search_exact_facts("login")

print(f"Exact search 'login': {len(exact_results)} results")
for i, result in enumerate(exact_results[:3], 1):
    print(f"  {i}. {result.get('name')} ({result.get('type')}) @ {result.get('file_path')}")
    print(f"     ID: {result.get('symbol_id')}")
    print(f"     Lines: {result.get('line_start')}-{result.get('line_end')}")
```

**Expected Capture**:
```
Exact search 'login': 3 results
  1. login (function) @ src/auth.py
     ID: <symbol_id>
     Lines: 2-8
  2. handleLogin (function) @ src/handlers.js
     ID: <symbol_id>
     Lines: 12-28
  3. login (method) @ src/middleware/auth.js
     ID: <symbol_id>
     Lines: 4-19
```

### Test 2: BM25 Lexical Search

```python
# Direct BM25 search
bm25_results = retriever.bm25_index.search("login", top_k=10) if retriever.bm25_index else []

print(f"BM25 search 'login': {len(bm25_results)} results")
for i, (doc_id, score) in enumerate(bm25_results[:3], 1):
    # Find doc in index
    doc = next((d for d in retriever.bm25_index.documents if d['id'] == doc_id), None)
    if doc:
        print(f"  {i}. {doc.get('name')} ({doc.get('type')}) @ {doc.get('file_path')}")
        print(f"     Score: {score:.3f}")
```

**Expected Capture**:
```
BM25 search 'login': 8 results
  1. login (function) @ src/auth.py
     Score: 0.847
  2. handleLogin (function) @ src/handlers.js
     Score: 0.821
  3. login (method) @ src/middleware/auth.js
     Score: 0.756
```

### Test 3: Semantic Search (Chroma)

```python
# Direct semantic search
if retriever.chroma_collection:
    semantic_results = retriever.chroma_collection.query(
        query_texts=["login"],
        n_results=10,
        include=["metadatas", "distances"]
    )
    
    print(f"Semantic search 'login': {len(semantic_results['ids'][0])} results")
    for i, (doc_id, distance, metadata) in enumerate(
        zip(semantic_results['ids'][0][:3], 
            semantic_results['distances'][0][:3],
            semantic_results['metadatas'][0][:3]), 1):
        print(f"  {i}. {metadata.get('entity_name')} ({metadata.get('entity_type')})")
        print(f"     File: {metadata.get('file_path')}")
        print(f"     Distance: {distance:.3f}")
else:
    print(f"Semantic search unavailable: {retriever.semantic_degradation}")
```

**Expected Capture**:
```
Semantic search 'login': 7 results
  1. login (FUNCTION)
     File: src/auth.py
     Distance: 0.142
  2. handleLogin (FUNCTION)
     File: src/handlers.js
     Distance: 0.163
  3. login (METHOD)
     File: src/middleware/auth.js
     Distance: 0.187
```

## Measurement Checkpoint: Source Traceability

### Trace Each Top Result

```python
# For each semantic result
for result in semantic_results[:3]:
    entity_id = result['id']
    file_path = result['metadata']['file_path']
    
    # Step 1: Look up in FactStore
    from backend.models.fact_store import FactSymbol, FactFile
    
    # Try symbol lookup
    symbol = db.query(FactSymbol).filter(FactSymbol.id == entity_id).first()
    if symbol:
        print(f"✓ Symbol {entity_id} found in FactStore")
        print(f"  Name: {symbol.name}")
        print(f"  File: {symbol.file.path if symbol.file else file_path}")
        
        # Step 2: Try to read source
        from backend.repository_tools.tools import RepositoryToolLayer
        tool_layer = RepositoryToolLayer(repo_name=..., repo_root=...)
        try:
            content = tool_layer.read_file(symbol.file.path, symbol.line_start, symbol.line_end)
            print(f"✓ Source readable: {len(content.get('content', ''))} chars")
        except Exception as e:
            print(f"✗ Source unreadable: {e}")
    else:
        print(f"✗ Entity {entity_id} NOT found in FactStore")
```

**Expected Capture**:
```
✓ Symbol <id1> found in FactStore
  Name: login
  File: src/auth.py
✓ Source readable: 423 chars

✓ Symbol <id2> found in FactStore
  Name: handleLogin
  File: src/handlers.js
✓ Source readable: 387 chars

✗ Entity <id3> NOT found in FactStore
```

## Measurement Checkpoint: Repository Isolation

### Test Cross-Repository Query

```python
# Assume analysis_ids 1 and 2 exist for different repositories

retriever_1 = HybridRetriever(db=session, analysis_id=1)
retriever_2 = HybridRetriever(db=session, analysis_id=2)

# Search in retriever_1
exact_1 = retriever_1._search_exact_facts("login")

# Check that no result has analysis_id=2
analysis_ids_in_result = set()
for result in exact_1:
    # Retrieve full entity
    symbol = db.query(FactSymbol).filter(FactSymbol.id == result['symbol_id']).first()
    if symbol:
        analysis_ids_in_result.add(symbol.analysis_id)

print(f"Analysis IDs in results: {analysis_ids_in_result}")
assert analysis_ids_in_result == {1}, "Repository isolation violated!"
```

**Expected Capture**:
```
Analysis IDs in results: {1}
✓ Repository isolation verified
```

## Measurement Checkpoint: Silent Failure Detection

### Test Chromadb Degradation Path

```python
# Monitor what happens when semantic_degradation is set

if hasattr(retriever, 'semantic_degradation') and retriever.semantic_degradation:
    print(f"⚠️ Semantic indexing degraded: {retriever.semantic_degradation}")
    
    # Check what retriever still supports
    print(f"BM25 available: {retriever.bm25_index is not None}")
    print(f"Exact search available: {retriever.db is not None}")
    print(f"Chroma available: {retriever.chroma_collection is not None}")
    
    # Does analysis still report complete?
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    print(f"Analysis status: {analysis.status}")
else:
    print(f"✓ Semantic indexing available")
```

**Expected Capture** (if no degradation):
```
✓ Semantic indexing available
```

**Expected Capture** (if degradation):
```
⚠️ Semantic indexing degraded: chromadb_unavailable
BM25 available: True
Exact search available: True
Chroma available: False
Analysis status: completed
```

## Measurement Checkpoint: Stale Index Detection

### Verify BM25 Artifact Dependency

```python
# Check if FactStore changes invalidate BM25

# Step 1: Get current BM25 document count
bm25_count_before = retriever.bm25_index.corpus_size

# Step 2: Add a new symbol to FactStore (manually via db)
new_symbol = FactSymbol(
    id=f"test-{uuid.uuid4()}",
    analysis_id=analysis_id,
    name="new_test_function",
    qualified_name="test.new_test_function",
    symbol_type="function"
)
db.add(new_symbol)
db.commit()

# Step 3: Check if BM25 reflects the change
# Create a new retriever (simulating fresh load)
retriever_new = HybridRetriever(db=session, analysis_id=analysis_id)
bm25_count_after = retriever_new.bm25_index.corpus_size

# Step 4: Compare
if bm25_count_after > bm25_count_before:
    print(f"✓ BM25 updated automatically ({bm25_count_before} → {bm25_count_after})")
else:
    print(f"✗ BM25 is stale (still {bm25_count_before}, expected {bm25_count_after})")
    print(f"  RISK: FactStore changes not reflected in BM25")

# Cleanup
db.delete(new_symbol)
db.commit()
```

**Expected Capture**:
```
✗ BM25 is stale (still 612, expected 613)
  RISK: FactStore changes not reflected in BM25
```

## Execution Checklist

- [ ] Identify analysis_id for clean repository
- [ ] Capture repository metadata
- [ ] Query FactStore counts
- [ ] Measure BM25 indexing
- [ ] Measure Chroma indexing
- [ ] Test exact search
- [ ] Test BM25 search
- [ ] Test semantic search
- [ ] Trace top 3 results to source
- [ ] Test repository isolation
- [ ] Monitor degradation modes
- [ ] Test stale index scenario
- [ ] Compile measurements into table
- [ ] Answer key questions

## Output Template

Once all measurements collected, populate:

```
# Phase 3B Report: Clean Repository Indexing Measurement

## Repository
- ID: ?
- Path: ?
- Languages: ?

## Counts
| Layer | Count | Status |
|-------|-------|--------|
| Files | ? | |
| Symbols | ? | |
| Relationships | ? | |
| FactStore | ? | |
| BM25 | ? | |
| Chroma | ? | |

## Retrieval Tests
### Exact: query="login"
- Results: ?
- Top 3: [...]
- Traceability: ✓/✗

### BM25: query="login"
- Results: ?
- Top 3: [...]
- Traceability: ✓/✗

### Semantic: query="login"
- Results: ?
- Top 3: [...]
- Traceability: ✓/✗

## Critical Findings
- Analysis complete guarantees semantic indexing: YES/NO
- BM25 stale risk: YES/NO
- Silent failures possible: YES/NO
- Repository isolation verified: YES/NO

## Overall Status
HEALTHY / HEALTHY_WITH_GAPS / DEGRADED / BROKEN
```

## Key Rules

✓ Measure only, do not fix
✓ Use actual numbers from running system
✓ Trace every retrieval result to source
✓ Test all three retrieval paths
✓ Report degradation modes explicitly
✓ Answer yes/no questions definitively

❌ Do not add new schema fields
❌ Do not implement fixes
❌ Do not change architecture
❌ Do not add permanent logging (temporary for measurement only)
