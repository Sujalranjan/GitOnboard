# Dead Code Report

**Confidence:** High Confidence  
**Cross-reference:** [03-module-dependency-graph.md](./03-module-dependency-graph.md), [05-function-analysis.md](./05-function-analysis.md)

> **Methodology:** For each candidate, a grep was performed for any import or call of the symbol anywhere in the active codebase. A symbol is classified as "dead" only if no active import or call was found.

---

## CRITICAL — Entire Dead Sub-Systems

### D-01: `src/analysis/` — Complete Orphaned Framework
**Evidence:** None of these files are imported anywhere in `backend/`:
- `src/analysis/__init__.py`
- `src/analysis/interfaces.py` (`IAnalyzer`, `IAnalysisResult` — abstract base classes never used)
- `src/analysis/registry.py` (plugin registry pattern)
- `src/analysis/runner.py` (analysis runner)
- `src/analysis/models/` (Finding, Health, Metric data models)
- `src/analysis/plugins/cycle_analyzer.py` (cycle detection)
- `src/analysis/plugins/dead_code_analyzer.py` (dead code detection)
- `src/analysis/plugins/metrics_analyzer.py` (metrics)

**Root `tests/`** test these dead files, not the actual backend.  
**Impact:** Significant confusion about project structure. The test suite tests code that has been completely abandoned.  
**Action:** Delete `src/` and `tests/` entirely, or archive them.

---

### D-02: `backend/intelligence/orchestrator/` — Complete Orphaned Sub-Package
**Evidence:** No import of any module from `backend/intelligence/orchestrator/` exists in `backend/routers/`, `backend/services/`, or `backend/main.py`.
- `orchestrator/intent_analyzer.py`
- `orchestrator/knowledge_model.py`  
- `orchestrator/planner.py`
- `orchestrator/providers/`
- `orchestrator/retrieval/`

**Action:** Delete or move to `archive/`.

---

### D-03: `backend/intelligence/visualization/` — Complete Orphaned Sub-Package
**Evidence:** Zero imports from active code.  
**Action:** Delete.

---

### D-04: `backend/intelligence/query/` — Complete Orphaned Sub-Package  
**Evidence:** Zero imports from active code.  
**Note:** `backend/intelligence/query_layer.py` IS used, but `backend/intelligence/query/` is a different sub-package.  
**Action:** Delete.

---

### D-05: `backend/intelligence/experiences/` — Complete Orphaned Sub-Package
**Evidence:** Zero imports from active code.  
**Action:** Delete.

---

## HIGH — Dead Modules Within Active Packages

### D-06: `backend/main.py.orig`
**Evidence:** Not imported. Not a Python module (`.orig` extension). 111,596 bytes.  
**Action:** Delete immediately.

### D-07: `backend/intelligence/pipeline.py` (`AnalysisPipeline` class)
**Evidence:** `worker.py` imports and uses `AnalysisEngine` from `engine/orchestration/pipeline.py`, not this file.  
**Action:** Delete.

### D-08: `backend/intelligence/parser.py` (`LanguageParser` class using tree-sitter)
**Evidence:** The active pipeline uses `ASTParserManager` in `engine/parser/manager.py`. This old `parser.py` file is not called anywhere in the active code path.  
**Action:** Delete or merge into `engine/parser/`.

### D-09: `backend/intelligence/stages/metadata_stage.py` and `metrics_stage.py`
**Evidence:** Not called from `worker.py` or `AnalysisEngine`. The old `pipeline.py` (also dead) previously called these.  
**Action:** Delete.

### D-10: `backend/intelligence/store/store.py`
**Evidence:** Not imported by any active module.  
**Action:** Evaluate and delete.

### D-11: `backend/intelligence/rim/query.py`
**Evidence:** Not imported by `query_layer.py` or any router.  
**Action:** Delete.

### D-12: `backend/intelligence/graphs/call_graph.py`
**Evidence:** Routers import `GraphQueryService` from `graph_query_service.py`. This file (`call_graph.py`) is not imported.  

### D-13: `backend/intelligence/graphs/dependency_graph.py`
**Evidence:** Not imported by any active router.  

### D-14: `backend/intelligence/graphs/graph_view.py`
**Evidence:** Not imported anywhere.

---

## HIGH — Dead Functions Within Active Files

### D-15: `enqueue_job()` in `backend/routers/repo.py` (line 97)
```python
def enqueue_job(job_id: int):
    from backend.main import repo_queue
    import asyncio
    asyncio.create_task(repo_queue.enqueue(job_id))
```
**Evidence:** The `import_repo` handler at line 165 directly calls `await repo_queue.enqueue(job.id)` — `enqueue_job()` is never called.  
**Action:** Delete.

### D-16: `_serialize_dataclass()` in `backend/services/worker.py`
**Evidence:** The `run_analysis()` closure returns `{"core_model": bytes}`. The code path that would call `_serialize_dataclass` for other artifact types is never hit.  
**Action:** Delete.

---

## MEDIUM — Dead Frontend Components

### D-17: `frontend/components/CallGraph.jsx`
**Evidence:** The `[tab]/page.tsx` switch statement case `'callgraph'` renders `<CallExplorer>` (not `<CallGraph>`). Grep confirms no import of `CallGraph` in any page.  
**Impact:** Dead component + confusion with `CallExplorer.jsx`.  
**Action:** Delete.

### D-18: `frontend/components/ViewTabs.jsx`
**Evidence:** The app uses Next.js file-based routing for tab navigation via `Sidebar.jsx`. `ViewTabs.jsx` was the old tab-based approach. Grep confirms zero imports.  
**Action:** Delete.

### D-19: `frontend/components/RepositoryList.jsx`
**Evidence:** `Dashboard/page.tsx` renders its own inline card grid. `RepositoryList.jsx` is never imported anywhere.  
**Action:** Delete.

### D-20: `frontend/utils/graph.js`
**Evidence:** Grep confirms zero imports from any file.  
**Action:** Delete.

---

## LOW — Backend Routes Never Called by Frontend

These routes exist in the backend but are not called by any current frontend component. They may be intentionally incomplete or planned for future use.

| Route | File | Status |
|-------|------|--------|
| `GET /{name}/health/cycles` | repo.py | No frontend consumer |
| `GET /{name}/health/layers` | repo.py | No frontend consumer |
| `GET /{name}/health/dependencies` | repo.py | No frontend consumer |
| `GET /{name}/health/dead-code` | repo.py | No frontend consumer |
| `POST /{name}/symbols/index` | repo.py | `SymbolExplorer.jsx` calls `/symbols/search` directly without triggering indexing first |

---

## Dead Code Size Estimate

| Category | Files | Approx Lines |
|----------|-------|--------------|
| `src/analysis/` framework | ~15 files | ~800 lines |
| `backend/intelligence/orchestrator/` | ~10 files | ~600 lines |
| `backend/intelligence/visualization/` | ~5 files | ~300 lines |
| `backend/intelligence/query/` | ~5 files | ~200 lines |
| `backend/intelligence/experiences/` | ~5 files | ~200 lines |
| `backend/main.py.orig` | 1 file | ~3,500 lines |
| Dead functions/modules in active packages | ~8 items | ~300 lines |
| Dead frontend components | 3 files | ~400 lines |
| **TOTAL** | **~52 items** | **~6,300 lines** |

~6,300 lines of dead code in a project of estimated ~12,000 total source lines = **~52% dead code ratio** in certain sub-packages.
