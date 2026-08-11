# GitOnboard — Final Architecture Document
**Version:** 1.0 (Frozen)  
**Date:** 2026-08-06  
**Status:** Architecture Complete — Implementation Phase

---

## 1. Product Definition

GitOnboard is a **Repository Intelligence Platform** that compiles a software repository into a structured Repository Intelligence Model (RIM), enabling deterministic repository understanding, architecture exploration, impact analysis, onboarding, documentation, and AI-powered explanations.

**The product is not an AI chatbot. The product is the platform. AI is one consumer of the platform.**

---

## 2. Core Philosophy

### Traditional Repository AI
```
Repository → Chunks → Embeddings → LLM
```

### GitOnboard
```
Repository → Static Analysis → RIM → Query Engine → Applications
```

### Principles
1. **Facts are the ground truth.** Graphs, summaries, and embeddings are derived views.
2. **The RIM is the single source of truth.** Nothing bypasses it.
3. **AI never discovers repository knowledge.** AI only explains, summarizes, teaches, and documents.
4. **Everything is evidence-based.** Every relationship and derived object must be traceable to extracted facts.
5. **Derive on demand.** Persist only facts, the RIM, and capability objects. Generate graphs, views, and documentation at query time.

---

## 3. Scope

### Included
- Repository understanding via static analysis
- Architecture exploration
- Execution tracing
- Impact analysis
- Documentation generation
- AI explanation and tutoring
- Onboarding assistance

### Not Included (Future Work)
- Bug prediction
- Code generation / completion
- Autonomous coding agents
- Automatic code review
- Security vulnerability detection
- Runtime profiling / live debugging
- Performance optimization
- CI/CD automation
- Git history evolution analysis
- Enterprise-scale analytics

### Supported Languages & Frameworks
- **Version 1:** Python only
- **Frameworks:** FastAPI (primary), Flask (secondary)
- **If time permits:** Java (Spring Boot)
- **Explicitly out of scope:** JavaScript, Go, Rust, C#, etc.

---

## 4. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        INTERFACES                           │
│  Architecture    Search    Documentation    AI Interfaces   │
│  Explorer       Explorer   Generator        (Chat/Tutor)    │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              REPOSITORY QUERY ENGINE                        │
│  findDefinition()  findCallers()  traceExecution()          │
│  findFeature()     findRoutes()   impactAnalysis()          │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│           CAPABILITY DETECTION ENGINE                       │
│  Rule-based assembly of higher-level objects from facts     │
│  Authentication, CRUD, Background Tasks, File Upload        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│         REPOSITORY INTELLIGENCE MODEL (RIM)                 │
│  Canonical structured model of the repository               │
│  Symbols, relationships, locations, metadata                │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    FACT STORE                               │
│  Canonical relational storage of extracted facts            │
│  SQLite / PostgreSQL                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              STATIC ANALYSIS ENGINE                         │
│  AST traversal → Fact extraction (deterministic)            │
│  Tree-sitter (default) + Language plugins (enrichment)      │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              REPOSITORY LOADER                              │
│  Clone / local read → Language detection → Framework detect │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Layer Specifications

### Layer 1: Repository Loader
**Responsibilities:**
- Clone or read local repository
- Detect language (Python only in V1)
- Detect framework (FastAPI/Flask heuristics)
- Collect metadata (path, commit hash, timestamp)

**Output:** Repository metadata object with `repo_id`, `commit_hash`, `root_path`, `detected_framework`.

---

### Layer 2: Parsing Layer
**Responsibilities:** Produce syntax trees and tokens. No semantics yet.

**Components:**
- **Tree-sitter** (default): Generates CST for all Python files
- **Language Plugins** (enrichment): Framework-specific semantic extraction (FastAPI decorators, Flask routes)

**Output:** Per-file AST with source locations.

---

### Layer 3: Static Analysis Engine
**Responsibilities:** Extract deterministic facts from AST.

