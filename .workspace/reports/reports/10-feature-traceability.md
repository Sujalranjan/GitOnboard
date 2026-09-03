# Feature Traceability

**Confidence:** Verified  
**Cross-reference:** [09-api-mapping.md](./09-api-mapping.md), [02-runtime-flow.md](./02-runtime-flow.md)

---

## 1. Repository Import Feature

**User Journey:** User pastes a GitHub URL → clicks "Import" → waits for analysis → sees overview

```
Feature: Import Repository
├─ Frontend: Dashboard/page.tsx → handleImport(e)
│    └─ Validates URL starts with "https://github.com/"
│    └─ repositoryService.import(importUrl)
│         └─ fetchAPI('/import', {method: 'POST', body: {url}})
│
├─ Backend: POST /api/import → import_repo()
│    ├─ check_repo_limits(owner, repo, token)  [github.py]
│    ├─ Creates Repository, Analysis, AnalysisJob in DB
│    └─ await repo_queue.enqueue(job.id)
│
├─ Background: AnalysisWorker.process(job_id)
│    ├─ download_repo_zipball()  → /tmp/repo-analysis/job_{id}/
│    ├─ AnalysisEngine.run()
│    │    ├─ Scan → Parse → Analyze → Validate
│    │    └─ Returns RepositoryModel
│    ├─ PatternRecognitionEngine.run()
│    ├─ CapabilityBuilderEngine.run()
│    ├─ FeatureReconstructionEngine.run()
│    └─ serialize_rim() → AnalysisArtifact("core_model", blob_data)
│
├─ Frontend polling: RepositoryOverview → repositoryService.scan() every 3s
│    └─ GET /api/repos/{name}/scan → returns {status: "processing"} until done
│
└─ When done: status="completed" → renders RepositoryOverview component
```

**Status:** ✅ Complete end-to-end flow works.

---

## 2. Repository Overview Feature

**User Journey:** Navigate to repo → see file counts, language, health summary

```
Feature: Repository Overview
├─ Frontend: app/repository/[repoName]/page.tsx
│    └─ repositoryService.scan() → GET /api/repos/{name}/scan
│
├─ Component: RepositoryOverview.jsx
│    ├─ fetch /api/repos/{name}/health/scores → health panel
│    ├─ fetch /api/repos/{name}/stats → stats panel
│    └─ fetch /api/repos/{name}/health/findings → findings panel
│
├─ Backend: scan_repo()
│    └─ get_or_build_model() → QueryLayer
│    └─ Builds hierarchy tree from entities
│    └─ Returns {status, overview, hierarchy, files}
│
└─ Backend: get_stats()
     └─ Queries enriched_metadata artifact for detailed stats
```

**Status:** ✅ Works. `repo.repository_path` field is undefined on the Dashboard card (I-01), but the overview page itself is correct.

---

## 3. File Explorer Feature

**User Journey:** Click "File Explorer" tab → browse directory tree → click file → see functions/classes

```
Feature: File Explorer
├─ Route: /repository/{name}/explorer → ExplorerView.jsx
│
├─ ExplorerView.jsx:
│    └─ repositoryService.scan() → GET /api/repos/{name}/scan
│    └─ Extracts hierarchy from scan data
│    └─ Renders FileExplorer.jsx (tree component)
│
├─ On file click:
│    └─ repositoryService.parseFile(repoName, filePath)
│         └─ GET /api/repos/{name}/parse?file_path={path}
│         └─ Fetches raw file from GitHub via fetch_file_content()
│         └─ Parses with LanguageParser (Python AST) in parse_repo_file()
│
└─ CodeDetailsViewer.jsx renders the file content
```

**Status:** ✅ Works. Note: `parse` endpoint fetches live from GitHub, so requires valid `github_access_token` for the user.

---

## 4. Dependency Graph Feature

**User Journey:** Click "Dependency Graph" tab → see interactive force-directed graph

```
Feature: Dependency Graph
├─ Route: /repository/{name}/graph → DependencyGraph.jsx
│
├─ DependencyGraph.jsx:
│    └─ fetch /api/repos/{name}/dependencies
│         └─ get_dependencies() → get_or_build_model()
│         └─ Builds {nodes, edges} from DEPENDS_ON relationships
│
├─ Frontend:
│    ├─ buildVFS() → virtual file system from nodes
│    ├─ buildVisibleGraph() → visible nodes/edges based on expanded state
│    ├─ layoutGraph() / applyLocalRelaxation() → positions via dagre
│    └─ Renders ReactFlow canvas with nodes and edges
│
└─ User can expand/collapse directory nodes, zoom, pan
```

**Status:** ✅ Works (data-dependent — depends on analysis quality).

---

## 5. Search Feature

**User Journey:** Click "Search" tab → component auto-triggers indexing → user searches

