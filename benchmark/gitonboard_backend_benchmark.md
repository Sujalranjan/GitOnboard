# GitOnboard Backend Benchmark

15 rigorous questions targeting GitOnboard Backend architecture (FastAPI, Tree-sitter AST, PostgreSQL Fact Store, Layer 6 Capabilities, Context Assembler, and Autonomous QALoop).

> **Evaluation Rule:** Every question specifies concrete `required_evidence`, `expected_symbols`, `expected_answer_points`, and `difficulty` levels (L1–L5). A rigorous agent evaluation must grade answers against these ground-truth expectations.

---

## GB01 — Security (L4)
**Question:** Trace how a repository/analysis identifier is propagated from the agent request into retrieval and context assembly. Where could repository data leak across analyses, and what code/tests enforce isolation?

- **Category:** `security`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 5, Hops: 4, Concepts: 5)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `True`

**Required Evidence Files:**
- `backend/agent/context/assembler.py`
- `backend/repository_tools/tools.py`
- `backend/tests/unit/test_repository_context_isolation.py`

**Supporting Evidence:**
- `backend/planning/impact_analysis.py`
- `backend/intelligence/retrieval/expansion.py`
- `backend/agent/planning/orchestrator.py`
- `backend/agent/modes.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/agent/safety/policy.py`

**Expected Symbols:** `ContextAssembler, assemble_context, RepositoryToolLayer, FactFile, resolve_target_repository_and_analysis`

**Expected Concepts:** `analysis-scoped composite keys ({analysis_id}:{entity_id}), FactFile.analysis_id SQL filter isolation, multi-language archetype adaptation (Python vs TS), isolated database session fixtures, prevention of cross-repo concept leakage`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, graph_traversal`

**Expected Answer Points:**
1. Agent requests supply repository_id and user_id, which resolve_target_repository_and_analysis maps to the latest completed analysis_id in PostgreSQL.
1. ContextAssembler.assemble_context strictly filters all FactStore queries using FactFile.analysis_id == request.analysis_id and FactSymbol.analysis_id == request.analysis_id.
1. RepositoryToolLayer scopes all filesystem search, read_file, and retrieval operations to the resolved analysis_id and repository snapshot hash.
1. Data could leak if fallback queries search globally across all repositories or if domain concepts hardcode application component names.
1. backend/tests/unit/test_repository_context_isolation.py enforces strict isolation by populating dual repositories in an isolated SQLite fixture and verifying that planning for a Python repo never leaks TypeScript files or foreign symbols.

**Expected Answer Structure:**
- repository and analysis identifier resolution
- SQL query scoping across Fact Store models
- RepositoryToolLayer snapshot isolation
- potential leakage surfaces (unscoped queries, hardcoded concepts)
- automated test verification in test_repository_context_isolation.py

**Known Traps & Failure Modes:**
- Assuming repository isolation is handled merely by system prompt instructions rather than SQL foreign-key filtering and composite keys
- Overlooking test_repository_context_isolation.py which explicitly validates zero-leakage contracts

---

## GB02 — Execution Flow (L4)
**Question:** When the agent decides it needs source code from a repository, trace the path from the repository tool call to the actual source returned to the LLM. Identify where file metadata, source/blob access, line ranges, and final context are assembled.

- **Category:** `execution_flow`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 4, Hops: 4, Concepts: 5)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `backend/repository_tools/tools.py`
- `backend/intelligence/retrieval/source_reader.py`
- `backend/agent/context/assembler.py`

**Supporting Evidence:**
- `backend/routers/repo/structure.py`
- `backend/storage/azure.py`
- `backend/intelligence/notebook.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/services/qa_protocol.py`

**Expected Symbols:** `read_file, RepositorySourceReader, read_source_snippet, get_storage, resolve_source_document, truncate_semantically`

**Expected Concepts:** `Azure Blob snapshot key construction, Repository.repository_hash resolution, line slicing and clamping, semantic token budget truncation, Jupyter notebook source extraction`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, cross_file_trace`

