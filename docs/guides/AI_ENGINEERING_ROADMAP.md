# AI Engine & Backend Architecture Roadmap (Branch: dheeraj)

## Overview & Scope
This document defines the technical architecture, data models, provider interfaces, safety mechanisms, and phased implementation for the **AI Engineering & Autonomous Repair Subsystem** of the Repository Intelligence Platform.

---

## 1. Safety & Robustness Architecture (The 14 Core Defenses)

| # | Challenge / Threat Vector | Defense Mechanism |
| :--- | :--- | :--- |
| **1** | **Test Tampering / Cheating** | Diff engine separates **Production Changes** from **Test Changes**. Verification runs trusted baseline oracle tests against production diffs and flags test modifications. |
| **2** | **Prompt Injection from Repo Data** | Repository content wrapped in `<untrusted_repo_context>` with strict system instructions treating all code/docs/comments as untrusted data. |
| **3** | **Unsafe Command Execution** | Commands strictly scoped to `/worktrees/<id>`. Worktree provides Git-level isolation; Docker containerization is designed as an optional hardened sandbox. |
| **4** | **Backend Secret Leakage** | Agent subprocess inherits only an explicit whitelist of safe environment variables. Production secrets (`GITHUB_TOKEN`, `DATABASE_URL`) are stripped. |
| **5** | **Passing Tests without Requirement Met** | Implementation Contract with explicit Acceptance Criteria (`AC-01`, `AC-02`) verified independently of unit test pass/fail codes. |
| **6** | **Plausible but Wrong Context** | **Evidence-Referenced Grounding**: Backend generates deterministic `EVID-001` objects (scores, RIM relationships, route links). LLM must cite existing evidence IDs instead of inventing scores. |
| **7** | **Component Hallucination vs Creation** | Deterministic validation: Backend checks symbols against RIM database. If absent, properly classified as `NEW` instead of blindly assuming `EXISTING`. |
| **8** | **Insufficient Retrieval / Context** | If retrieval evidence is low, planning enters `NEEDS_CONTEXT` state and invokes dynamic on-demand search tools rather than hallucinating blind plans. |
| **9** | **Selective Provider Fallback** | Fallback only triggers on transient errors (timeouts, 502/503/504) or rate limits (429). Invalid requests (400), auth errors (401/403), or model refusals fail immediately. |
| **10** | **Self-Repair Regressions** | Monotonic defect check: If defects increase between iterations (e.g. 3 -> 6), the repair loop terminates early with `FAILED (Needs Review)`. |
| **11** | **Git / State Machine Inconsistency** | Strict workflow state machine (`QUEUED` -> `PREPARING` -> `PLANNING` / `NEEDS_CONTEXT` -> `READY` -> `RUNNING` -> `VERIFYING` -> `REPAIRING` -> `VERIFIED`/`FAILED`) with server crash recovery. |
| **12** | **Concurrent Worktree Collisions** | Unique isolated paths (`/worktrees/<implementation_id>`) and unique branches (`implementation/<id>`). |
| **13** | **Frontend-Backend API Drift** | OpenAPI schema comparison checking frontend fetch/axios URL endpoints against backend route definitions before testing. |
| **14** | **External Service Non-Determinism** | Test sandbox adapter layer mocking third-party APIs (Google OAuth, Stripe, GitHub) during verification. |

---

## 2. System Architecture & End-to-End Flow

