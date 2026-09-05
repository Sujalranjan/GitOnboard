# Real Repository Analysis Progress Implementation Plan

**Date:** 2026-09-05  
**Objective:** Replace fake static progress (stuck at 50% during "Analyzing") with real work-based progress

---

## 1. EXISTING PIPELINE DISCOVERED

### High-Level Flow (worker.py)

```
1. Queued (initial)
2. Downloading (20s-120s)
   ↓ asyncio.wait_for(download_repo_zipball(...), timeout=120)
3. Analyzing (varies: 30s-600s for large repos)
   ├─ run_analysis() in thread:
   │  ├─ AnalysisEngine.run()
   │  │  ├─ Scan Repository (fast, <1s)
   │  │  ├─ Parse ASTs (slow, scales with files)
   │  │  ├─ Execute Analyzers (medium, scales with symbols)
   │  │  └─ Validate RIM (fast)
   │  └─ Upload files to blob storage (scales with file count/size)
   ├─ Capability Engine (medium)
   ├─ Feature Reconstruction Engine (medium)
   └─ Serialize RIM (medium)
4. Saving (varies: 10s-60s)
   ├─ Persist Facts to Fact Store (scales with entity count)
   ├─ Build BM25 Index (scales with document count)
   ├─ Build Semantic/Chroma Index (scales with entity count)
   └─ Record Indexing Health
5. Completed

### Internal Analysis Engine Stages (pipeline.py)

```
1. Scan Repository
   - Input: directory path
   - Output: manifest with file list
   - Measurable: files discovered (known total)
   - Current: No progress tracking

2. Parse ASTs
   - Input: manifest
   - Output: ASTs for each file
   - Measurable: files parsed (can track processed/total)
   - Current: No progress tracking

3. Execute Analyzers (registry order)
   - Input: model, ASTs
   - Runs all analyzers in registry
   - Output: populated RepositoryModel with entities/relationships
   - Measurable: entities/relationships extracted
   - Current: No progress tracking

4. Validate RIM
   - Input: model
   - Output: validation result
   - Measurable: validation status
   - Current: No progress tracking
```

---

## 2. MEASURABLE WORK UNITS

### File-based (Concrete)

| Operation | Total | Progress Tracking | Notes |
|-----------|-------|-------------------|-------|
| Download | 1 | Download URL size tracking | Already have timeout |
| Scan files | N (known) | Files discovered | Returned from scanner |
| Parse ASTs | N (known) | Files processed | Can track in parser loop |
| Upload blobs | N (known) | Files uploaded | Already looping |

### Entity-based (Discovered)

| Operation | Total | Progress Tracking | Notes |
|-----------|-------|-------------------|-------|
| Extract symbols | M (from AST) | Symbols processed | Known after parsing complete |
| Build relationships | P (from analyzers) | Relationships processed | Known after analysis complete |
| Persist facts | M+P (all entities) | Entities persisted | Can track in persist loop |

### Index-based (Measurable)

| Operation | Total | Progress Tracking | Notes |
|-----------|-------|-------------------|-------|
| BM25 index | K docs (from FactStore count) | Document count | Known: retriever_temp.bm25_index.corpus_size |
| Semantic index | M entities (from RIM) | Entity count | Known: len(rim_model.entities) |

---

## 3. WEIGHTED PROGRESS MODEL

Each stage contributes to overall progress based on estimated time/complexity:

```
Downloading:     5% (fixed, download is mostly I/O)
Scanning:        5% (fast, 1-2 seconds)
Parsing:        30% (scales with file count, most time)
Symbol Extract: 20% (scales with AST complexity)
Relationships:  15% (depends on symbol count)
Persist Facts:  10% (I/O, depends on entity count)
Build Indexes:  10% (BM25 + Semantic, both need to complete)
Finalize:        5% (cleanup, health reporting)
---
TOTAL:         100%
```

### Rationale

- **Parsing (30%):** Slowest operation, file count * complexity factor
- **Symbol Extract (20%):** Medium complexity, proportional to symbols
- **Relationships (15%):** Depends on symbols, graph operations
- **Persist (10%):** I/O bound, usually fast
- **Indexes (10%):** Both must complete, but run in parallel internally
- **Rest (25%):** Scanning, downloading, finalization

---

## 4. DATABASE SCHEMA EXTENSION

### Add to Analysis Model (repository.py)

```python
class Analysis(Base):
    # Existing fields...
    
    # New progress tracking fields
    progress_stage = Column(String, nullable=True)  # "Downloading", "Parsing", etc.
    progress_substage = Column(String, nullable=True)  # "Parsing Python files", etc.
    progress_percentage = Column(Integer, default=0)  # 0-100
    progress_processed = Column(Integer, default=0)  # work units done
    progress_total = Column(Integer, default=0)  # work units total
    progress_unit = Column(String, nullable=True)  # "files", "symbols", "entities"
