# Contract: AI Implementation Engine

**Status**: `PLANNED (Future Pipeline Stage)`

> [!NOTE]
> This document specifies the target contract for the planned **Phase 5: Implementation Engine**. It is NOT yet implemented in runtime code.

## 1. Purpose
Defines the interface and behavioral invariants for an autonomous AI coding agent that plans and generates code modifications for requested features or bug fixes.

## 2. Planned Architecture

```text
User Request + RIM Context ──► Plan Generator ──► Task Decomposition ──► Patch Generator ──► Git Worktree
```

1. **Context Grounding**:
   - Consumes fact-grounded context from `GET /api/repos/{repo_name}/context` and the Layer 4 Fact Store.
2. **Plan Generation**:
   - Produces a step-by-step implementation plan identifying exact target files, required symbol changes, and invariants.
3. **Execution in Isolated Git Worktrees**:
   - Clones a temporary Git worktree for the repository.
   - Applies code modifications using AST-aware syntax transformations or structured diff patches.
4. **Output Proposal**:
   - Emits a structured changeset proposal (`files_modified`, `files_created`, `diff_patch`, `rationale`).

## 3. Target Invariants
- The agent must never modify files outside the isolated worktree.
- The agent must never perform unrelated refactoring.
- Generated code must strictly preserve existing typing conventions and architectural boundaries.
