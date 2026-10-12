import json
from pathlib import Path

GITONBOARD_COMMIT = "9d4de5e77ef9d4c651acfac9a58a8a81d46d6a6d"

backend_questions = [
  {
    "id": "GB01",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "Trace how a repository/analysis identifier is propagated from the agent request into retrieval and context assembly. Where could repository data leak across analyses, and what code/tests enforce isolation?",
    "category": "security",
    "answer_type": "execution_trace",
    "difficulty": "L4",
    "required_evidence": [
      "backend/agent/context/assembler.py",
      "backend/repository_tools/tools.py",
      "backend/tests/unit/test_repository_context_isolation.py"
    ],
    "supporting_evidence": [
      "backend/planning/impact_analysis.py",
      "backend/intelligence/retrieval/expansion.py",
      "backend/agent/planning/orchestrator.py",
      "backend/agent/modes.py"
    ],
    "decoy_files": [
      "backend/agent/safety/policy.py"
    ],
    "expected_symbols": [
      "ContextAssembler",
      "assemble_context",
      "RepositoryToolLayer",
      "FactFile",
      "resolve_target_repository_and_analysis"
    ],
    "expected_concepts": [
      "analysis-scoped composite keys ({analysis_id}:{entity_id})",
      "FactFile.analysis_id SQL filter isolation",
      "multi-language archetype adaptation (Python vs TS)",
      "isolated database session fixtures",
      "prevention of cross-repo concept leakage"
    ],
    "expected_answer_points": [
      "Agent requests supply repository_id and user_id, which resolve_target_repository_and_analysis maps to the latest completed analysis_id in PostgreSQL.",
      "ContextAssembler.assemble_context strictly filters all FactStore queries using FactFile.analysis_id == request.analysis_id and FactSymbol.analysis_id == request.analysis_id.",
      "RepositoryToolLayer scopes all filesystem search, read_file, and retrieval operations to the resolved analysis_id and repository snapshot hash.",
      "Data could leak if fallback queries search globally across all repositories or if domain concepts hardcode application component names.",
      "backend/tests/unit/test_repository_context_isolation.py enforces strict isolation by populating dual repositories in an isolated SQLite fixture and verifying that planning for a Python repo never leaks TypeScript files or foreign symbols."
    ],
    "expected_answer_structure": [
      "repository and analysis identifier resolution",
      "SQL query scoping across Fact Store models",
      "RepositoryToolLayer snapshot isolation",
      "potential leakage surfaces (unscoped queries, hardcoded concepts)",
      "automated test verification in test_repository_context_isolation.py"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "symbol_lookup",
      "file_read",
      "graph_traversal"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": True,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 5,
      "hops": 4,
      "concepts": 5
    },
    "known_traps": [
      "Assuming repository isolation is handled merely by system prompt instructions rather than SQL foreign-key filtering and composite keys",
      "Overlooking test_repository_context_isolation.py which explicitly validates zero-leakage contracts"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB02",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "When the agent decides it needs source code from a repository, trace the path from the repository tool call to the actual source returned to the LLM. Identify where file metadata, source/blob access, line ranges, and final context are assembled.",
    "category": "execution_flow",
    "answer_type": "execution_trace",
    "difficulty": "L4",
    "required_evidence": [
      "backend/repository_tools/tools.py",
      "backend/intelligence/retrieval/source_reader.py",
      "backend/agent/context/assembler.py"
    ],
    "supporting_evidence": [
      "backend/routers/repo/structure.py",
      "backend/storage/azure.py",
      "backend/intelligence/notebook.py"
    ],
    "decoy_files": [
      "backend/services/qa_protocol.py"
    ],
    "expected_symbols": [
      "read_file",
      "RepositorySourceReader",
      "read_source_snippet",
      "get_storage",
      "resolve_source_document",
      "truncate_semantically"
    ],
    "expected_concepts": [
      "Azure Blob snapshot key construction",
      "Repository.repository_hash resolution",
      "line slicing and clamping",
      "semantic token budget truncation",
      "Jupyter notebook source extraction"
    ],
    "expected_answer_points": [
      "Agent invokes read_file(path, start_line, end_line) through tool dispatch.",
      "RepositoryToolLayer verifies analysis_id and looks up Repository.repository_hash from PostgreSQL.",
      "Builds blob key 'repositories/{repo_hash}/snapshots/{snapshot_id}/{path}' and downloads object text via AzureBlobStorage / Azurite.",
      "resolve_source_document parses source code or converts .ipynb notebooks to standard Python representations.",
      "Applies line slicing (lines[start_line-1:end_line]) and optional semantic truncation if max_content_tokens is set, before returning to context assembly."
    ],
    "expected_answer_structure": [
      "tool call invocation and parameter validation",
      "database hash lookup and Azure blob key construction",
      "blob download and notebook normalization",
      "line slicing and context overflow protection",
      "return format to LLM observation context"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "symbol_lookup",
      "file_read",
      "cross_file_trace"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 4,
      "hops": 4,
      "concepts": 5
    },
    "known_traps": [
      "Assuming files are read directly from local git clone rather than Azure Blob Storage snapshots",
      "Missing the notebook conversion hook in resolve_source_document"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB03",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "If the frontend reports that a source read returned only lines 1–1, while the LLM says it was not given the requested source, what backend path should be inspected first? Explain how an incorrect range selection or context assembly could produce this symptom and what evidence would distinguish the possible causes.",
    "category": "debugging",
    "answer_type": "debugging",
    "difficulty": "L4",
    "required_evidence": [
      "backend/repository_tools/tools.py",
      "backend/intelligence/retrieval/source_reader.py",
      "backend/agent/context/assembler.py"
    ],
    "supporting_evidence": [
      "backend/routers/repo/structure.py",
      "backend/services/qa_loop.py"
    ],
    "decoy_files": [
      "backend/agent/context/formatter.py"
    ],
    "expected_symbols": [
      "read_file",
      "clamp_line_range",
      "read_source_snippet"
    ],
    "expected_concepts": [
      "off-by-one or default start_line=1, end_line=1 clamping",
      "context_overflow_protection early exit on large files (>150 lines without end_line)",
      "empty or whitespace-only slice extraction",
      "FactSymbol default line_start=1 fallback when AST parser misses line metadata"
    ],
    "expected_answer_points": [
      "First inspect clamp_line_range and parameter parsing in read_file: if end_line is omitted or parsed as 1, the slice defaults to 1–1.",
      "Inspect context_overflow_protection: if a file has >150 lines and end_line is missing, read_file returns an error message requesting line limits rather than source text.",
      "Inspect AST symbol extraction in FactSymbol: if line_start is null or 1 and line_end is null, context assembler requests 1–1 by default.",
      "Inspect source_reader.py: if blob content download fails or file is empty, splitlines() returns 0 or 1 line.",
      "Distinguish causes by checking tool observation logs: an error message indicates context protection, while raw_text with line 1 indicates faulty AST coordinates or line clamping."
    ],
    "expected_answer_structure": [
      "primary backend inspection points",
      "cause 1: parameter clamping and default end_line",
      "cause 2: context overflow protection on large files",
      "cause 3: AST symbol coordinate defaults in FactSymbol",
      "distinguishing telemetry evidence"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 4,
      "hops": 3,
      "concepts": 4
    },
    "known_traps": [
      "Blaming the frontend UI without checking backend clamp_line_range and context_overflow_protection",
      "Missing that FactSymbol records default line_start=1 if AST parsing fails to pinpoint end lines"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB04",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does the backend resolve which repository the agent is operating on? Trace repository resolution, authentication, mode selection/fallback, and the point at which repository-scoped context becomes available to the agent.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "backend/agent/modes.py",
      "backend/routers/agent.py",
      "backend/dependencies/auth.py"
    ],
    "supporting_evidence": [
      "backend/models/repository.py",
      "backend/agent/engineering_agent.py"
    ],
    "decoy_files": [
      "backend/routers/auth.py"
    ],
    "expected_symbols": [
      "resolve_target_repository_and_analysis",
      "get_current_user",
      "execute_explore",
      "execute_plan"
    ],
    "expected_concepts": [
      "user authentication dependency (JWT cookie/bearer)",
      "repository lookup by name/URL and user_id ownership",
      "latest analysis resolution (status='Completed')",
      "mode dispatch (explore, explain, plan, implement)",
      "injection of repository_id and analysis_id into context"
    ],
    "expected_answer_points": [
      "backend/routers/agent.py intercepts agent requests and authenticates the user via get_current_user dependency.",
      "Calls resolve_target_repository_and_analysis(db, repo_name, user_id) in backend/agent/modes.py.",
      "Queries Repository table matching user_id and repository name/URL, then finds the most recent Analysis with status='Completed'.",
      "Determines mode (explore, explain, plan, implement) from request payload or intent classifier.",
      "Instantiates ContextAssembler or QALoop passing resolved repository_id and analysis_id, making FactStore records accessible."
    ],
    "expected_answer_structure": [
      "HTTP request receipt and user authentication",
      "repository ownership validation in database",
      "latest completed analysis selection",
      "mode router dispatch and fallback",
      "context injection into agent loop"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 3,
      "hops": 3,
      "concepts": 4
    },
    "known_traps": [
      "Assuming repository resolution uses global active directory rather than user-owned database records",
      "Missing that only analyses with status='Completed' provide valid analysis_id"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB05",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How is semantic search scoped so that results from one repository/analysis cannot contaminate another? Trace the Chroma/vector-store path, collection/path construction, metadata filters, and the caller that supplies the scope.",
    "category": "security",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "backend/routers/repo/semantic.py",
      "backend/intelligence/retrieval/retriever.py",
      "backend/models/repository.py"
    ],
    "supporting_evidence": [
      "backend/intelligence/retrieval/semantic_builder.py"
    ],
    "decoy_files": [
      "backend/intelligence/retrieval/lexical.py"
    ],
    "expected_symbols": [
      "get_chroma_collection",
      "CHROMA_BASE_DIR",
      "AnalysisArtifact",
      "HybridRetriever"
    ],
    "expected_concepts": [
      "hierarchical filesystem partitioning (/tmp/chroma/user_{uid}/repo_{rid}/analysis_{aid})",
      "AnalysisArtifact storage in PostgreSQL (type='semantic_index_db')",
      "zip extraction into isolated analysis directory",
      "metadata filtering on file_path and symbol",
      "analysis_id parameter propagation"
    ],
    "expected_answer_points": [
      "backend/routers/repo/semantic.py enforces isolated Chroma directories via CHROMA_BASE_DIR / f'user_{user_id}' / f'repo_{repo_id}' / f'analysis_{analysis_id}'.",
      "If not present locally, downloads the pre-built semantic index artifact (type='semantic_index_db') from PostgreSQL AnalysisArtifact table and unzips it into the analysis directory.",
      "PersistentClient opens only the specific collection 'semantic_index' in that isolated directory.",
      "HybridRetriever receives the scoped Chroma collection and analysis_id, ensuring vector queries only search within that snapshot.",
      "Vector metadata includes file_path and symbol name, mapped back to FactSymbol and FactFile rows for that analysis."
    ],
    "expected_answer_structure": [
      "directory-level path partitioning scheme",
      "AnalysisArtifact database persistence and on-demand unpack",
      "Chroma PersistentClient instantiation",
      "HybridRetriever integration",
      "metadata verification and isolation guarantee"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 4,
      "hops": 3,
      "concepts": 4
    },
    "known_traps": [
      "Assuming Chroma runs as a shared multi-tenant cloud service with metadata tags rather than partitioned persistent local directories and DB artifacts",
      "Missing that AnalysisArtifact stores compressed Chroma databases directly in PostgreSQL"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB06",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "Explain how GitOnboard combines exact/entity retrieval, lexical/code-aware retrieval, semantic retrieval, and rank fusion before results reach the agent. Which retrieval signals complement each other, and where is the final ranking/merging performed?",
    "category": "retrieval",
    "answer_type": "architecture",
    "difficulty": "L4",
    "required_evidence": [
      "backend/intelligence/retrieval/retriever.py",
      "backend/intelligence/retrieval/fusion.py",
      "backend/intelligence/retrieval/lexical.py"
    ],
    "supporting_evidence": [
      "backend/routers/repo/semantic.py",
      "backend/models/fact_store.py"
    ],
    "decoy_files": [
      "backend/intelligence/retrieval/source_reader.py"
    ],
    "expected_symbols": [
      "HybridRetriever",
      "reciprocal_rank_fusion",
      "retrieve",
      "LexicalRetriever",
      "FactSymbol"
    ],
    "expected_concepts": [
      "Reciprocal Rank Fusion (RRF with k=60)",
      "exact symbol lookup (FactSymbol with exact_weight=1.2)",
      "BM25 / lexical token matching (lexical_weight=1.0)",
      "Chroma semantic embedding distance (semantic_weight=1.0)",
      "structural expansion over FactRelationship"
    ],
    "expected_answer_points": [
      "HybridRetriever coordinates three independent retrieval signals: exact entity matching from PostgreSQL FactSymbol, lexical token search via BM25/LexicalRetriever, and vector embedding similarity via Chroma collection.",
      "Exact matching captures identifier names with high precision; lexical matching captures comments and string occurrences; semantic matching captures conceptual descriptions.",
      "Results are unified using Reciprocal Rank Fusion (reciprocal_rank_fusion in fusion.py) with formula: RRF_score = sum(weight / (k + rank)).",
      "Optionally expands candidates using FactRelationship (CALLS, IMPORTS) to include adjacent structural dependencies.",
      "Returns ranked items sorted by rrf_score to context assembly or QA loop."
    ],
    "expected_answer_structure": [
      "the three retrieval signals and their complementarities",
      "exact matching via FactStore",
      "lexical and semantic retriever queries",
      "Reciprocal Rank Fusion algorithm and parameter k=60",
      "structural relationship expansion and final sorting"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup",
      "graph_traversal"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": True,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 4,
      "hops": 4,
      "concepts": 5
    },
    "known_traps": [
      "Describing generic RAG instead of GitOnboard's concrete HybridRetriever and reciprocal_rank_fusion implementation",
      "Forgetting that exact symbol matches receive higher weight (1.2) than lexical/semantic (1.0)"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB07",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does the backend turn parsed repository information into a knowledge graph? Trace AST parsing into symbols/entities and then into relationships such as imports, calls, inheritance, or file ownership. Identify where the graph is persisted and queried.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L4",
    "required_evidence": [
      "backend/intelligence/store/fact_store.py",
      "backend/models/fact_store.py",
      "backend/agent/graph/builder.py"
    ],
    "supporting_evidence": [
      "backend/intelligence/retrieval/graph_traverser.py",
      "backend/services/tool_dispatch.py"
    ],
    "decoy_files": [
      "backend/agent/graph/state.py"
    ],
    "expected_symbols": [
      "save_rim_to_fact_store",
      "FactRelationship",
      "FactSymbol",
      "FactFile",
      "AgentGraphBuilder",
      "FactStoreGraphTraverser"
    ],
    "expected_concepts": [
      "Tree-sitter CST parsing to RepositoryModel",
      "relational Fact Store tables (files, symbols, relationships)",
      "relationship types (CONTAINS, CALLS, IMPORTS, INHERITS)",
      "composite keys ({analysis_id}:{entity_id})",
      "graph traversal in FactStoreGraphTraverser"
    ],
    "expected_answer_points": [
      "Tree-sitter parser extracts symbols (functions, classes, methods) and static AST references into an in-memory RepositoryModel.",
      "save_rim_to_fact_store in fact_store.py persists the model into PostgreSQL: files into FactFile, entities into FactSymbol, and edges into FactRelationship.",
      "FactRelationship stores from_symbol_id, to_symbol_id, rel_type (CALLS, IMPORTS, INHERITS, CONTAINS), and evidence_line/evidence_snippet.",
      "Composite IDs enforce strict analysis isolation.",
      "AgentGraphBuilder and FactStoreGraphTraverser query FactRelationship to build bounded subgraphs and navigate caller/callee paths."
    ],
    "expected_answer_structure": [
      "AST extraction into RepositoryModel entities",
      "persistence to PostgreSQL Fact Store tables",
      "FactRelationship schema and edge types",
      "querying and traversal mechanisms (FactStoreGraphTraverser, AgentGraphBuilder)"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "symbol_lookup",
      "file_read",
      "graph_traversal"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": True,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 4,
      "hops": 4,
      "concepts": 5
    },
    "known_traps": [
      "Assuming a graph database like Neo4j is used (GitOnboard persists graphs directly into PostgreSQL relational FactRelationship tables)",
      "Missing composite ID format {analysis_id}:{entity_id}"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB08",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "Given a request to change a function, how does the backend determine potentially affected files or symbols? Trace the impact-analysis algorithm and identify which graph relationships it relies on and how the result is passed into planning.",
    "category": "impact_analysis",
    "answer_type": "execution_trace",
    "difficulty": "L4",
    "required_evidence": [
      "backend/planning/impact_analysis.py",
      "backend/models/fact_store.py",
      "backend/agent/planning/orchestrator.py"
    ],
    "supporting_evidence": [
      "backend/agent/graph/builder.py",
      "backend/planning/requirements.py"
    ],
    "decoy_files": [
      "backend/planning/change_classifier.py"
    ],
    "expected_symbols": [
      "ImpactAnalyzer",
      "analyze_impact",
      "FactRelationship",
      "PlanningOrchestrator"
    ],
    "expected_concepts": [
      "multi-hop dependency traversal",
      "relationship types (CALLS, IMPORTS, INHERITS, QUERIES)",
      "blast radius calculation",
      "affected symbols and files aggregation",
      "task dependency injection in PlanningOrchestrator"
    ],
    "expected_answer_points": [
      "ImpactAnalyzer.analyze_impact receives target symbol(s) and analysis_id.",
      "Queries PostgreSQL FactRelationship for reverse CALLS (callers), reverse IMPORTS (dependent modules), and INHERITS (subclasses).",
      "Performs bounded depth traversal (typically depth 1–3) to calculate upstream blast radius.",
      "Aggregates unique affected file paths and caller symbols into an ImpactReport.",
      "PlanningOrchestrator consumes the ImpactReport to generate implementation tasks, ordering modifications before dependent test updates."
    ],
    "expected_answer_structure": [
      "input target symbol and analysis context",
      "graph traversal across CALLS/IMPORTS/INHERITS edges",
      "blast radius calculation and cycle prevention",
      "ImpactReport structure",
      "planning task generation and sequencing"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "symbol_lookup",
      "file_read",
      "graph_traversal"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": True,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 4,
      "hops": 4,
      "concepts": 5
    },
    "known_traps": [
      "Assuming impact analysis only looks at file imports (it traverses function CALLS and class INHERITS)",
      "Overlooking how PlanningOrchestrator translates affected files into structured task dependencies"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB09",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "What is the responsibility boundary between TaskOrchestrator, TaskExecutor, and the engineering-agent loop? Trace one task from planning to execution and explain which component decides what should happen versus which component performs the work.",
    "category": "architecture",
    "answer_type": "architecture",
    "difficulty": "L3",
    "required_evidence": [
      "backend/agent/tasks/orchestrator.py",
      "backend/agent/tasks/executor.py",
      "backend/agent/engineering_agent.py"
    ],
    "supporting_evidence": [
      "backend/agent/tasks/state_machine.py",
      "backend/routers/agent.py"
    ],
    "decoy_files": [
      "backend/services/worker.py"
    ],
    "expected_symbols": [
      "TaskOrchestrator",
      "TaskExecutor",
      "EngineeringAgent",
      "TaskStateMachine"
    ],
    "expected_concepts": [
      "separation of planning vs execution",
      "topological task dependency resolution",
      "task state transitions (PENDING -> RUNNING -> COMPLETED)",
      "tool execution delegation",
      "approval gate interception"
    ],
    "expected_answer_points": [
      "EngineeringAgent is the overarching controller managing agent lifecycle, state transitions (UNDERSTANDING -> PLANNING -> EXECUTING), and user interactions.",
      "TaskOrchestrator manages the task graph: parses dependencies, determines execution order (topological sort), and evaluates preconditions.",
      "TaskExecutor executes individual task units: dispatches tool operations, monitors output, and reports success/failure back to TaskStateMachine.",
      "TaskOrchestrator decides WHAT tasks should run and WHEN, while TaskExecutor performs the actual code or tool modifications.",
      "If a task requires approval, TaskOrchestrator halts execution and requests user consent before passing the task to TaskExecutor."
    ],
    "expected_answer_structure": [
      "EngineeringAgent high-level coordinator role",
      "TaskOrchestrator planning and dependency role",
      "TaskExecutor work execution and tool dispatch role",
      "state transition flow across TaskStateMachine",
      "concrete execution trace of one task"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 4,
      "hops": 3,
      "concepts": 4
    },
    "known_traps": [
      "Conflating TaskOrchestrator with PlanningOrchestrator (planning creates the plan; TaskOrchestrator executes tasks)",
      "Assuming TaskExecutor decides task order (order is strictly governed by TaskOrchestrator dependencies)"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB10",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "Which backend operations require approval before execution, how is approval state represented, and where is the final safety decision enforced? Trace the request through the approval mechanism to the executor.",
    "category": "security",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "backend/agent/safety/approval.py",
      "backend/agent/safety/policy.py",
      "backend/agent/tasks/executor.py"
    ],
    "supporting_evidence": [
      "backend/models/implementation.py",
      "backend/routers/agent.py"
    ],
    "decoy_files": [
      "backend/agent/safety/cancellation.py"
    ],
    "expected_symbols": [
      "ApprovalController",
      "ExecutionPolicy",
      "requires_approval",
      "TaskExecutor"
    ],
    "expected_concepts": [
      "mutation operations requiring approval (code writes, deletions, command execution)",
      "ApprovalStatus (PENDING, APPROVED, REJECTED)",
      "backend policy evaluation in ExecutionPolicy",
      "enforcement at TaskExecutor pre-execution gate",
      "prevention of UI client spoofing"
    ],
    "expected_answer_points": [
      "ExecutionPolicy in policy.py classifies actions: read/inspection operations are auto-approved, while file mutations, file creations, and shell executions require explicit user approval.",
      "ApprovalController manages approval requests, storing them in PostgreSQL with status PENDING, APPROVED, or REJECTED.",
      "When a task reaches execution, TaskExecutor calls policy.check_approval(task); if unapproved, it pauses execution and returns approval_required.",
      "The final safety decision is enforced strictly on the backend inside TaskExecutor before any disk or git mutation runs.",
      "Client UI approval banners merely send an approval API request; the backend validates token ownership and updates database status before continuing."
    ],
    "expected_answer_structure": [
      "operations requiring approval according to ExecutionPolicy",
      "approval data model and state machine",
      "interception point in TaskExecutor",
      "backend enforcement guarantee independent of frontend"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 4,
      "hops": 3,
      "concepts": 4
    },
    "known_traps": [
      "Believing frontend UI controls security (the backend re-verifies approval status in TaskExecutor)",
      "Assuming read operations require approval (only mutations and terminal executions require approval)"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB11",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does the backend handle an LLM claim that something does not exist in the repository? Explain the verification gate, what evidence it requires before accepting an absence claim, and what happens when prior search evidence contradicts the claim.",
    "category": "verification",
    "answer_type": "execution_trace",
    "difficulty": "L4",
    "required_evidence": [
      "backend/services/qa_validation.py",
      "backend/services/qa_loop.py"
    ],
    "supporting_evidence": [
      "backend/tests/services/test_stage4_fact_validation.py",
      "backend/tests/services/test_p0_fixes_verification.py"
    ],
    "decoy_files": [
      "backend/services/qa_protocol.py"
    ],
    "expected_symbols": [
      "validate_final_answer_against_evidence",
      "retrieval_evidence_supports_absence",
      "is_absence_claim",
      "SUSPICIOUS_TERMS"
    ],
    "expected_concepts": [
      "Stage 4 fact validation gate",
      "absence claim detection (direct and soft negation)",
      "targeted search requirement (zero-result searches must target entity)",
      "contradiction detection against prior search/read observations",
      "verification retry loop and caveat attachment"
    ],
    "expected_answer_points": [
      "qa_validation.py detects absence claims using regex patterns (DIRECT_NEGATION, SOFT_NEGATION) and SUSPICIOUS_TERMS (e.g. postgres, redis, auth).",
      "retrieval_evidence_supports_absence checks that retrieval was actually performed: failed/errored searches are rejected as proof of absence.",
      "Requires targeted searches: claiming Redis is absent requires that queries targeted 'redis' and returned zero results; searching for unrelated terms is rejected.",
      "If search observations or read_file contents contain positive matches for the entity, the claim is rejected as a direct contradiction.",
      "qa_loop.py prompts the LLM with validation feedback to correct the answer (up to 2 retries); if still contradicted, appends structured '> [!WARNING] Verification Caveat'."
    ],
    "expected_answer_structure": [
      "absence claim detection heuristics",
      "targeted zero-result retrieval requirement",
      "contradiction detection against positive observations",
      "retry loop mechanism in QALoop",
      "fallback caveat formatting"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 3,
      "hops": 3,
      "concepts": 5
    },
    "known_traps": [
      "Assuming absence claims are accepted automatically without checking search queries",
      "Assuming failed tool searches count as evidence of absence (failed searches are explicitly rejected)"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB12",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "Why are repository facts/AST metadata and source code stored separately? Trace how a fact such as a symbol or file is resolved back to the actual source content, and identify the boundaries between SQL metadata and the external source/blob/worktree.",
    "category": "architecture",
    "answer_type": "explanation",
    "difficulty": "L3",
    "required_evidence": [
      "backend/models/fact_store.py",
      "backend/repository_tools/tools.py",
      "backend/routers/repo/structure.py"
    ],
    "supporting_evidence": [
      "backend/storage/azure.py",
      "backend/intelligence/store/fact_store.py"
    ],
    "decoy_files": [
      "backend/models/repository.py"
    ],
    "expected_symbols": [
      "FactFile",
      "FactSymbol",
      "read_file",
      "get_raw_file",
      "build_blob_key"
    ],
    "expected_concepts": [
      "metadata vs binary content separation",
      "FactFile.blob_name pointing to Azure Blob Storage",
      "PostgreSQL relational query efficiency (indexing symbols without bloating DB with large source text)",
      "immutable snapshot blobs in container gitonboard-repos",
      "runtime source hydration via read_file or /file API"
    ],
    "expected_answer_points": [
      "Storing source code directly in PostgreSQL would bloat table sizes, degrade index performance, and complicate re-analyses.",
      "PostgreSQL Fact Store stores AST metadata: FactSymbol (name, line_start, line_end) and FactFile (path, size, language, blob_name).",
      "Raw source files are stored immutably in Azure Blob Storage / Azurite under container 'gitonboard-repos' keyed by 'repositories/{repo_hash}/snapshots/{snapshot_id}/{path}'.",
      "When source code is needed, the backend uses FactFile.path and Repository.repository_hash to fetch the blob via storage.get_object_text.",
      "The /file endpoint in structure.py and read_file in tools.py slice the downloaded text using line coordinates from FactSymbol."
    ],
    "expected_answer_structure": [
      "architectural rationale for separation (performance, immutability)",
      "PostgreSQL Fact Store schema responsibilities",
      "Azure Blob Storage snapshot keying",
      "hydration path connecting symbol coordinates to blob content"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 4,
      "hops": 3,
      "concepts": 4
    },
    "known_traps": [
      "Assuming full source code is stored in PostgreSQL TEXT or JSON columns",
      "Overlooking FactFile.blob_name which links PostgreSQL rows to Azure Blob Storage"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB13",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "What information does the backend place into the LLM context for a repository question, and in what order or structure? Trace how search results, source snippets, symbols, relationships, and task state become the final model input.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "backend/agent/context/assembler.py",
      "backend/agent/context/formatter.py",
      "backend/services/qa_protocol.py"
    ],
    "supporting_evidence": [
      "backend/services/qa_loop.py",
      "backend/agent/context/contracts.py"
    ],
    "decoy_files": [
      "backend/agent/context/domain.py"
    ],
    "expected_symbols": [
      "ContextAssembler",
      "assemble_context",
      "format_repository_context",
      "SystemPromptParts",
      "ContextBudget"
    ],
    "expected_concepts": [
      "token budget allocation (ContextBudget)",
      "architectural boundary constraints",
      "relevant files, symbols, and relationships",
      "system prompt assembly (grounding, tool catalog, RIM metadata)",
      "conversation message ordering"
    ],
    "expected_answer_points": [
      "ContextAssembler.assemble_context collects evidence adhering to ContextBudget token limits.",
      "Builds RepositoryUnderstandingContract: cataloged repository files, archetype constraints (Python vs TS), and relevant symbols.",
      "format_repository_context formats evidence sections: Target Repository Structure, Architecture Constraints, Discovered Entities, and Relational Subgraphs.",
      "qa_protocol.py constructs SystemPromptParts: Grounding instructions, Tool Catalog, and RIM metadata summary.",
      "QALoop places system prompt at index 0, followed by user question, agent reasoning turns, and tool observations."
    ],
    "expected_answer_structure": [
      "ContextBudget budgeting parameters",
      "evidence gathering stages in ContextAssembler",
      "markdown formatting sections in format_repository_context",
      "SystemPromptParts assembly in qa_protocol.py",
      "final message array structure passed to LLM generate"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 4,
      "hops": 3,
      "concepts": 4
    },
    "known_traps": [
      "Assuming raw database records are dumped into the prompt without formatting and budgeting",
      "Missing that system prompts are split into modular parts (grounding, tool catalog, RIM metadata)"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB14",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "Trace the repository indexing lifecycle from repository ingestion through parsing, fact extraction, graph construction, and searchable representations. Identify which stages are deterministic and which are used later during retrieval.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L4",
    "required_evidence": [
      "backend/services/worker.py",
      "backend/intelligence/store/fact_store.py",
      "backend/intelligence/retrieval/semantic_builder.py",
      "backend/models/repository.py"
    ],
    "supporting_evidence": [
      "backend/intelligence/capabilities/engine.py",
      "backend/routers/repo/structure.py"
    ],
    "decoy_files": [
      "backend/task_manager.py"
    ],
    "expected_symbols": [
      "AnalysisWorker",
      "save_rim_to_fact_store",
      "SemanticIndexBuilder",
      "Analysis",
      "AnalysisArtifact"
    ],
    "expected_concepts": [
      "deterministic parsing stages (Tree-sitter CST)",
      "AnalysisWorker stage transitions (Downloading, Analyzing, Saving, Completed)",
      "Layer 6 Capability Detection",
      "Fact Store persistence in PostgreSQL",
      "ChromaDB semantic index generation and artifact storage"
    ],
    "expected_answer_points": [
      "Stage 1: AnalysisWorker downloads repository snapshot to local storage and uploads files to Azure Blob Storage.",
      "Stage 2: Deterministic Tree-sitter CST parsing extracts symbols, imports, calls, routes, and database objects into RepositoryModel.",
      "Stage 3: Rule-based capability engine detects capabilities (Authentication, CRUD, Background Tasks) deterministically without LLM calls.",
      "Stage 4: save_rim_to_fact_store persists entities and relationships into PostgreSQL Fact Store tables.",
      "Stage 5: SemanticIndexBuilder embeds docstrings and symbols into a ChromaDB database, compressing it into an AnalysisArtifact record; Analysis status transitions to 'Completed'."
    ],
    "expected_answer_structure": [
      "ingestion and blob storage snapshot",
      "deterministic Tree-sitter parsing and symbol extraction",
      "capability detection rules",
      "PostgreSQL Fact Store persistence",
      "Chroma vector indexing and artifact persistence",
      "status progression (Downloading -> Analyzing -> Saving -> Completed)"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "file_read",
      "symbol_lookup",
      "cross_file_trace"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": True,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 4,
      "hops": 4,
      "concepts": 5
    },
    "known_traps": [
      "Claiming LLMs parse code or extract symbols (the entire pipeline up to summary generation is 100% deterministic)",
      "Missing that AnalysisWorker publishes progress updates via Server-Sent Events (SSE)"
    ],
    "ground_truth_status": "verified"
  },
  {
    "id": "GB15",
    "repository": "gitonboard_backend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "Suppose GitOnboard retrieves the correct file entity and reports a successful source-read tool call, but the final LLM answer still claims that the source was unavailable. Enumerate the backend failure points, in execution order, that could explain this discrepancy, and specify what evidence would confirm or eliminate each one.",
    "category": "debugging",
    "answer_type": "debugging",
    "difficulty": "L5",
    "required_evidence": [
      "backend/services/qa_loop.py",
      "backend/services/qa_protocol.py",
      "backend/repository_tools/tools.py",
      "backend/agent/context/assembler.py"
    ],
    "supporting_evidence": [
      "backend/services/qa_validation.py",
      "backend/services/tool_dispatch.py"
    ],
    "decoy_files": [
      "backend/services/structured_logger.py"
    ],
    "expected_symbols": [
      "QALoop",
      "_format_tool_observation",
      "sanitize_observation",
      "parse_final_synthesis",
      "read_file"
    ],
    "expected_concepts": [
      "observation formatting failure or empty content return",
      "sanitize_observation stripping large content exceeding token limits",
      "context window truncation on subsequent conversation turns",
      "LLM protocol parsing discarding observations",
      "telemetry checks for diagnostic isolation"
    ],
    "expected_answer_points": [
      "Point 1: read_file returned an error payload disguised as success: if file was >150 lines without end_line, it returned a context_overflow_protection error string instead of code.",
      "Point 2: guardrails.sanitize_observation truncated or suppressed data if the result exceeded maximum observation character limits, leaving raw_text empty.",
      "Point 3: _format_tool_observation failed to format the output correctly or appended insufficient character counts, leading the LLM to perceive an empty result.",
      "Point 4: Conversation history truncation: in long multi-turn sessions, older tool observation turns were pruned to keep prompt size within Ollama/Groq context bounds.",
      "Point 5: Protocol adapter parsing: model generated malformed output or XML tool tags that were stripped by parse_final_synthesis.",
      "Diagnostic evidence: Inspect result.turns[i].tool_observation['data'] to verify exact content, check messages array length, and review structured_logger output."
    ],
    "expected_answer_structure": [
      "Point 1: read_file return payload and overflow protection",
      "Point 2: guardrails sanitize_observation truncation",
      "Point 3: tool observation formatting into conversation message",
      "Point 4: conversation turn pruning and context limits",
      "Point 5: final synthesis parsing and XML stripping",
      "concrete diagnostic evidence for each failure mode"
    ],
    "expected_tool_capabilities": [
      "repository_search",
      "symbol_lookup",
      "file_read",
      "cross_file_trace"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 5,
      "hops": 5,
      "concepts": 5
    },
    "known_traps": [
      "Attributing the failure entirely to LLM hallucination without inspecting observation sanitization and message formatting",
      "Missing that context_overflow_protection returns a message rather than raising an exception"
    ],
    "ground_truth_status": "verified"
  }
]

out_path = Path("benchmark/gitonboard_backend_benchmark.json")
out_path.write_text(json.dumps(backend_questions, indent=2), encoding="utf-8")
print(f"Successfully generated {out_path} with {len(backend_questions)} questions")