```text
                                  +-----------------------+
                                  |   User Requirement    |
                                  |  (Natural Language)   |
                                  +-----------+-----------+
                                              |
                                              v
                                  +-----------------------+
                                  | Requirement Analyzer  | <--- Selective Fallback LLMProvider
                                  | (Extracts AC criteria)|      (Prompt Injection Defenses)
                                  +-----------+-----------+
                                              |
                                              v
+------------------------+        +-----------------------+
|  Repository Knowledge  | -----> | Hybrid Context Engine | <--- Produces Deterministic Evidence Objects
| (RIM Graph + pgvector) |        | (Target files/symbols)|      ([EVID-001, EVID-002])
+------------------------+        +-----------+-----------+
                                              |
                                      +-------+-------+
                                      | Low Context?  |
                                      +-------+-------+
                                     YES /         \ NO
                                        v           v
                          +---------------+   +-----------------------+
                          | NEEDS_CONTEXT |   |Implementation Contract| <--- Ground-truth Acceptance Criteria
                          | (Tool Search) |   +-----------+-----------+      (Cites verified evidence_ids)
                          +---------------+               |
                                 |                        v
                                 +-------------> +-----------------------+
                                                 | Step-by-Step Planner  | <--- Ordered Task Decomposition
                                                 +-----------+-----------+      (Linked to ACs, Symbols, NEW/EXISTING)
                                                             |
                                                 [ Milestone: V4 COMPLETE ]
                                                             │
                                                             ▼
                                                 +-----------------------+
                                                 | Isolated Git Worktree | <--- `/worktrees/<implementation_id>`
                                                 +-----------+-----------+      (Sanitized Environment, No Secrets)
                                                             |
                                                             v
                                                 +-----------------------+
                                                 | OpenCode Agent Runner | <--- Reads, modifies code & runs tools
                                                 |  (Streams SSE logs)   |      (Observable Events: READ, EDIT, RUN)
                                                 +-----------+-----------+
                                                             |
                                                             v
                                                 +-----------------------+
                                                 |    Git Diff Engine    | <--- Separates Prod Diffs vs Test Diffs
                                                 +-----------+-----------+
                                                             |
                                                             v
                                  +-----------------------------------------------------+
                                  |           5-Layer Verification Pipeline             |
                                  |                                                     |
                                  |  [Layer 1] Deterministic Build (npm / pytest)       |
                                  |  [Layer 2] Test Execution (baseline oracle suite)   |
                                  |  [Layer 3] Static Analysis (ruff / tsc / eslint)    |
                                  |  [Layer 4] Contract Requirements Matching (AC-01..) |
                                  |  [Layer 5] Independent Semantic LLM Review          |
                                  +--------------------------+--------------------------+
                                                             |
                                            +----------------+----------------+
                                            |                                 |
                                       [ALL PASSED]                      [ANY FAILED]
                                            |                                 |
                                            v                                 v
                              +---------------------------+     +---------------------------+
                              | Unlock Create PR Action   |     | Self-Repair Loop Trigger  |
                              | (Verified & Ready)        |     | (Max 3, Monotonic check)  |
                              +-------------+-------------+     +-------------+-------------+
                                            |                                 |
                                            v                                 | Feed `<verification_defects>`
                              +---------------------------+                   v
                              | GitHub Pull Request       |     +---------------------------+
                              | Generated (#PR_NUMBER)    |     | Re-execute OpenCode Agent |
                              | Verified badge attached   |     | in Worktree with Feedback |
                              +---------------------------+     +-------------+-------------+
                                                                              |
                                                                              +---> Re-Run Verification
```

---

## 3. Database Models Specification

The database models in `backend/models/implementation.py`:

### 3.1 Implementation & Planning Tables
* **`implementations`**:
  * `id` (PK, String/UUID)
  * `repository_id` (FK -> `repositories.id`)
  * `user_id` (FK -> `users.id`)
  * `title` (String, e.g. "Add Google OAuth Login")
  * `raw_requirement` (Text)
  * `branch_name` (String, e.g. "feature/google-oauth")
  * `worktree_path` (String, isolated filesystem path)
  * `status` (Enum: `QUEUED`, `PREPARING`, `PLANNING`, `NEEDS_CONTEXT`, `READY`, `RUNNING`, `VERIFYING`, `REPAIRING`, `VERIFIED`, `FAILED`, `PR_CREATED`)
  * `created_at`, `updated_at` (DateTime)

* **`implementation_contracts`**:
  * `id` (PK, String/UUID)
  * `implementation_id` (FK -> `implementations.id`, Unique)
  * `acceptance_criteria` (JSONB / List[str])
  * `affected_components` (JSONB / List[dict], e.g. `[{"file": "...", "symbol": "...", "component_type": "EXISTING", "evidence_ids": ["EVID-001"]}]`)
  * `evidence_manifest` (JSONB / List[dict], deterministic evidence items with source, similarity, relationships)
  * `tests_required` (JSONB / List[str])
  * `security_considerations` (JSONB / List[str])