**Expected Answer Points:**
1. Agent invokes read_file(path, start_line, end_line) through tool dispatch.
1. RepositoryToolLayer verifies analysis_id and looks up Repository.repository_hash from PostgreSQL.
1. Builds blob key 'repositories/{repo_hash}/snapshots/{snapshot_id}/{path}' and downloads object text via AzureBlobStorage / Azurite.
1. resolve_source_document parses source code or converts .ipynb notebooks to standard Python representations.
1. Applies line slicing (lines[start_line-1:end_line]) and optional semantic truncation if max_content_tokens is set, before returning to context assembly.

**Expected Answer Structure:**
- tool call invocation and parameter validation
- database hash lookup and Azure blob key construction
- blob download and notebook normalization
- line slicing and context overflow protection
- return format to LLM observation context

**Known Traps & Failure Modes:**
- Assuming files are read directly from local git clone rather than Azure Blob Storage snapshots
- Missing the notebook conversion hook in resolve_source_document

---

## GB03 — Debugging (L4)
**Question:** If the frontend reports that a source read returned only lines 1–1, while the LLM says it was not given the requested source, what backend path should be inspected first? Explain how an incorrect range selection or context assembly could produce this symptom and what evidence would distinguish the possible causes.

- **Category:** `debugging`
- **Answer Type:** `debugging`
- **Difficulty:** `L4` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `backend/repository_tools/tools.py`
- `backend/intelligence/retrieval/source_reader.py`
- `backend/agent/context/assembler.py`

**Supporting Evidence:**
- `backend/routers/repo/structure.py`
- `backend/services/qa_loop.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/agent/context/formatter.py`

**Expected Symbols:** `read_file, clamp_line_range, read_source_snippet`

**Expected Concepts:** `off-by-one or default start_line=1, end_line=1 clamping, context_overflow_protection early exit on large files (>150 lines without end_line), empty or whitespace-only slice extraction, FactSymbol default line_start=1 fallback when AST parser misses line metadata`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. First inspect clamp_line_range and parameter parsing in read_file: if end_line is omitted or parsed as 1, the slice defaults to 1–1.
1. Inspect context_overflow_protection: if a file has >150 lines and end_line is missing, read_file returns an error message requesting line limits rather than source text.
1. Inspect AST symbol extraction in FactSymbol: if line_start is null or 1 and line_end is null, context assembler requests 1–1 by default.
1. Inspect source_reader.py: if blob content download fails or file is empty, splitlines() returns 0 or 1 line.
1. Distinguish causes by checking tool observation logs: an error message indicates context protection, while raw_text with line 1 indicates faulty AST coordinates or line clamping.

**Expected Answer Structure:**
- primary backend inspection points
- cause 1: parameter clamping and default end_line
- cause 2: context overflow protection on large files
- cause 3: AST symbol coordinate defaults in FactSymbol
- distinguishing telemetry evidence

**Known Traps & Failure Modes:**
- Blaming the frontend UI without checking backend clamp_line_range and context_overflow_protection
- Missing that FactSymbol records default line_start=1 if AST parsing fails to pinpoint end lines

---

## GB04 — Architecture (L3)
**Question:** How does the backend resolve which repository the agent is operating on? Trace repository resolution, authentication, mode selection/fallback, and the point at which repository-scoped context becomes available to the agent.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 3, Hops: 3, Concepts: 4)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `backend/agent/modes.py`
- `backend/routers/agent.py`
- `backend/dependencies/auth.py`

**Supporting Evidence:**
- `backend/models/repository.py`
- `backend/agent/engineering_agent.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/routers/auth.py`

**Expected Symbols:** `resolve_target_repository_and_analysis, get_current_user, execute_explore, execute_plan`

**Expected Concepts:** `user authentication dependency (JWT cookie/bearer), repository lookup by name/URL and user_id ownership, latest analysis resolution (status='Completed'), mode dispatch (explore, explain, plan, implement), injection of repository_id and analysis_id into context`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. backend/routers/agent.py intercepts agent requests and authenticates the user via get_current_user dependency.
1. Calls resolve_target_repository_and_analysis(db, repo_name, user_id) in backend/agent/modes.py.
1. Queries Repository table matching user_id and repository name/URL, then finds the most recent Analysis with status='Completed'.
1. Determines mode (explore, explain, plan, implement) from request payload or intent classifier.
1. Instantiates ContextAssembler or QALoop passing resolved repository_id and analysis_id, making FactStore records accessible.