```

### Add to AnalysisJob Model (repository.py)

```python
class AnalysisJob(Base):
    # Existing fields...
    
    # New progress tracking (denormalized for fast polling)
    progress_percentage = Column(Integer, default=0)
    progress_details = Column(JSONType, nullable=True)  # Detailed stage progress
```

---

## 5. PROGRESS TRACKER SERVICE (NEW)

**File:** `backend/services/progress_tracker.py`

```python
class ProgressTracker:
    """Track real work-based analysis progress."""
    
    def __init__(self, db: Session, analysis_id: int):
        self.db = db
        self.analysis_id = analysis_id
        
    def update_stage(
        self,
        stage: str,           # "Downloading", "Parsing", etc.
        substage: Optional[str] = None,  # "Parsing Python files"
        processed: int = 0,   # Work units completed
        total: int = 0,       # Total work units
        unit: str = "items",  # "files", "symbols", "entities"
    ) -> None:
        """Update progress for current stage."""
        analysis = self.db.query(Analysis).get(self.analysis_id)
        
        # Calculate overall progress using weighted model
        stage_weight = STAGE_WEIGHTS.get(stage, 0)
        if total > 0:
            stage_progress = (processed / total) * stage_weight
        else:
            stage_progress = stage_weight  # Assume complete if no total given
            
        analysis.progress_stage = stage
        analysis.progress_substage = substage or stage
        analysis.progress_percentage = calculate_overall_progress(analysis, stage_progress)
        analysis.progress_processed = processed
        analysis.progress_total = total
        analysis.progress_unit = unit
        
        self.db.commit()
```

---

## 6. INTEGRATION POINTS

### In AnalysisEngine.run() (pipeline.py)

```python
# After scanner.scan()
progress.update_stage("Scanning", "Discovered files", 
                      len(manifest.files), len(manifest.files), "files")

# In parser loop
for file in manifest.files:
    asts[file] = parser.parse(file)
    progress.update_stage("Parsing", f"Parsing {file}", 
                          processed_count, len(manifest.files), "files")

# After analyzers
progress.update_stage("Symbol Extraction", "Extracted symbols",
                      len(model.entities), total_expected, "symbols")

# After all analyzers
progress.update_stage("Building Relationships", "Built relationships",
                      len(model.relationships), total_expected, "relationships")
```

### In Worker.py (save_rim_to_fact_store)

```python
# When persisting entities
from backend.services.progress_tracker import ProgressTracker
progress = ProgressTracker(db, analysis.id)

for entity in rim_model.entities:
    # persist entity
    progress.update_stage("Persisting Facts", "Saving entities",
                          persisted_count, len(rim_model.entities), "entities")
```

### In Worker.py (index building)

```python
# After building each index
progress.update_stage("Building Indexes", "Built BM25 index",
                      bm25_doc_count, bm25_doc_count, "documents")

progress.update_stage("Building Indexes", "Built semantic index",
                      semantic_doc_count, semantic_doc_count, "documents")