**Extracted facts:**
- Files and directories
- Classes, functions, methods
- Variables and parameters
- Import statements
- Call sites
- Inheritance relationships
- Decorators
- API routes (framework-specific)
- Database access patterns (ORM queries)
- Configuration and environment variables
- Test functions

**Output:** Fact stream → Fact Store.

---

### Layer 4: Fact Store
**Responsibilities:** Canonical persistent storage.

**Storage:** SQLite (default) or PostgreSQL if already required by application.

**Core Tables:**

```sql
-- Repositories
repositories (
    id TEXT PRIMARY KEY,
    name TEXT,
    url TEXT,
    root_path TEXT,
    commit_hash TEXT,
    analyzed_at TIMESTAMP,
    parser_version TEXT
);

-- Files
files (
    id TEXT PRIMARY KEY,
    repo_id TEXT,
    path TEXT,
    language TEXT,
    content_hash TEXT,
    last_modified TIMESTAMP
);

-- Symbols (stable identity)
symbols (
    id TEXT PRIMARY KEY,           -- stable_id, not random UUID
    file_id TEXT,
    name TEXT,
    qualified_name TEXT,
    symbol_type TEXT,              -- function, class, method, variable, route
    line_start INTEGER,
    line_end INTEGER,
    signature_hash TEXT,           -- for identity stability
    metadata JSON
);

-- Relationships (ground truth)
relationships (
    id TEXT PRIMARY KEY,
    from_symbol_id TEXT,
    to_symbol_id TEXT,
    rel_type TEXT,                 -- CONTAINS, CALLS, IMPORTS, INHERITS, 
                                   -- READS, WRITES, USES, EXPOSES, DECLARES,
                                   -- HANDLED_BY, QUERIES
    evidence_line INTEGER,
    evidence_snippet TEXT,
    status TEXT,                   -- CONFIRMED, INFERRED, UNRESOLVED
    created_at TIMESTAMP
);

-- Framework-specific
routes (
    id TEXT PRIMARY KEY,
    symbol_id TEXT,
    method TEXT,
    path TEXT,
    handler_symbol_id TEXT
);

database_objects (
    id TEXT PRIMARY KEY,
    symbol_id TEXT,
    object_type TEXT,
    name TEXT
);

-- Capabilities (derived, deterministic)
capabilities (
    id TEXT PRIMARY KEY,
    name TEXT,                     -- Authentication, CRUD, FileUpload
    capability_type TEXT,
    status TEXT,                   -- CONFIRMED, INFERRED
    evidence_summary TEXT
);

capability_members (
    capability_id TEXT,
    symbol_id TEXT,
    role TEXT,                     -- entry_point, service, repository, table
    evidence_id TEXT
);

-- Evidence registry
evidence (
    id TEXT PRIMARY KEY,
    fact_type TEXT,
    symbol_id TEXT,
    details TEXT,
    location TEXT
);
```

**Key rule:** No graphs stored here. Relationships are rows. Graphs are views.

---

### Layer 5: Repository Intelligence Model (RIM)
**Responsibilities:** In-memory representation and API over the Fact Store.

**Node types:**
- Repository, Module, Package, Directory, File
- Class, Function, Method, Variable
- Route, Database Table, Configuration, Environment Variable

**Relationship types:**
- `CONTAINS` (directory → file, class → method)
- `CALLS` (function → function)
- `IMPORTS` (file → module)
- `INHERITS` (class → class)
- `IMPLEMENTS` (class → interface)
- `READS` / `WRITES` (function → variable)
- `USES` (function → configuration)
- `EXPOSES` (module → route)
- `DECLARES` (file → symbol)
- `HANDLED_BY` (route → function)
- `QUERIES` (function → database table)

**Stable Identity Formula:**
```
stable_id = hash(repo_id + ":" + file_path + ":" + qualified_name + ":" + signature_hash)
```

