# Contract: Autonomous Agent Reasoning & Tooling

**Status**: `PLANNED (Future Pipeline Stage)`

> [!NOTE]
> This document specifies the target contract for the planned **Autonomous Coding Agent**. It is NOT yet implemented in runtime code.

## 1. Purpose
Defines the tool interface, reasoning loop, and grounding constraints for autonomous AI agents operating within the repository pipeline.

## 2. Planned Agent Tools
- `read_fact_store(analysis_id, query)`: Query symbols, relationships, and routes from PostgreSQL.
- `search_code(query, mode="semantic"|"keyword")`: Search code snippets via ChromaDB or AST symbol tables.
- `trace_execution(route_path)`: Trace full execution path from route to database.
- `apply_patch(file_path, diff)`: Apply targeted modifications to files in the Git worktree.
- `run_verification(test_filter)`: Execute verification engine tests against the worktree.

## 3. Grounding & Anti-Hallucination Constraints
- The agent must ground all architectural reasoning in facts retrieved from the Fact Store.
- The agent must report missing dependencies or ambiguities rather than inventing phantom packages or endpoints.