```

---

## 7. API RESPONSE CHANGES

### Current (core.py)

```json
{
  "status": "Analyzing",
  "progress": 50,
  "started_at": "...",
  "completed_at": null,
  "error": null
}
```

### New (backward compatible)

```json
{
  "status": "Analyzing",
  "progress": 63,
  "started_at": "...",
  "completed_at": null,
  "error": null,
  
  "stage": "Parsing",
  "substage": "Parsing Python files",
  "processed": 340,
  "total": 1200,
  "unit": "files",
  "message": "Parsing Python files (340 / 1,200)"
}
```

**Backward Compatibility:** `progress` field still exists (integer 0-100). New fields are optional.

---

## 8. FRONTEND CHANGES

**Current behavior:**
```javascript
progress_pct = status_map[job.status]  // 50 for "Analyzing"
```

**New behavior:**
```javascript
progress_pct = response.progress  // Real percentage from backend

// Display detailed message when available
if (response.substage) {
  message = `${response.substage} (${response.processed} / ${response.total} ${response.unit})`
}
```

---

## 9. TESTING STRATEGY

### Unit Tests

1. `test_progress_tracker_initialization`
2. `test_progress_stage_update`
3. `test_overall_progress_calculation`
4. `test_backward_compatibility`

### Integration Tests

1. `test_progress_during_file_parsing`
2. `test_progress_during_symbol_extraction`
3. `test_progress_during_persistence`
4. `test_progress_during_indexing`
5. `test_progress_monotonicity` (never decreases)
6. `test_progress_reaches_100_only_at_completion`

### Manual Validation

Run real repository analysis and record progress at checkpoints:

```
T=0: Queued 5%
T=5: Downloading 10%
T=10: Scanning 15%
T=15: Parsing - 100 / 1200 = 25%
T=30: Parsing - 600 / 1200 = 45%
T=45: Parsing - 1200 / 1200 = 60%
T=50: Symbol Extract - 4200 / 10100 = 68%
T=60: Relationships - 8400 / 10100 = 80%
T=65: Persisting Facts - 6050 / 10100 = 90%
T=75: Building Indexes - 10100 / 10100 = 100%
T=80: Completed 100%
```

---

## 10. IMPLEMENTATION ORDER

1. Add progress fields to Analysis/AnalysisJob models
2. Create ProgressTracker service
3. Wire ProgressTracker into AnalysisEngine
4. Wire ProgressTracker into file upload loop
5. Wire ProgressTracker into persistence loop
6. Wire ProgressTracker into index building
7. Update API endpoint to expose new fields
8. Update frontend to use new progress data
9. Add unit/integration tests
10. Manual validation with real repo

---

## 11. DELIVERABLES

- [ ] Database schema migration (new columns)
- [ ] ProgressTracker service implementation
- [ ] Integration in analysis pipeline (4 locations)
- [ ] API endpoint update
- [ ] Frontend progress display
- [ ] Unit tests (4-5 tests)
- [ ] Integration tests (5-6 tests)
- [ ] Manual validation record
- [ ] Implementation report

---

## 12. RISK ASSESSMENT

| Risk | Mitigation |
|------|-----------|
| Introduces db write overhead | Progress updates batched/async |
| Breaks existing progress consumers | Backward compatible API |
| Race conditions in concurrent updates | Job is single-threaded; sequential updates |
| Progress doesn't match reality | Validate with real repo test |

---

## 13. SUCCESS CRITERIA

✓ Progress percentage increases smoothly during analysis (not stuck at 50%)
✓ Progress reflects actual work completed (files parsed, symbols extracted, etc.)
✓ API exposes stage/substage/processed/total information
✓ Frontend displays meaningful progress message
✓ All existing tests pass
✓ New tests validate progress accuracy
✓ Manual validation shows monotonic progress increase
✓ No regression in analysis speed

---

**Status:** Ready to implement  
**Estimated Effort:** 4-6 hours  
**Priority:** High (blocks product usability)