* **`implementation_plans`** *(Enhanced Traceability)*:
  * `id` (PK, String/UUID)
  * `implementation_id` (FK -> `implementations.id`)
  * `step_number` (Integer)
  * `title` (String)
  * `description` (Text)
  * `target_files` (JSONB / List[str])
  * `affected_symbols` (JSONB / List[str])
  * `component_type` (Enum: `EXISTING`, `NEW`)
  * `acceptance_criteria` (JSONB / List[str], e.g. `["AC-01", "AC-02"]`)
  * `evidence_ids` (JSONB / List[str], e.g. `["EVID-001"]`)
  * `expected_changes` (Text)
  * `dependencies` (JSONB / List[int], e.g. `[1]`)
  * `status` (Enum: `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`)

---

## 4. Backend Module Structure (AI Subsystem)

```text
backend/
├── ai/
│   ├── __init__.py
│   ├── interfaces.py        # LLMProvider Protocol definition
│   ├── schemas.py           # Structured Pydantic request/response types
│   ├── service.py           # Selective Fallback dispatcher (OpenRouter -> NVIDIA -> Ollama)
│   └── providers/
│       ├── openrouter.py    # OpenRouter API client
│       ├── nvidia.py        # NVIDIA Free Tier API client
│       └── ollama.py        # Local Ollama client
│
├── planning/
│   ├── __init__.py
│   ├── requirements.py      # Extracts criteria & intent with prompt injection defense
│   ├── impact_analysis.py   # Hybrid vector + keyword + RIM graph; produces EVID-001 items
│   ├── contract.py          # Ground-truth ImplementationContract generation with evidence manifest
│   └── planner.py           # Step planner generating linked ACs, symbols, & EXISTING/NEW tags
│
├── agent/                   # [Version 5 - Not started yet]
│   ├── __init__.py
│   ├── worktree.py          # Git worktree isolation manager
│   ├── opencode_runner.py   # OpenCode subprocess agent runner
│   ├── events.py            # Observable event emitter & streaming logger
│   └── diff.py              # Git diff parser (separating prod vs test diffs)
│
├── verification/            # [Version 6 - Not started yet]
│   ├── __init__.py
│   ├── runner.py            # 5-layer verification pipeline runner
│   ├── build.py             # Deterministic project build check
│   ├── tests.py             # Baseline oracle test execution
│   ├── static.py            # Static analysis checks (ruff, tsc, eslint)
│   ├── api_drift.py         # Frontend-Backend OpenAPI drift detector
│   ├── requirements.py      # Criteria matching vs diff
│   ├── semantic.py          # Independent LLM reviewer
│   └── report.py            # Verification report generator
│
├── repair/                  # [Version 7 - Not started yet]
│   ├── __init__.py
│   ├── repair_loop.py       # Autonomous repair loop (Max 3, Monotonic check)
│   └── defect_builder.py    # Structured XML defect builder
│
└── routers/
    ├── implementation.py    # REST APIs for requirement, contract, plan, run
    ├── verification.py      # Verification triggers, findings, history
    └── pull_request.py      # GitHub PR creation upon VERIFIED status
```

---

## 5. Phase 1 Scope: Version 4 Implementation

We are strictly implementing **Version 4 (Requirement Understanding + Planning)**:

```text
User Request ("Add Google OAuth login")
          |
          v
LLM Provider Abstraction (`backend/ai/`)
          |
          v
Requirement Analysis with Injection Defense (`planning/requirements.py`)
          |
          v
Hybrid Context Retrieval with Deterministic Evidence (`planning/impact_analysis.py`)
          |
          v
Implementation Contract (`planning/contract.py`)
          |
          v
Implementation Plan with Linked ACs, Symbols & Evidence IDs (`planning/planner.py`)
          |
          v
Alembic Migrations (`alembic/versions/`)
          |
          v
REST API Endpoints (`backend/routers/implementation.py`)
          |
          v
Deterministic Mocked Tests (`tests/unit/test_*.py`)
```

---

## 6. Git Branch & Isolation Guarantee
* All work is developed, tested, and committed exclusively on branch **`dheeraj`**.
* This roadmap file resides at `docs/AI_ENGINEERING_ROADMAP.md` and stays tracked only on this branch.
