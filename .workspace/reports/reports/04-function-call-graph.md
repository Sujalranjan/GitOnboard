# Function Call Graph

**Confidence:** High Confidence (static analysis; dynamic dispatch not traced)  
**Cross-reference:** [05-function-analysis.md](./05-function-analysis.md), [03-module-dependency-graph.md](./03-module-dependency-graph.md)

---

## Critical Call Chains

### Chain 1: Repository Import

```
Browser: POST /api/import
  ▼
import_repo(req, db, current_user)           [repo.py:107]
  ├─ check_repo_limits(owner, repo, token)   [github.py]
  │    └─ get_github_client(token)           [github.py]
  ├─ db.query(Repository)...
  ├─ db.add(repo); db.commit()
  ├─ db.add(analysis); db.commit()
  ├─ db.add(job); db.commit()
  └─ await repo_queue.enqueue(job.id)        [services/queue.py:InMemoryQueue.enqueue]
       └─ asyncio.Queue.put(job_id)
       └─ [consumer picks up] → worker.process(job_id)
```

### Chain 2: Background Analysis Worker

```
AnalysisWorker.process(job_id)               [worker.py]
  ├─ SessionLocal()                          [database.py]
  ├─ db.query(AnalysisJob)...
  ├─ await download_repo_zipball(...)        [github.py]
  │    └─ get_github_client(token)
  │    └─ httpx.AsyncClient.stream(GET, url)
  │    └─ zipfile.ZipFile.extractall (with filtering)
  └─ asyncio.to_thread(run_analysis)
       └─ run_analysis() [closure in worker.py]
            ├─ AnalysisEngine(target_dir, registry).run(repo_name)
            │    ├─ RepositoryScanner(target_dir).scan()
            │    │    └─ os.walk + LanguageDetector.detect_language()
            │    ├─ ASTParserManager.parse_manifest(manifest)
            │    │    └─ For each file: provider.parse(source, file_path)
            │    │         ├─ PythonParser: ast.parse()
            │    │         ├─ TypeScriptParser: subprocess (or synthetic)
            │    │         └─ JavaParser: (synthetic AST dict)
            │    └─ For each analyzer: analyzer.analyze(model, asts)
            │         ├─ SymbolAnalyzer.analyze()
            │         │    └─ PythonSymbolVisitor.visit(ast)
            │         │    └─ _process_synthetic_ast()
            │         ├─ CallGraphAnalyzer.analyze()
            │         │    └─ PythonCallGraphVisitor.visit(ast)
            │         ├─ ImportAnalyzer.analyze()
            │         ├─ DependencyAnalyzer.analyze()
            │         └─ ... (6 more analyzers)
            ├─ PatternRecognitionEngine(pattern_registry).run(model)
            ├─ CapabilityBuilderEngine().run(model)
            │    ├─ CandidateSelector(model).select()
            │    ├─ infer_keywords_from_entity()
            │    ├─ infer_category_and_purpose_from_keywords()
            │    └─ ConsolidationEngine().consolidate(raw_capabilities)
            ├─ FeatureReconstructionEngine().run(model)
            │    ├─ SimilarityEngine(model).build_weighted_graph()
            │    ├─ ConnectedComponents(threshold=0.65).cluster()
            │    ├─ RefinementEngine(model).refine()
            │    └─ NamingEngine(model).name_feature()
            └─ serialize_rim(model) → JSON bytes
```

### Chain 3: Query Endpoint (get_or_build_model pattern)

```
Any route that needs the RIM (e.g., GET /api/repos/{name}/scan)
  ▼
get_or_build_model(repo_name, db, current_user)   [repo.py:567]
  ├─ _get_latest_analysis(repo_name, db, current_user)
  │    ├─ db.query(Repository) → match by URL suffix
  │    └─ db.query(Analysis) → latest by created_at
  ├─ db.query(AnalysisArtifact) filter type="core_model"
  ├─ deserialize_rim(art.blob_data.decode("utf-8"))
  │    └─ json.loads() → RepositoryModel.model_validate()
  └─ QueryLayer(model)
       └─ _build_indexes()  [builds in-memory function/class name dicts]
```

