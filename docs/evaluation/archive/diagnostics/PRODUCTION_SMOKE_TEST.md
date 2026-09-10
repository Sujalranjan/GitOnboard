# Production Smoke Test Procedure

**Date:** 2026-09-02  
**Purpose:** Verify semantic retrieval pipeline in production environment with real repositories  
**Scope:** End-to-end verification from repository analysis through semantic query execution

---

## Prerequisites

### Infrastructure Requirements
- [ ] Production analyzer/worker service running
- [ ] PostgreSQL database (or target database) accessible
- [ ] Chromadb available and installed
- [ ] HybridRetriever code deployed
- [ ] RIM metadata building code deployed

### Repository Selection
- [ ] 3-5 diverse real repositories identified
- [ ] Mix of languages (Python, Node, Go, etc.)
- [ ] Different domain contexts (web, API, microservice, etc.)
- [ ] Various relationship complexity levels

### Access & Permissions
- [ ] Access to production database
- [ ] Ability to run analyzer on selected repositories
- [ ] Ability to query production API endpoints
- [ ] Read access to application logs

---

## Part 1: Analyzer Execution

### 1.1 Run Analyzer on First Repository

**Procedure:**
```bash
# Run analyzer on target repository
python -m backend.services.worker --repo-url "https://github.com/org/repo1" --analysis-id 1

# Monitor logs for completion
tail -f logs/analyzer.log | grep "analysis_id 1"
```

**Success Criteria:**
- ✅ Process exits with status 0
- ✅ Logs show: "Job ... completed successfully"
- ✅ Analysis.status = "Completed" in database

**Capture:**
- Analysis ID
- Entity count
- Relationship count
- Analysis duration (seconds)

### 1.2 Verify RIM Model Created

**Database Check:**
```sql
SELECT id, status, created_at FROM analysis WHERE id = 1;
SELECT COUNT(*) FROM fact_symbol WHERE analysis_id = 1;
SELECT COUNT(*) FROM fact_relationship WHERE analysis_id = 1;
```

**Success Criteria:**
- ✅ Analysis.status = "Completed"
- ✅ fact_symbol count ≥ 50 (realistic repository)
- ✅ fact_relationship count ≥ 20

---

## Part 2: Semantic Index Verification

### 2.1 Verify SemanticIndexBuilder Ran

**Database Check:**
```sql
SELECT id, type, LENGTH(blob_data) as size_bytes, created_at 
FROM analysis_artifact 
WHERE analysis_id = 1 AND type = 'semantic_index_db';
```

**Success Criteria:**
- ✅ Artifact row exists
- ✅ type = 'semantic_index_db'
- ✅ blob_data is NOT NULL
- ✅ size_bytes > 10000 (realistic index size)

**Capture:**
- Artifact ID
- Artifact size (bytes)
- Creation timestamp
- Status: EXISTS or MISSING

### 2.2 Verify Artifact Persistence

**Procedure:**
```python
# Read artifact back from database
artifact = session.query(AnalysisArtifact).filter(
    AnalysisArtifact.analysis_id == 1,
    AnalysisArtifact.type == 'semantic_index_db'
).first()

assert artifact is not None
assert artifact.blob_data is not None
assert len(artifact.blob_data) > 10000
print(f"✅ Artifact persisted: {len(artifact.blob_data)} bytes")
```

**Success Criteria:**
- ✅ Artifact retrieved successfully
- ✅ blob_data can be read
- ✅ Size matches what was written

**Capture:**
- Artifact retrievable: YES/NO
- blob_data checksum (for verification)

---

## Part 3: Retriever Artifact Loading

### 3.1 Start/Restart Worker or Retriever Service

**Procedure:**
```bash
# Restart retriever/worker service
systemctl restart rim-worker

# Wait for service to fully initialize
sleep 5

# Check logs for initialization
tail -f logs/retriever.log | grep "semantic_index"
```

**Success Criteria:**
- ✅ Service starts successfully
- ✅ No errors in semantic loading
- ✅ Logs show artifact loading attempts

### 3.2 Verify Artifact Loads in HybridRetriever

**Instrumentation (add temporary logging):**
```python
# In HybridRetriever._load_semantic_index_from_artifact()
logger.info(f"[SMOKE_TEST] Loading semantic for analysis {self.analysis_id}")
logger.info(f"[SMOKE_TEST] Artifact found: {artifact is not None}")
logger.info(f"[SMOKE_TEST] chroma_collection initialized: {self.chroma_collection is not None}")
logger.info(f"[SMOKE_TEST] semantic_degradation: {self.semantic_degradation}")
```

**Log Verification:**
```bash
grep "SMOKE_TEST" logs/retriever.log
```

