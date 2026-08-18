# Contract: Autonomous Agent Reasoning & Tooling

**Status**: `PARTIALLY IMPLEMENTED` — `backend/verification/orchestrator.py::VerificationOrchestrator` (`generate_contract`, `run_agent`, `verify_run`, `judge_and_repair`) implements requirement → contract → code generation → verification → bounded (max 3) repair as a single LLM multi-file-generation prompt per attempt, NOT yet as the discrete tool-call loop described below.

## 1. Purpose
Defines the tool interface, reasoning loop, and grounding constraints for autonomous AI agents operating within the repository pipeline.

## 2. Execution Model (as implemented today)
- **Worktree**: agent code-writing runs in a plain, real `git worktree add` sandbox (`backend/services/git_manager.py::GitManager`), scoped under `data/worktrees/`. No Docker — matches this contract's original design, and stays that way deliberately (see `ARCHITECTURE.md` §4: only the verification step's build/test execution runs containerized).
- **Observability**: every run persists an `AgentRun` and an append-only `AgentEvent` trail (`STARTED`, `CODE_GENERATING`, `FILE_WRITTEN` per file, `DIFF_CAPTURED`, `VERIFICATION_STARTED/COMPLETED`, `REPAIR_STARTED`, `FINISHED`/`FAILED`), streamed live over SSE at `GET /api/v1/pipeline/task/{task_id}/events/stream`, and structured `FileChange` diff rows at `GET /api/v1/pipeline/task/{task_id}/changes` (`backend/services/diff_parser.py`). See `DATA_MODEL.md` §1.5.

## 3. Planned Agent Tools (not yet implemented as discrete callable tools)
- `read_fact_store(analysis_id, query)`: Query symbols, relationships, and routes from PostgreSQL.
- `search_code(query, mode="semantic"|"keyword")`: Search code snippets via ChromaDB or AST symbol tables.
- `trace_execution(route_path)`: Trace full execution path from route to database.
- `apply_patch(file_path, diff)`: Apply targeted modifications to files in the Git worktree.
- `run_verification(test_filter)`: Execute verification engine tests against the worktree.

## 4. Grounding & Anti-Hallucination Constraints
- The agent must ground all architectural reasoning in facts retrieved from the Fact Store.
- The agent must report missing dependencies or ambiguities rather than inventing phantom packages or endpoints.
- Not yet enforced by the current single-prompt `run_agent`/`judge_and_repair` implementation — this remains a gap to close when the tool-call loop above is built.