**Expected Answer Structure:**
- HTTP request receipt and user authentication
- repository ownership validation in database
- latest completed analysis selection
- mode router dispatch and fallback
- context injection into agent loop

**Known Traps & Failure Modes:**
- Assuming repository resolution uses global active directory rather than user-owned database records
- Missing that only analyses with status='Completed' provide valid analysis_id

---

## GB05 — Security (L3)
**Question:** How is semantic search scoped so that results from one repository/analysis cannot contaminate another? Trace the Chroma/vector-store path, collection/path construction, metadata filters, and the caller that supplies the scope.

- **Category:** `security`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `backend/routers/repo/semantic.py`
- `backend/intelligence/retrieval/retriever.py`
- `backend/models/repository.py`

**Supporting Evidence:**
- `backend/intelligence/retrieval/semantic_builder.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/intelligence/retrieval/lexical.py`

**Expected Symbols:** `get_chroma_collection, CHROMA_BASE_DIR, AnalysisArtifact, HybridRetriever`

**Expected Concepts:** `hierarchical filesystem partitioning (/tmp/chroma/user_{uid}/repo_{rid}/analysis_{aid}), AnalysisArtifact storage in PostgreSQL (type='semantic_index_db'), zip extraction into isolated analysis directory, metadata filtering on file_path and symbol, analysis_id parameter propagation`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. backend/routers/repo/semantic.py enforces isolated Chroma directories via CHROMA_BASE_DIR / f'user_{user_id}' / f'repo_{repo_id}' / f'analysis_{analysis_id}'.
1. If not present locally, downloads the pre-built semantic index artifact (type='semantic_index_db') from PostgreSQL AnalysisArtifact table and unzips it into the analysis directory.
1. PersistentClient opens only the specific collection 'semantic_index' in that isolated directory.
1. HybridRetriever receives the scoped Chroma collection and analysis_id, ensuring vector queries only search within that snapshot.
1. Vector metadata includes file_path and symbol name, mapped back to FactSymbol and FactFile rows for that analysis.

**Expected Answer Structure:**
- directory-level path partitioning scheme
- AnalysisArtifact database persistence and on-demand unpack
- Chroma PersistentClient instantiation
- HybridRetriever integration
- metadata verification and isolation guarantee

**Known Traps & Failure Modes:**
- Assuming Chroma runs as a shared multi-tenant cloud service with metadata tags rather than partitioned persistent local directories and DB artifacts
- Missing that AnalysisArtifact stores compressed Chroma databases directly in PostgreSQL

---

## GB06 — Retrieval (L4)
**Question:** Explain how GitOnboard combines exact/entity retrieval, lexical/code-aware retrieval, semantic retrieval, and rank fusion before results reach the agent. Which retrieval signals complement each other, and where is the final ranking/merging performed?

- **Category:** `retrieval`
- **Answer Type:** `architecture`
- **Difficulty:** `L4` (Files: 4, Hops: 4, Concepts: 5)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `False`

**Required Evidence Files:**
- `backend/intelligence/retrieval/retriever.py`
- `backend/intelligence/retrieval/fusion.py`
- `backend/intelligence/retrieval/lexical.py`

**Supporting Evidence:**
- `backend/routers/repo/semantic.py`
- `backend/models/fact_store.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/intelligence/retrieval/source_reader.py`

**Expected Symbols:** `HybridRetriever, reciprocal_rank_fusion, retrieve, LexicalRetriever, FactSymbol`

