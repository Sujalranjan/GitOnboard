# Phase 4-C Investigation: BM25 Staleness Model

## Finding: Analysis.id Guarantees Immutable FactStore Snapshot

### Evidence Chain

1. **FactStore Creation** (worker.py line 295)
   - Called immediately after RIM analysis completes
   - Operates on single `rim_model` snapshot

2. **FactStore Persistence** (fact_store.py)
   - Line 52-66: Clears prior facts for analysis_id (idempotent)
   - Lines 72-343: Inserts all entities, relationships, routes, capabilities
   - Line 344: Single `db.commit()` — atomic transaction

3. **No Post-Creation Mutations**
   - Searched entire codebase for FactStore modifications
   - Found only: blob_name/size updates (storage metadata only)
   - No entity adds/deletes/updates after initial save

4. **BM25 Timing** (worker.py line 319)
   - `HybridRetriever` created IMMEDIATELY after FactStore save
   - Built from same session's just-persisted FactStore
   - Same transaction — no intervening FactStore changes possible

### Architectural Model

```
RIM Model (immutable in-memory)
    ↓
FactStore(analysis_id) ← atomic save, then immutable
    ↓
HybridRetriever(analysis_id) → queries FactStore(analysis_id)
    ↓
BM25(analysis_id) ← built from immutable FactStore(analysis_id)
```

**Property**: `BM25(analysis_id) ≡ FactStore(analysis_id)`

### Invariant

```
For any analysis_id:
- FactStore entities for that analysis_id do not change after initial save
- BM25 was built in the same transaction as FactStore save
- Therefore: BM25 always reflects the current FactStore state
```

### Risk Assessment

**Genuine Staleness Risk**: LOW (but non-zero)

If code is added that:
- Mutates FactStore after analysis
- Loads old BM25 from deleted analysis
- Shares BM25 cache across analyses

Then staleness could occur.

**Recommendation**: Make the guarantee **explicit and verifiable** without expensive mechanisms.

---

## Solution: Lightweight Version Coupling

Instead of hashing the entire corpus, use:

```python
# At FactStore save time
Analysis.fact_store_version = uuid()

# At BM25 artifact creation time
BM25_artifact.metadata = {
    "fact_store_version": Analysis.fact_store_version,
    "built_at": now()
}

# At retriever init time
if BM25_artifact.fact_store_version != Analysis.fact_store_version:
    BM25 is STALE
```

**Rationale**:
- No expensive hashing of large corpus
- Completely deterministic
- Works immediately (no corpus fingerprinting)
- Detects accidental mutations
- Simple to understand and verify

**Cost**: Single UUID field in Analysis + AnalysisArtifact