### Chain 4: Semantic Indexing

```
POST /api/repos/{name}/semantic-index
  ▼
semantic_index(repo_name, background_tasks, db, current_user)  [repo.py:844]
  ├─ set_task_status("semantic_index", "processing")     [⚠️ task name is "semantic_index"]
  └─ background_tasks.add_task(background_semantic_index)
       └─ background_semantic_index() [closure]
            ├─ get_or_build_model()
            ├─ chromadb.PersistentClient(path=...) 
            ├─ client.get_or_create_collection("repo_index")
            ├─ For each function/class entity:
            │    collection.add(documents, metadatas, ids)
            └─ set_task_status("semantic_index", "completed")
```

**⚠️ Bug:** `SemanticSearch.jsx` uses `useTaskStatus(repoName, 'semantic')` (line 4), but the backend sets the task name as `'semantic_index'` (repo.py:855). The SSE message will never match the hook's key, so the UI spinner never clears via SSE.

### Chain 5: Feature Tracing

```
GET /api/repos/{name}/trace?q={query}
  ▼
trace_feature(repo_name, q, db, current_user)           [repo.py:1144]
  ├─ get_chroma_collection(repo_name, current_user, db)
  │    └─ chromadb.PersistentClient(path=DATA_REPOS_PATH/chroma)
  │    └─ client.get_collection("repo_index")            [can raise if not indexed]
  ├─ collection.query(query_texts=[q], n_results=5)      [semantic search]
  ├─ get_or_build_model() → QueryLayer
  └─ DeterministicTracer(model).trace_feature(seed_nodes)
       ├─ Builds calls_out, calls_in, imports_out, depends_out, depends_in maps
       ├─ Stage 1: Collect seed entity IDs
       ├─ Stage 2: Expand via DEPENDS_ON relationships
       ├─ Stage 3: Expand via CALLS relationships
       ├─ Stage 4: Add import edges between active nodes
       └─ Stage 5: Heuristic layer ordering → returns {flow, nodes, edges}
```

---

## High Fan-In Functions (Bottlenecks)

| Function | File | # Callers | Risk |
|----------|------|-----------|------|
| `get_or_build_model()` | repo.py:567 | ~20 routes | Deserializes full model on every call — no caching |
| `_get_latest_analysis()` | repo.py:253 | ~15 routes | DB query on every call |
| `set_task_status()` | repo.py:591 | ~8 callers | DB write + SSE notify |
| `get_current_user()` | dependencies/auth.py | Every authenticated route | JWT decode + DB query per request |
| `SessionLocal()` | database.py | Every DB-accessing function | New session per operation |

---

## High Fan-Out Functions

| Function | File | # Callees | Risk |
|----------|------|-----------|------|
| `AnalysisWorker.process()` | worker.py | 10+ | Complex orchestration in single function |
| `run_analysis()` [closure] | worker.py | 5 engines | All failure modes collapse to single try/except |
| `AnalysisEngine.run()` | engine/orchestration/pipeline.py | 3 major phases + 9 analyzers | |
| `import_repo()` | repo.py | 5+ | Async handler with many side effects |

---

## Dead Callers / Dead Call Chains

| Function | File | Why Dead |
|----------|------|----------|
| `enqueue_job()` | repo.py:97 | Defined but only called from `import_router.post("")` indirectly. Actually NOT called — the `import_repo` handler directly calls `await repo_queue.enqueue(job.id)` at line 165, not `enqueue_job()`. `enqueue_job()` is defined but **never called**. |
| `get_task_status()` | repo.py | Only called indirectly — actually used in `index_repo` and similar handlers. Verified used. |
| `AnalysisPipeline.run()` | intelligence/pipeline.py | Not called from worker.py (worker uses `AnalysisEngine` directly) |
| `LanguageParser.*` | intelligence/parser.py | LanguageParser (tree-sitter) not used by active engine (engine uses `ASTParserManager`) |