**Expected Concepts:** `Reciprocal Rank Fusion (RRF with k=60), exact symbol lookup (FactSymbol with exact_weight=1.2), BM25 / lexical token matching (lexical_weight=1.0), Chroma semantic embedding distance (semantic_weight=1.0), structural expansion over FactRelationship`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup, graph_traversal`

**Expected Answer Points:**
1. HybridRetriever coordinates three independent retrieval signals: exact entity matching from PostgreSQL FactSymbol, lexical token search via BM25/LexicalRetriever, and vector embedding similarity via Chroma collection.
1. Exact matching captures identifier names with high precision; lexical matching captures comments and string occurrences; semantic matching captures conceptual descriptions.
1. Results are unified using Reciprocal Rank Fusion (reciprocal_rank_fusion in fusion.py) with formula: RRF_score = sum(weight / (k + rank)).
1. Optionally expands candidates using FactRelationship (CALLS, IMPORTS) to include adjacent structural dependencies.
1. Returns ranked items sorted by rrf_score to context assembly or QA loop.

**Expected Answer Structure:**
- the three retrieval signals and their complementarities
- exact matching via FactStore
- lexical and semantic retriever queries
- Reciprocal Rank Fusion algorithm and parameter k=60
- structural relationship expansion and final sorting

**Known Traps & Failure Modes:**
- Describing generic RAG instead of GitOnboard's concrete HybridRetriever and reciprocal_rank_fusion implementation
- Forgetting that exact symbol matches receive higher weight (1.2) than lexical/semantic (1.0)

---

## GB07 — Architecture (L4)
**Question:** How does the backend turn parsed repository information into a knowledge graph? Trace AST parsing into symbols/entities and then into relationships such as imports, calls, inheritance, or file ownership. Identify where the graph is persisted and queried.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 4, Hops: 4, Concepts: 5)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `True`

**Required Evidence Files:**
- `backend/intelligence/store/fact_store.py`
- `backend/models/fact_store.py`
- `backend/agent/graph/builder.py`

**Supporting Evidence:**
- `backend/intelligence/retrieval/graph_traverser.py`
- `backend/services/tool_dispatch.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/agent/graph/state.py`

**Expected Symbols:** `save_rim_to_fact_store, FactRelationship, FactSymbol, FactFile, AgentGraphBuilder, FactStoreGraphTraverser`

**Expected Concepts:** `Tree-sitter CST parsing to RepositoryModel, relational Fact Store tables (files, symbols, relationships), relationship types (CONTAINS, CALLS, IMPORTS, INHERITS), composite keys ({analysis_id}:{entity_id}), graph traversal in FactStoreGraphTraverser`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, graph_traversal`

**Expected Answer Points:**
1. Tree-sitter parser extracts symbols (functions, classes, methods) and static AST references into an in-memory RepositoryModel.
1. save_rim_to_fact_store in fact_store.py persists the model into PostgreSQL: files into FactFile, entities into FactSymbol, and edges into FactRelationship.
1. FactRelationship stores from_symbol_id, to_symbol_id, rel_type (CALLS, IMPORTS, INHERITS, CONTAINS), and evidence_line/evidence_snippet.
1. Composite IDs enforce strict analysis isolation.
1. AgentGraphBuilder and FactStoreGraphTraverser query FactRelationship to build bounded subgraphs and navigate caller/callee paths.

**Expected Answer Structure:**
- AST extraction into RepositoryModel entities
- persistence to PostgreSQL Fact Store tables
- FactRelationship schema and edge types
- querying and traversal mechanisms (FactStoreGraphTraverser, AgentGraphBuilder)

**Known Traps & Failure Modes:**
- Assuming a graph database like Neo4j is used (GitOnboard persists graphs directly into PostgreSQL relational FactRelationship tables)
- Missing composite ID format {analysis_id}:{entity_id}

---

## GB08 — Impact Analysis (L4)
**Question:** Given a request to change a function, how does the backend determine potentially affected files or symbols? Trace the impact-analysis algorithm and identify which graph relationships it relies on and how the result is passed into planning.

- **Category:** `impact_analysis`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 4, Hops: 4, Concepts: 5)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `False`

**Required Evidence Files:**
- `backend/planning/impact_analysis.py`
- `backend/models/fact_store.py`
- `backend/agent/planning/orchestrator.py`