**Success Criteria:**
- ✅ Log shows "Artifact found: True"
- ✅ Log shows "chroma_collection initialized: True"
- ✅ Log shows "semantic_degradation: None"

**Capture:**
- Artifact loading: SUCCESS / FAILURE
- Error message (if failed)

---

## Part 4: Semantic Query Execution

### 4.1 Test Natural-Language Query (Code Vocabulary Overlap)

**Query:** (Choose appropriate to repository type)
- Python repo: "How are users authenticated?"
- Node repo: "How is access controlled?"
- Go repo: "How are permissions verified?"

**Procedure:**
```bash
# Query via API or direct
curl -X POST http://localhost:8000/api/rim/query \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_id": 1,
    "query": "How are users authenticated?"
  }' | jq .
```

**Response Structure:**
```json
{
  "query": "How are users authenticated?",
  "retrieval_method": "semantic",  // or "lexical", "fallback"
  "results": [
    {
      "entity_name": "...",
      "entity_type": "SYMBOL",
      "score_type": "semantic",  // or "lexical"
      "score": 0.85
    }
  ],
  "rim_metadata": "..."
}
```

**Success Criteria:**
- ✅ HTTP 200
- ✅ "results" array non-empty
- ✅ At least one result with score_type="semantic" OR results via RRF fusion
- ✅ Retrieved entities match repository context

**Capture:**
- Query: [exact text]
- Results count
- Retrieval method: semantic / lexical / fallback
- Top entity names
- HTTP status

### 4.2 Test Vocabulary-Gap Query (Semantic Necessary)

**Query:** (Choose vocabulary NOT present in code)

Examples:
- **For auth code:** "How do people prove who they are?" (instead of "verify_identity", "authenticate", etc.)
- **For web framework:** "How does an incoming request get processed?" (instead of "middleware", "handler", etc.)
- **For DB code:** "How do we persist data?" (instead of "save", "insert", "store", etc.)

**Procedure:**
```bash
curl -X POST http://localhost:8000/api/rim/query \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_id": 1,
    "query": "How do people prove who they are?"
  }' | jq .
```

**Success Criteria:**
- ✅ HTTP 200
- ✅ "results" array non-empty (semantic recovers vocabulary gap)
- ✅ At least one result with score_type="semantic"
- ✅ Retrieved entities are semantically relevant (not random)

**Failure Criteria (Expected with Lexical Only):**
- ❌ Empty results array
- ✗ Only "fallback" results with low relevance

**Capture:**
- Query: [exact text]
- Results with semantic scoring
- Score values (should be > 0.5 for relevant)
- Comparison: semantic vs lexical results

### 4.3 Test Unrelated Query (Negative Test)

**Query:** "What's the fastest sorting algorithm?"

**Success Criteria:**
- ✅ Either returns 0 results OR
- ✅ Returns results clearly marked as low-confidence
- ✅ Does NOT return false positives from unrelated code

**Capture:**
- Query returns: EMPTY / LOW-CONFIDENCE / FALSE-POSITIVE
- Result count

---

## Part 5: RIM Metadata Verification

### 5.1 Verify Semantic Results Build RIM Metadata

**Procedure:**
```python
# Use same queries from Part 4
retriever = HybridRetriever(db, analysis_id=1)
results = retriever.retrieve("How are users authenticated?")

metadata = build_rim_metadata_block(
    db,
    analysis_id=1,
    query="How are users authenticated?",
    retriever=retriever,
    max_seed_entities=5
)

assert metadata.text is not None
assert "No structural facts" not in metadata.text
assert len(metadata.relationships) > 0
```

**Success Criteria:**
- ✅ metadata.text non-empty
- ✅ Does NOT contain "No structural facts"
- ✅ metadata.relationships populated
- ✅ metadata.seed_entities populated

**Verification:** Read metadata.text and verify it contains:
- Repository-specific facts
- Entity names from actual codebase
- Relationships between entities
- Relevant to query

**Capture:**
- Metadata length (characters)
- Seed entity count
- Relationship count
- Metadata quality: FULL / PARTIAL / EMPTY

### 5.2 Verify Graph Expansion from Semantic Seeds

**Procedure:**
```python
# Inspect metadata structure
print(f"Seeds: {len(metadata.seed_entities)}")
print(f"Relationships: {len(metadata.relationships)}")

for rel in metadata.relationships[:3]:
    print(f"  {rel.from_entity} → {rel.to_entity}: {rel.rel_type}")
```

**Success Criteria:**
- ✅ Seeds extracted from semantic results
- ✅ Graph traversal found relationships
- ✅ Relationship types are valid (CALLS, USES, DEFINES, etc.)