Why: Line numbers change. File content changes. But `qualified_name + signature_hash` identifies the same logical symbol across incremental updates.

---

### Layer 6: Capability Detection Engine
**Responsibilities:** Assemble higher-level capability objects from deterministic facts via explicit rules.

**Not:** Machine learning, clustering, or AI inference.

**Example rule (Authentication):**
```
IF route.path MATCHES "/auth/*" OR "/login" OR "/logout"
   AND handler.calls CONTAINS "verify_password" OR "check_credentials"
   AND handler.queries CONTAINS "users" OR "credentials"
THEN emit Capability("Authentication")
     WITH members: [route, handler, service, table]
     WITH evidence: [route_id, handler_id, table_id]
```

**Capabilities V1:**
- Authentication
- CRUD (Create, Read, Update, Delete)
- Background Tasks
- File Upload

**Implementation:** Hardcoded Python functions per framework. No generic DSL in V1.

---

### Layer 7: Repository Query Engine
**Responsibilities:** The only API through which consumers access intelligence.

**Core APIs:**
```python
findDefinition(symbol_id) -> Symbol
findCallers(symbol_id) -> List[Symbol]
findCallees(symbol_id) -> List[Symbol]
findDependencies(symbol_id) -> List[Symbol]
findCapability(name) -> Capability
traceExecution(route_id) -> ExecutionPath
findRoutes() -> List[Route]
findDatabaseFlow(function_id) -> List[DatabaseObject]
impactAnalysis(symbol_id) -> ImpactReport
```

**Rule:** No consumer queries the Fact Store or RIM directly. Everything goes through this engine.

---

### Layer 8: Applications (Interfaces)
All applications consume the Query Engine only.

| Application | Function |
|-------------|----------|
| **Architecture Explorer** | Visualize modules, packages, dependencies, call graphs |
| **Feature Explorer** | Browse capabilities (Authentication, CRUD) with members and evidence |
| **Search** | Symbol search, graph expansion, hybrid semantic search (embeddings for ranking only) |
| **Execution Replay** | Select route → visualize step-by-step execution path |
| **Impact Analysis** | Select symbol → see affected routes, services, tests, capabilities |
| **Documentation Generator** | Generate README, architecture docs, Mermaid diagrams, API docs |
| **AI Interfaces** | Repository Chat, Architecture Tutor, Onboarding Assistant |

---

## 6. AI Pipeline
```
User Question
    ↓
Intent Detection (rule-based)
    ↓
Planner (selects query engine operations)
    ↓
Repository Query Engine
    ↓
Evidence Collection
    ↓
Context Builder (assembles evidence + representative code)
    ↓
LLM (explains only)
    ↓
Evidence-backed Response
```

**AI never retrieves. AI never reasons over raw repositories. AI only explains deterministic evidence.**

---

## 7. Incremental Update Pipeline
```
File Changed (git diff / file watcher)
    ↓
Hash Check (content_hash unchanged → skip)
    ↓
Reparse File (Tree-sitter)
    ↓
Extract Facts (Static Analysis)
    ↓
Fact Diff (compare with previous facts for this file)
    ↓
Update RIM (create / update / delete nodes)
    ↓
Cascade Relationship Updates (delete stale, create new)
    ↓
Re-evaluate Affected Capabilities (only if member symbols changed)
    ↓
Invalidate Derived Views (mark stale, regenerate on next query)
```

**Key principle:** Diff facts, not ASTs. The RIM is independent of parser implementation.

---

## 8. Failure Modes & Limitations
Static analysis cannot resolve:
- Dynamic imports (`__import__`, `importlib`)
- Runtime metaprogramming (`setattr`, `type()`, `eval()`, `exec()`)
- String-based route registration (`app.route(f"/{dynamic_path}")`)
- Reflection and monkey-patching
- Conditional imports inside functions

**Our approach:**
- Extract what is statically determinable
- Mark unresolved references as `status = UNRESOLVED`
- Never guess dynamic behavior
- Document limitations explicitly