**Supporting Evidence:**
- `backend/agent/graph/builder.py`
- `backend/planning/requirements.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/planning/change_classifier.py`

**Expected Symbols:** `ImpactAnalyzer, analyze_impact, FactRelationship, PlanningOrchestrator`

**Expected Concepts:** `multi-hop dependency traversal, relationship types (CALLS, IMPORTS, INHERITS, QUERIES), blast radius calculation, affected symbols and files aggregation, task dependency injection in PlanningOrchestrator`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, graph_traversal`

**Expected Answer Points:**
1. ImpactAnalyzer.analyze_impact receives target symbol(s) and analysis_id.
1. Queries PostgreSQL FactRelationship for reverse CALLS (callers), reverse IMPORTS (dependent modules), and INHERITS (subclasses).
1. Performs bounded depth traversal (typically depth 1–3) to calculate upstream blast radius.
1. Aggregates unique affected file paths and caller symbols into an ImpactReport.
1. PlanningOrchestrator consumes the ImpactReport to generate implementation tasks, ordering modifications before dependent test updates.

**Expected Answer Structure:**
- input target symbol and analysis context
- graph traversal across CALLS/IMPORTS/INHERITS edges
- blast radius calculation and cycle prevention
- ImpactReport structure
- planning task generation and sequencing

**Known Traps & Failure Modes:**
- Assuming impact analysis only looks at file imports (it traverses function CALLS and class INHERITS)
- Overlooking how PlanningOrchestrator translates affected files into structured task dependencies

---

## GB09 — Architecture (L3)
**Question:** What is the responsibility boundary between TaskOrchestrator, TaskExecutor, and the engineering-agent loop? Trace one task from planning to execution and explain which component decides what should happen versus which component performs the work.

- **Category:** `architecture`
- **Answer Type:** `architecture`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `backend/agent/tasks/orchestrator.py`
- `backend/agent/tasks/executor.py`
- `backend/agent/engineering_agent.py`

**Supporting Evidence:**
- `backend/agent/tasks/state_machine.py`
- `backend/routers/agent.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/services/worker.py`

**Expected Symbols:** `TaskOrchestrator, TaskExecutor, EngineeringAgent, TaskStateMachine`

**Expected Concepts:** `separation of planning vs execution, topological task dependency resolution, task state transitions (PENDING -> RUNNING -> COMPLETED), tool execution delegation, approval gate interception`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. EngineeringAgent is the overarching controller managing agent lifecycle, state transitions (UNDERSTANDING -> PLANNING -> EXECUTING), and user interactions.
1. TaskOrchestrator manages the task graph: parses dependencies, determines execution order (topological sort), and evaluates preconditions.
1. TaskExecutor executes individual task units: dispatches tool operations, monitors output, and reports success/failure back to TaskStateMachine.
1. TaskOrchestrator decides WHAT tasks should run and WHEN, while TaskExecutor performs the actual code or tool modifications.
1. If a task requires approval, TaskOrchestrator halts execution and requests user consent before passing the task to TaskExecutor.

**Expected Answer Structure:**
- EngineeringAgent high-level coordinator role
- TaskOrchestrator planning and dependency role
- TaskExecutor work execution and tool dispatch role
- state transition flow across TaskStateMachine
- concrete execution trace of one task

**Known Traps & Failure Modes:**
- Conflating TaskOrchestrator with PlanningOrchestrator (planning creates the plan; TaskOrchestrator executes tasks)
- Assuming TaskExecutor decides task order (order is strictly governed by TaskOrchestrator dependencies)

---

## GB10 — Security (L3)
**Question:** Which backend operations require approval before execution, how is approval state represented, and where is the final safety decision enforced? Trace the request through the approval mechanism to the executor.

- **Category:** `security`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `backend/agent/safety/approval.py`
- `backend/agent/safety/policy.py`
- `backend/agent/tasks/executor.py`

**Supporting Evidence:**
- `backend/models/implementation.py`
- `backend/routers/agent.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/agent/safety/cancellation.py`

**Expected Symbols:** `ApprovalController, ExecutionPolicy, requires_approval, TaskExecutor`

**Expected Concepts:** `mutation operations requiring approval (code writes, deletions, command execution), ApprovalStatus (PENDING, APPROVED, REJECTED), backend policy evaluation in ExecutionPolicy, enforcement at TaskExecutor pre-execution gate, prevention of UI client spoofing`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. ExecutionPolicy in policy.py classifies actions: read/inspection operations are auto-approved, while file mutations, file creations, and shell executions require explicit user approval.
1. ApprovalController manages approval requests, storing them in PostgreSQL with status PENDING, APPROVED, or REJECTED.
1. When a task reaches execution, TaskExecutor calls policy.check_approval(task); if unapproved, it pauses execution and returns approval_required.
1. The final safety decision is enforced strictly on the backend inside TaskExecutor before any disk or git mutation runs.
1. Client UI approval banners merely send an approval API request; the backend validates token ownership and updates database status before continuing.

**Expected Answer Structure:**
- operations requiring approval according to ExecutionPolicy
- approval data model and state machine
- interception point in TaskExecutor
- backend enforcement guarantee independent of frontend

**Known Traps & Failure Modes:**
- Believing frontend UI controls security (the backend re-verifies approval status in TaskExecutor)
- Assuming read operations require approval (only mutations and terminal executions require approval)

---

## GB11 — Verification (L4)
**Question:** How does the backend handle an LLM claim that something does not exist in the repository? Explain the verification gate, what evidence it requires before accepting an absence claim, and what happens when prior search evidence contradicts the claim.

- **Category:** `verification`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 3, Hops: 3, Concepts: 5)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `backend/services/qa_validation.py`
- `backend/services/qa_loop.py`

**Supporting Evidence:**
- `backend/tests/services/test_stage4_fact_validation.py`
- `backend/tests/services/test_p0_fixes_verification.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/services/qa_protocol.py`

**Expected Symbols:** `validate_final_answer_against_evidence, retrieval_evidence_supports_absence, is_absence_claim, SUSPICIOUS_TERMS`

**Expected Concepts:** `Stage 4 fact validation gate, absence claim detection (direct and soft negation), targeted search requirement (zero-result searches must target entity), contradiction detection against prior search/read observations, verification retry loop and caveat attachment`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. qa_validation.py detects absence claims using regex patterns (DIRECT_NEGATION, SOFT_NEGATION) and SUSPICIOUS_TERMS (e.g. postgres, redis, auth).
1. retrieval_evidence_supports_absence checks that retrieval was actually performed: failed/errored searches are rejected as proof of absence.
1. Requires targeted searches: claiming Redis is absent requires that queries targeted 'redis' and returned zero results; searching for unrelated terms is rejected.
1. If search observations or read_file contents contain positive matches for the entity, the claim is rejected as a direct contradiction.
1. qa_loop.py prompts the LLM with validation feedback to correct the answer (up to 2 retries); if still contradicted, appends structured '> [!WARNING] Verification Caveat'.

**Expected Answer Structure:**
- absence claim detection heuristics
- targeted zero-result retrieval requirement
- contradiction detection against positive observations
- retry loop mechanism in QALoop
- fallback caveat formatting

**Known Traps & Failure Modes:**
- Assuming absence claims are accepted automatically without checking search queries
- Assuming failed tool searches count as evidence of absence (failed searches are explicitly rejected)

---

## GB12 — Architecture (L3)
**Question:** Why are repository facts/AST metadata and source code stored separately? Trace how a fact such as a symbol or file is resolved back to the actual source content, and identify the boundaries between SQL metadata and the external source/blob/worktree.

- **Category:** `architecture`
- **Answer Type:** `explanation`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `backend/models/fact_store.py`
- `backend/repository_tools/tools.py`
- `backend/routers/repo/structure.py`

**Supporting Evidence:**
- `backend/storage/azure.py`
- `backend/intelligence/store/fact_store.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/models/repository.py`

**Expected Symbols:** `FactFile, FactSymbol, read_file, get_raw_file, build_blob_key`

**Expected Concepts:** `metadata vs binary content separation, FactFile.blob_name pointing to Azure Blob Storage, PostgreSQL relational query efficiency (indexing symbols without bloating DB with large source text), immutable snapshot blobs in container gitonboard-repos, runtime source hydration via read_file or /file API`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. Storing source code directly in PostgreSQL would bloat table sizes, degrade index performance, and complicate re-analyses.
1. PostgreSQL Fact Store stores AST metadata: FactSymbol (name, line_start, line_end) and FactFile (path, size, language, blob_name).
1. Raw source files are stored immutably in Azure Blob Storage / Azurite under container 'gitonboard-repos' keyed by 'repositories/{repo_hash}/snapshots/{snapshot_id}/{path}'.
1. When source code is needed, the backend uses FactFile.path and Repository.repository_hash to fetch the blob via storage.get_object_text.
1. The /file endpoint in structure.py and read_file in tools.py slice the downloaded text using line coordinates from FactSymbol.

**Expected Answer Structure:**
- architectural rationale for separation (performance, immutability)
- PostgreSQL Fact Store schema responsibilities
- Azure Blob Storage snapshot keying
- hydration path connecting symbol coordinates to blob content

**Known Traps & Failure Modes:**
- Assuming full source code is stored in PostgreSQL TEXT or JSON columns
- Overlooking FactFile.blob_name which links PostgreSQL rows to Azure Blob Storage

---

## GB13 — Architecture (L3)
**Question:** What information does the backend place into the LLM context for a repository question, and in what order or structure? Trace how search results, source snippets, symbols, relationships, and task state become the final model input.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `backend/agent/context/assembler.py`
- `backend/agent/context/formatter.py`
- `backend/services/qa_protocol.py`

**Supporting Evidence:**
- `backend/services/qa_loop.py`
- `backend/agent/context/contracts.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/agent/context/domain.py`

**Expected Symbols:** `ContextAssembler, assemble_context, format_repository_context, SystemPromptParts, ContextBudget`

**Expected Concepts:** `token budget allocation (ContextBudget), architectural boundary constraints, relevant files, symbols, and relationships, system prompt assembly (grounding, tool catalog, RIM metadata), conversation message ordering`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. ContextAssembler.assemble_context collects evidence adhering to ContextBudget token limits.
1. Builds RepositoryUnderstandingContract: cataloged repository files, archetype constraints (Python vs TS), and relevant symbols.
1. format_repository_context formats evidence sections: Target Repository Structure, Architecture Constraints, Discovered Entities, and Relational Subgraphs.
1. qa_protocol.py constructs SystemPromptParts: Grounding instructions, Tool Catalog, and RIM metadata summary.
1. QALoop places system prompt at index 0, followed by user question, agent reasoning turns, and tool observations.

**Expected Answer Structure:**
- ContextBudget budgeting parameters
- evidence gathering stages in ContextAssembler
- markdown formatting sections in format_repository_context
- SystemPromptParts assembly in qa_protocol.py
- final message array structure passed to LLM generate

**Known Traps & Failure Modes:**
- Assuming raw database records are dumped into the prompt without formatting and budgeting
- Missing that system prompts are split into modular parts (grounding, tool catalog, RIM metadata)

---

## GB14 — Architecture (L4)
**Question:** Trace the repository indexing lifecycle from repository ingestion through parsing, fact extraction, graph construction, and searchable representations. Identify which stages are deterministic and which are used later during retrieval.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 4, Hops: 4, Concepts: 5)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `True`

**Required Evidence Files:**
- `backend/services/worker.py`
- `backend/intelligence/store/fact_store.py`
- `backend/intelligence/retrieval/semantic_builder.py`
- `backend/models/repository.py`

**Supporting Evidence:**
- `backend/intelligence/capabilities/engine.py`
- `backend/routers/repo/structure.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/task_manager.py`

**Expected Symbols:** `AnalysisWorker, save_rim_to_fact_store, SemanticIndexBuilder, Analysis, AnalysisArtifact`

**Expected Concepts:** `deterministic parsing stages (Tree-sitter CST), AnalysisWorker stage transitions (Downloading, Analyzing, Saving, Completed), Layer 6 Capability Detection, Fact Store persistence in PostgreSQL, ChromaDB semantic index generation and artifact storage`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup, cross_file_trace`

