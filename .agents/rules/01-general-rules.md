---
trigger: always_on
---

# General AI Engineering Rules

These rules apply to every task executed by AI agents in this repository.

## Philosophy
- Build only the requested feature or fix.
- Keep implementations simple, readable, and maintainable.
- Avoid overengineering, speculative architecture, and premature optimization.
- Every modification must leave the repository in a working, testable state.
- Treat active executable code and automated tests as the primary source of truth.

## Scope & Code Changes
- Modify ONLY files directly related to the current task.
- Do NOT refactor unrelated code or fix tangential formatting issues.
- Do NOT rename files or reorganize folder structures unless explicitly instructed.
- Do NOT introduce duplicate implementations of existing functionality (e.g., `parser_v2.py`, `graph_new.py`).

## Investigation Before Action
- Search the codebase (`grep_search`, `view_file`) to identify existing patterns, helpers, and models before creating new ones.
- If existing functionality satisfies the requirement, reuse it.
- If requirements are ambiguous, inspect active tests and database models or ask for clarification rather than guessing.
