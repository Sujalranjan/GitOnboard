# Architectural Smells

**Confidence:** Verified  
**Cross-reference:** [03-module-dependency-graph.md](./03-module-dependency-graph.md), [12-architectural-smells.md](./12-architectural-smells.md)

---

## A-01: God Router — `backend/routers/repo.py` (1,210+ lines)

**Type:** God Object / God Module  
**Evidence:** `repo.py` is 1,210+ lines and contains:
- 30+ route handlers
- 2 router instances (`repo_router`, `import_router`)  
- 4 helper functions (`_get_latest_analysis`, `get_or_build_model`, `get_task_status`, `set_task_status`)
- 1 dead function (`enqueue_job`)
- Business logic (health score computation)
- Infrastructure concerns (database queries, ChromaDB management)
- Background task closures

**Impact:** Impossible to navigate, test, or maintain. Any bug fix risks introducing regressions. The health score calculation (a business logic concern) is embedded in a route handler.

**Refactoring:** Split into: `repos.py`, `analysis.py`, `search.py`, `health.py`, `graph.py`, `semantic.py`, `summary.py`, `trace.py`.

---

## A-02: No Caching on `get_or_build_model()` — Performance Bomb

**Type:** Performance Anti-Pattern  
**Evidence:** `get_or_build_model()` at repo.py:567 is called in 20+ route handlers. Each call:
1. Queries `_get_latest_analysis()` → 2 DB queries (Repository, Analysis)
2. Queries `AnalysisArtifact` → 1 DB query
3. `json.loads(blob_data.decode("utf-8"))` — deserializes potentially large JSON
4. `RepositoryModel.model_validate(data)` — reconstructs the full Pydantic model
5. `QueryLayer(model)._build_indexes()` — rebuilds in-memory dict indexes

This happens on **every single API request**. For a large repository with thousands of entities, this could take hundreds of milliseconds per call.

**Impact:** Every tab switch, every graph render, every search causes full model deserialization.

**Fix:** Cache the deserialized model in memory, keyed by `(repo_name, analysis_id)`. Invalidate on reanalysis.

---

## A-03: Circular Import — `repo.py` → `main.py`

**Type:** Circular Dependency  
**Evidence:** `repo.py:97` contains `from backend.main import repo_queue` inside `enqueue_job()`. `main.py` imports from `repo.py`. This is a deferred circular import. (The `enqueue_job` function is dead, so it has no runtime impact currently, but the circular dependency pattern is dangerous.)

**Fix:** Pass `repo_queue` as a dependency or store it in a module separate from both `main.py` and `repo.py` (e.g., `backend/queue_singleton.py`).

---

## A-04: Large Orphaned Sub-Systems (~6,300 Lines)

**Type:** Accumulation of Dead Code / Premature Architecture  
**Evidence:** Documented in [06-dead-code-report.md](./06-dead-code-report.md). Over 6,300 lines of orphaned code:
- `src/analysis/` (complete abandoned analysis framework)
- `backend/intelligence/orchestrator/`
- `backend/intelligence/visualization/`
- `backend/intelligence/query/`
- `backend/intelligence/experiences/`
- `backend/main.py.orig`

**Impact:** Developer confusion, false sense of completeness, maintenance burden, misleading `tests/` that test dead code.

---

## A-05: Inconsistent API Service Layer in Frontend

**Type:** Inconsistent Abstraction  
**Evidence:** `services/repository.js` provides a clean service layer for some endpoints (`getAll`, `delete`, `scan`, `parseFile`, `import`, `reanalyze`). But 12 other components bypass this layer and call `fetch()` directly. This means error handling, base URL logic, and auth cookie forwarding logic is duplicated in each component.

**Fix:** Extend `repositoryService` to cover all endpoints. All components should use the service layer.

---

## A-06: Health Score is Synthetic, Not Based on Real Analysis

**Type:** Misleading Representation  
**Evidence:** `get_health_scores()` in `repo.py:506`:
```python
deduction = sum(5.0 if sev in ["CRITICAL","ERROR"] else 2.0 if sev=="WARNING" else 0.5 
                for f in findings for sev in [f.get("severity","INFO").upper()])
m_score = max(0.0, 100.0 - deduction * 0.4)
r_score = max(0.0, 100.0 - deduction * 0.3)
s_score = max(0.0, 100.0 - deduction * 0.3)
```

The "Maintainability", "Reliability", and "Security" category scores are all derived from the same `findings` list with different multipliers. They do not independently measure what they claim (e.g., security score is not based on security-specific analysis, cyclomatic complexity is not measured).

**Impact:** Users see health scores that appear authoritative but are not meaningful.

---

## A-07: Background Analysis Worker Has No Progress Notifications

**Type:** Missing Feedback Loop  
**Evidence:** `AnalysisWorker.process()` updates `job.status` in the database (Downloading, Analyzing, Saving) but does NOT call `task_manager.notify()`. The frontend polls via `repositoryService.scan()` with a 3-second interval. This means the "progress bar" on the overview page shows stages (based on `job_status`) only via polling, not SSE.

The SSE infrastructure exists (`task_manager`, `useTaskStatus`, `stream_tasks`) but is **not wired to the import/analysis background job**. It is only used for the secondary operations (index, summary/generate, semantic-index).

**Impact:** Unnecessary polling; 3-second latency in progress updates; missed opportunity to use the existing SSE system.

---

## A-08: `asyncio.create_task()` in Non-Async Context (Dead Code but Dangerous)

**Type:** Incorrect Async Usage  
**Evidence:** `enqueue_job()` in `repo.py` (line 97-100, dead function):
```python
def enqueue_job(job_id: int):
    from backend.main import repo_queue
    import asyncio
    asyncio.create_task(repo_queue.enqueue(job_id))
```

`asyncio.create_task()` requires a running event loop in the current thread. Called from a synchronous function, this would raise `RuntimeError: no current event loop`. Although this function is dead, the pattern is wrong and could be cargo-culted.

---

## A-09: ChromaDB Collection Name Not Isolated by User

**Type:** Data Isolation Bug  
**Evidence:** In `semantic_index()` and `get_chroma_collection()`, the collection is named `{repo_name}_index`. However, if two different users import a repository with the same name, they would share the same ChromaDB collection.

**Fix:** Use `{user_id}_{repo_name}_index` as the collection name.

---

## A-10: PyJWT `decode()` Without `algorithms` Parameter

**Type:** Incorrect API Usage / Security Risk  
**Evidence:** `dependencies/auth.py` calls `jwt.decode(token, settings.jwt_secret, ...)`. PyJWT v2+ requires the `algorithms` parameter. If `algorithms` is omitted, the decode may fail or may accept unexpected algorithms.

**Fix:** `jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])`

---

## A-11: `enqueue_job()` Is Dead but Contains a Circular Import

**Type:** Code Rot Compound Issue  
**Evidence:** Dead function at repo.py:97 that (a) is never called, (b) contains a circular import, (c) uses incorrect async primitives. Three issues in 4 lines of dead code.

**Fix:** Delete `enqueue_job()`.
