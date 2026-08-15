# AI Agent Operational Guide

This document is the operational guide for AI agents working in this repository.

## Operational Workflow

Every AI agent must follow this strict 8-step workflow before, during, and after making changes:

```text
Understand ──► Locate ──► Trace ──► Plan ──► Modify ──► Validate ──► Review ──► Report
```

1. **Understand**: Restate the user's goal in technical terms. Identify the required capability and ensure it is not already implemented.
2. **Locate**: Identify the exact files, modules, and tests involved. Search the codebase before creating new files or abstractions.
3. **Trace**: Trace callers, dependencies, data flows, and database schemas affected by the change. Identify what invariants must not be broken.
4. **Plan**: Formulate a minimal, scoped change list. Never modify unrelated files or perform opportunistic refactors.
5. **Modify**: Implement the minimal required changes adhering to existing architectural patterns, type conventions, and naming styles.
6. **Validate**: Run the relevant automated test suite (`pytest`, `eslint`, type checks). Verify that behavior matches contracts.
7. **Review**: Check git diff to ensure no unexpected changes, stray debug logs, or broken imports were introduced.
8. **Report**: Summarize the changes concisely: files modified/created, functionality implemented, limitations, and verification steps.

## Authority & Instruction Precedence

When encountering conflicting guidance or ambiguity:

```text
1. Actual Executable Behavior & Code Contracts
                     ↓
2. Automated Test Suites (pytest, etc.)
                     ↓
3. Domain Contracts (docs/contracts/*)
                     ↓
4. Root /AGENTS.md
                     ↓
5. AI Rules (.agents/rules/*)
                     ↓
6. Domain AGENTS.md (frontend/AGENTS.md, backend/AGENTS.md)
                     ↓
7. Historical / Archive Documentation
```

If two sources conflict, **stop and investigate the active code and tests** rather than silently guessing or choosing an arbitrary path.

## Component Classification

- **ACTIVE**: In active production/development. You may inspect, use, and extend these components adhering to their contracts:
  - Multi-language Tree-sitter Parser (`backend/intelligence/engine/`)
  - Repository Intelligence Model / RIM (`backend/intelligence/rim/`)
  - Relational Layer 4 Fact Store (`backend/intelligence/store/fact_store.py`, `backend/models/fact_store.py`)
  - Layer 6 Capability Detection Engine (`backend/intelligence/capabilities/`)
  - Feature Reconstruction & Tracing (`backend/intelligence/features/`, `backend/routers/repo/trace.py`)
  - ChromaDB Vector & Semantic Index (`backend/routers/repo/semantic.py`)
  - FastAPI Routers & Database Models (`backend/routers/`, `backend/models/`)
  - Asynchronous Queue Worker & TaskManager SSE (`backend/services/worker.py`, `backend/task_manager.py`)
  - Next.js 16 App Router UI (`frontend/app/`, `frontend/components/`)
- **PLANNED**: Target specifications for future phases. Do **NOT** treat them as already implemented runtime code:
  - Autonomous AI Implementation Engine (Git worktrees & code generation)
  - Independent Verification Engine (sandbox testing & regression)
  - Self-Repair Loop (automated patch iteration)
  - Pull Request Generation & Export
- **LEGACY**: Historical material only (`archive/legacy/`). Never import from or recommend patterns from legacy archives.

## Environment Note (WSL / Windows)
When running shell commands in WSL from PowerShell or IDE terminals, execute commands in the Linux environment using `wsl -e bash -c "..."`. For deleting directories with nested files or symlinks, always use native Linux tools (`rm -rf`) inside WSL.