**Expected Answer Points:**
1. Stage 1: AnalysisWorker downloads repository snapshot to local storage and uploads files to Azure Blob Storage.
1. Stage 2: Deterministic Tree-sitter CST parsing extracts symbols, imports, calls, routes, and database objects into RepositoryModel.
1. Stage 3: Rule-based capability engine detects capabilities (Authentication, CRUD, Background Tasks) deterministically without LLM calls.
1. Stage 4: save_rim_to_fact_store persists entities and relationships into PostgreSQL Fact Store tables.
1. Stage 5: SemanticIndexBuilder embeds docstrings and symbols into a ChromaDB database, compressing it into an AnalysisArtifact record; Analysis status transitions to 'Completed'.

**Expected Answer Structure:**
- ingestion and blob storage snapshot
- deterministic Tree-sitter parsing and symbol extraction
- capability detection rules
- PostgreSQL Fact Store persistence
- Chroma vector indexing and artifact persistence
- status progression (Downloading -> Analyzing -> Saving -> Completed)

**Known Traps & Failure Modes:**
- Claiming LLMs parse code or extract symbols (the entire pipeline up to summary generation is 100% deterministic)
- Missing that AnalysisWorker publishes progress updates via Server-Sent Events (SSE)

---

## GB15 — Debugging (L5)
**Question:** Suppose GitOnboard retrieves the correct file entity and reports a successful source-read tool call, but the final LLM answer still claims that the source was unavailable. Enumerate the backend failure points, in execution order, that could explain this discrepancy, and specify what evidence would confirm or eliminate each one.