```
Feature: Search
├─ Route: /repository/{name}/search → Search.jsx
│
├─ On mount: POST /api/repos/{name}/index
│    └─ index_repo() → set_task_status("index", "processing")
│    └─ Background: get_or_build_model() (just loads existing model)
│    └─ set_task_status("index", "completed")
│
├─ SSE: useTaskStatus(repoName, 'index')
│    └─ EventSource /api/repos/{name}/tasks/stream
│    └─ status updates 'processing' → 'completed'
│    └─ Spinner clears when status=completed
│
└─ On search submit: GET /api/repos/{name}/search?q={query}
     └─ search_repo() → query_layer.search_entities(q)
     └─ Returns {results: [{file_path, match_reasons}]}
```

**Status:** ✅ Works. SSE task name matches.

---

## 6. Semantic Search Feature

**User Journey:** Click "Semantic Search" tab → index is built → user searches semantically

```
Feature: Semantic Search
├─ Route: /repository/{name}/semantic → SemanticSearch.jsx
│
├─ On mount: GET /api/repos/{name}/semantic-status
│    └─ Returns {status: "not_indexed"|"indexed"}
│
├─ If not indexed: POST /api/repos/{name}/semantic-index
│    └─ semantic_index() → background task
│    └─ Uses ChromaDB PersistentClient
│    └─ Embeds all function/class entities
│    └─ set_task_status("semantic_index", "completed")
│
├─ ⚠️ SSE BUG: useTaskStatus(repoName, 'semantic') ← wrong key
│    └─ Backend sets 'semantic_index' → SSE never updates UI
│    └─ Spinner gets stuck forever
│
└─ On search: GET /api/repos/{name}/semantic-search?q={query}
     └─ collection.query(query_texts=[q], n_results=5)
     └─ Returns {results: [{id, name, type, file_path, content, score}]}
```

**Status:** ⚠️ SSE spinner bug (task name mismatch). Semantic search itself works once indexing completes.

---

## 7. AI Summary Feature

**User Journey:** Click "AI Summary" tab → view existing summary or generate new one

```
Feature: AI Summary
├─ Route: /repository/{name}/summary → RepositorySummary.jsx
│
├─ On mount: GET /api/repos/{name}/summary
│    └─ Returns {summary: "...", outdated: false} or {summary: null}
│
├─ If no summary → user clicks "Generate"
│    └─ POST /api/repos/{name}/summary/generate
│    └─ set_task_status("summary", "processing")
│    └─ Background:
│         ├─ get_or_build_model()
│         ├─ Collects metadata (files, functions, classes)
│         ├─ llm_service.generate_summary(metadata)
│         │    └─ POST http://localhost:11434/api/generate (Ollama)
│         ├─ Saves AnalysisArtifact(type="summary", data=markdown_str)
│         └─ set_task_status("summary", "completed")
│
└─ SSE: useTaskStatus(repoName, 'summary') ← ✅ correct task name
     └─ When completed → fetchSummary() again → renders markdown
```

**Status:** ✅ Works (requires Ollama running locally with configured model).

---

## 8. Feature Tracing Feature

**User Journey:** Click "Feature Tracing" → type feature name → see implementation path

```
Feature: Feature Tracing
├─ Route: /repository/{name}/trace → trace/page.tsx
│
├─ On submit: GET /api/repos/{name}/trace?q={query}
│    └─ trace_feature():
│         ├─ get_chroma_collection() → requires prior semantic indexing
│         ├─ collection.query([q], n_results=5) → seed nodes
│         ├─ get_or_build_model()
│         └─ DeterministicTracer.trace_feature(seed_nodes)
│              └─ Returns {flow, nodes, edges}
│
├─ Frontend renders implementation path (ordered nodes with arrows)
│
└─ Optional: "Explain Trace" → POST /api/repos/{name}/trace/explain
     └─ explain_trace():
          ├─ Builds prompt from trace data
          └─ llm_service.generate_explanation(prompt) → Ollama
```

**Status:** ✅ Works (requires semantic indexing to be done first + Ollama).

---

## 9. Health & Analysis Features

```
Feature: Health Scores
├─ Route: /repository/{name}/health → RepositoryHealth.jsx
└─ GET /api/repos/{name}/health/scores
     └─ Queries "findings" artifact, computes score formula
     └─ Returns {health_score, status, categories}
     
Feature: Health Metrics
├─ Route: /repository/{name}/metrics → RepositoryMetrics.jsx
└─ GET /api/repos/{name}/health/metrics
     └─ Returns raw "metrics" artifact data
     
Feature: Analysis (Findings + Smells)
├─ Route: /repository/{name}/analysis → RepositoryAnalysis.jsx
├─ GET /api/repos/{name}/health/findings → {findings}
└─ GET /api/repos/{name}/health/smells → {smells}
```

**Status:** ✅ All work. Note: Health score formula is heuristic (findings severity count), not real static analysis metrics.