---

## 9. Validation Strategy
### 9.1 Ground Truth Tests
Select 3–5 small Python repositories. For each, create expected outputs:
- Expected routes
- Expected capabilities
- Expected dependencies
- Expected execution flows

Compare extracted results against expected outputs.

### 9.2 Deterministic Rule Tests
Each capability detector has unit tests with mock RIM data.
```python
def test_authentication_detector():
    mock_rim = build_mock(route="/login", handler="login_user", table="users")
    result = detect_authentication(mock_rim)
    assert result.name == "Authentication"
    assert result.status == "CONFIRMED"
```

### 9.3 Regression Tests
- After incremental updates, unchanged files retain their stable IDs
- Deleted files cascade-delete relationships
- No orphaned nodes after update

### 9.4 Sanity Checks
- Every symbol has a valid `file_id`
- Every relationship references existing symbols
- Every capability links to at least one evidence record

---

## 10. Non-Functional Goals
| Goal | Target |
|------|--------|
| **Performance** | Initial analysis of medium repo (<500 files) in <60 seconds. Incremental updates in <2 seconds. |
| **Reliability** | Every derived object links to evidence. No AI-generated relationships. |
| **Explainability** | Every query result is reproducible. Every capability is backed by deterministic rules with evidence IDs. |
| **Extensibility** | New languages add extractors. New frameworks add analyzers. Core RIM schema remains unchanged. |
| **Correctness** | 100% precision for extracted static facts (if it compiles, we extract it). Recall limited by static analysis boundaries. |

---

## 11. Development Roadmap

| Phase | Weeks | Deliverable |
|-------|-------|-------------|
| **Phase 1: Foundation** | 1–2 | RIM schema, SQLite store, stable ID generation |
| **Phase 2: Extraction** | 3–4 | Tree-sitter parser, fact extractor, FastAPI route extraction |
| **Phase 3: Intelligence** | 5–6 | Relationships, call graph, dependency graph, execution flow |
| **Phase 4: Capabilities** | 7–8 | Authentication + CRUD capability detectors |
| **Phase 5: Query Engine** | 9–10 | Query APIs, one UI view (Architecture Explorer) |
| **Phase 6: Incremental** | 11–12 | Git diff integration, fact diff, cascade updates, validation tests |
| **Phase 7: Applications** | 13–14 | AI pipeline, documentation generator, chat interface |
| **Phase 8: Polish** | 15–16 | Demo script, edge cases, viva preparation |

---

## 12. What We Are NOT Building
- No generic rule DSL (hardcoded Python functions in V1)
- No generic inference engine
- No Neo4j-first architecture
- No CodeQL competitor
- No compiler or runtime instrumentation
- No enterprise-scale distributed indexing
- No Git history evolution tracking
- No autonomous AI developer agent
- No code generation platform

---

## 13. Success Criteria
By project completion, GitOnboard must:
1. Ingest a Python repository and build a RIM deterministically
2. Extract symbols, relationships, routes, and dependencies with evidence
3. Detect at least 2 capabilities (Authentication, CRUD) via deterministic rules
4. Reconstruct request execution paths for FastAPI routes
5. Answer repository questions using evidence from the RIM
6. Generate architecture documentation and Mermaid diagrams
7. Show impact analysis for symbol changes
8. Support interactive architecture exploration via UI
9. Update incrementally on file changes without full rebuild
10. Validate correctness against expected outputs for test repositories

---

## 14. Final Vision

> **GitOnboard is a Repository Intelligence Platform that transforms source code into a deterministic Repository Intelligence Model, enabling architecture exploration, execution tracing, capability understanding, impact analysis, documentation, onboarding, and evidence-backed AI assistance through a single reusable intelligence layer.**

---

**Architecture Status: FROZEN**  
No further architectural changes unless implementation reveals a genuine flaw. All future work is implementation, testing, and documentation.