- **Category:** `debugging`
- **Answer Type:** `debugging`
- **Difficulty:** `L5` (Files: 5, Hops: 5, Concepts: 5)
- **Repository:** `gitonboard_backend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `backend/services/qa_loop.py`
- `backend/services/qa_protocol.py`
- `backend/repository_tools/tools.py`
- `backend/agent/context/assembler.py`

**Supporting Evidence:**
- `backend/services/qa_validation.py`
- `backend/services/tool_dispatch.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/services/structured_logger.py`

**Expected Symbols:** `QALoop, _format_tool_observation, sanitize_observation, parse_final_synthesis, read_file`

**Expected Concepts:** `observation formatting failure or empty content return, sanitize_observation stripping large content exceeding token limits, context window truncation on subsequent conversation turns, LLM protocol parsing discarding observations, telemetry checks for diagnostic isolation`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, cross_file_trace`

**Expected Answer Points:**
1. Point 1: read_file returned an error payload disguised as success: if file was >150 lines without end_line, it returned a context_overflow_protection error string instead of code.
1. Point 2: guardrails.sanitize_observation truncated or suppressed data if the result exceeded maximum observation character limits, leaving raw_text empty.
1. Point 3: _format_tool_observation failed to format the output correctly or appended insufficient character counts, leading the LLM to perceive an empty result.
1. Point 4: Conversation history truncation: in long multi-turn sessions, older tool observation turns were pruned to keep prompt size within Ollama/Groq context bounds.
1. Point 5: Protocol adapter parsing: model generated malformed output or XML tool tags that were stripped by parse_final_synthesis.
1. Diagnostic evidence: Inspect result.turns[i].tool_observation['data'] to verify exact content, check messages array length, and review structured_logger output.

**Expected Answer Structure:**
- Point 1: read_file return payload and overflow protection
- Point 2: guardrails sanitize_observation truncation
- Point 3: tool observation formatting into conversation message
- Point 4: conversation turn pruning and context limits
- Point 5: final synthesis parsing and XML stripping
- concrete diagnostic evidence for each failure mode

**Known Traps & Failure Modes:**
- Attributing the failure entirely to LLM hallucination without inspecting observation sanitization and message formatting
- Missing that context_overflow_protection returns a message rather than raising an exception

---
