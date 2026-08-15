# Repository Intelligence Platform — AI Agent Master Guide

Welcome to the Repository Intelligence Platform. This file is the **canonical AI instruction entry point**. All AI coding agents operating in this repository must read this document and adhere to its rules.

---

## 1. Instruction Precedence Hierarchy

When resolving conflicts or ambiguities, follow this strict order of authority:

```text
1. Actual Executable Behavior & Code Contracts (Active Python/TypeScript implementation)
                                  ↓
2. Automated Test Suites (pytest test files in tests/ and backend/tests/)
                                  ↓
3. Domain Contracts (docs/contracts/*.md)
                                  ↓
4. Root /AGENTS.md (This document)
                                  ↓
5. AI Rules (.agents/rules/*.md)
                                  ↓
6. Domain AGENTS.md (frontend/AGENTS.md, backend/AGENTS.md)
                                  ↓
7. Historical / Archive Documentation (archive/legacy/)
```

> [!IMPORTANT]
> If documentation conflicts with active executable code or passing tests, **stop and investigate the code and tests**. Do not silently follow outdated documentation.

---

## 2. Core Agent Instructions

1. **Inspect Before Coding**: Always search existing files (`backend/`, `frontend/`, `docs/contracts/`) before designing new functions or classes.
2. **Prefer Existing Abstractions**: Reuse established models (`RepositoryModel`, `FactStore`, `AnalysisWorker`, `TaskManager`).
3. **Never Invent Architecture**: Do not invent microservices, external message queues, or new database abstractions.
4. **Never Duplicate Implementations**: Never create `_v2`, `_new`, or `_old` files. Exactly one active implementation of every module is permitted.
5. **Keep Changes Minimal and Scoped**: Modify only files relevant to the requested task. Do not perform opportunistic refactoring.
6. **Use Approved Tooling**: Use `uv` for Python dependency management and `npm` for frontend packages. Never use raw `pip`.
7. **Maintain Active vs Planned vs Legacy Boundaries**:
   - **ACTIVE**: Multi-language Tree-sitter parser, RIM graph, Layer 4 Fact Store, Layer 6 Capability Detection, ChromaDB semantic index, FastAPI API routers, SSE TaskManager, Next.js 16 UI.
   - **PLANNED**: AI implementation engine, automated verification engine, self-repair loop, pull request automation. (Contracts in `docs/contracts/` define target specs for planned phases).
   - **LEGACY**: Archived code in `archive/legacy/`. Never import from this directory.
8. **Verify All Modifications**: Always run automated tests (`pytest`) and verify the build before concluding a task.

---

## 3. Team Ownership Boundaries

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND TEAMMATE                               │
│  frontend/ (Next.js 16 App Router, React 19, Tailwind CSS 4, UI)       │
├────────────────────────────────────────────────────────────────────────┤
│                     BACKEND / API TEAMMATE                             │
│  backend/ (FastAPI setup, Auth/OAuth, DB models, Queue worker, SSE)    │
├────────────────────────────────────────────────────────────────────────┤
│                 YOU (INTELLIGENCE / AI TEAMMATE)                       │
│  backend/intelligence/ (Tree-sitter engine, RIM, Fact Store,           │
│  Capabilities, Features, Stages, Graphs, ChromaDB, Ollama LLM)         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Operational Workflow

AI agents must follow the standard 8-step workflow:

```text
Understand ──► Locate ──► Trace ──► Plan ──► Modify ──► Validate ──► Review ──► Report
```

See [.agents/AGENTS.md](.agents/AGENTS.md) and [.agents/rules/](.agents/rules/) for detailed operational guidelines.