**Capture:**
- Relationships by type (count)
- Expansion depth
- Total entities in metadata

---

## Part 6: Performance Verification

### 6.1 Measure Semantic Indexing Time

**Capture from logs:**
```bash
grep "Semantic index built" logs/analyzer.log
# Expected: ~5-15 seconds depending on repository size
```

**Capture:**
- Semantic build time (seconds)
- Repository entity count
- Time per entity (build_time / entity_count)

### 6.2 Measure Semantic Query Time

**Procedure:**
```python
import time

start = time.time()
results = retriever.retrieve("How are users authenticated?")
query_time = time.time() - start

print(f"Query time: {query_time*1000:.1f}ms")
# Expected: <100ms for semantic query
```

**Success Criteria:**
- ✅ Semantic query latency < 100ms (typically 20-50ms)
- ✅ No performance degradation vs lexical

**Capture:**
- Query latency (milliseconds)
- Result count
- Semantic cost vs fallback cost

### 6.3 Compare Before/After Semantic

**Metrics:**
- Queries that succeed: WITHOUT vs WITH semantic
- Average latency: WITHOUT vs WITH semantic
- Vocabulary-gap recovery rate

---

## Part 7: Repeat for Additional Repositories

**Repeat Parts 1-6 for:**
- [ ] Repository 2
- [ ] Repository 3
- [ ] Repository 4 (if applicable)
- [ ] Repository 5 (if applicable)

**For each, complete:**
- [ ] Analyzer execution ✓
- [ ] Artifact creation ✓
- [ ] Artifact persistence ✓
- [ ] Artifact loading ✓
- [ ] Semantic queries execute ✓
- [ ] Vocabulary-gap recovery ✓
- [ ] RIM metadata built ✓
- [ ] Graph expansion ✓

---

## Failure Conditions & Rollback

### Blocker Issues (STOP, Investigate)

**If semantic artifact NOT created:**
1. Check SemanticIndexBuilder logs
2. Verify chromadb installed
3. Check entity count (need > 10 for meaningful index)
4. Verify sufficient disk space
5. **Recommendation:** DO NOT DEPLOY

**If semantic artifact NOT loaded:**
1. Check AnalysisArtifact table for artifact existence
2. Verify HybridRetriever initialization logs
3. Check for chromadb errors
4. Verify blob_data integrity
5. **Recommendation:** DO NOT DEPLOY

**If semantic queries return 0 results:**
1. Verify artifact loaded (check retriever logs)
2. Test Chroma directly with sample query
3. Check semantic entity text (may be too sparse)
4. **Recommendation:** Acceptable if fallback works

### Acceptable Issues (MONITOR)

**Performance degradation:**
- Semantic indexing adds 5-15s per analysis (acceptable)
- Semantic queries add 20-50ms (acceptable)

**Vocabulary gaps:**
- Some queries fail due to semantic limitations (expected)
- Fallback still provides results (acceptable)

---

## Rollback Criteria

**Rollback immediately if:**
- ❌ Semantic artifacts corrupt or unreadable
- ❌ Semantic queries crash or hang
- ❌ Retriever service crash on artifact load
- ❌ RIM metadata building fails
- ❌ Latency increases > 50% vs baseline

**Do NOT rollback if:**
- ✓ Semantic index creation takes longer than expected
- ✓ Some queries fail due to vocabulary gaps
- ✓ Fallback compensates for failures

---

## Sign-Off Checklist

**Before declaring production ready:**

- [ ] ≥3 repositories tested successfully
- [ ] Semantic artifacts created on 100% of analyses
- [ ] Artifacts persist and load correctly
- [ ] Semantic queries execute and return results
- [ ] Vocabulary-gap queries show semantic recovery
- [ ] RIM metadata contains repository-specific facts
- [ ] Graph expansion occurs on semantic seeds
- [ ] No blocker failures encountered
- [ ] Performance within acceptable range
- [ ] Logs show no errors or warnings

**Sign-off by:** [Engineer Name]  
**Date:** [YYYY-MM-DD]  
**Status:** ☐ PASS ☐ PARTIAL ☐ FAIL

---

## Summary

This procedure verifies the complete semantic retrieval pipeline in production:

1. **Analyzer phase:** Semantic index built
2. **Storage phase:** Artifact persisted
3. **Loading phase:** HybridRetriever loads artifact
4. **Query phase:** Semantic queries execute
5. **Integration phase:** RIM metadata built from semantic results
6. **Expansion phase:** Graph expansion from semantic seeds

**Expected outcome:** 100% of tests pass with semantic retrieval working end-to-end.

**Known limitations:** Vocabulary gaps may still cause some queries to fail, but semantic recovery should show measurable improvement over lexical-only.
