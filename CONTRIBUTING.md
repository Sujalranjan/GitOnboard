# Contributing & Engineering Governance

This guide outlines standards, development workflows, and git hooks for contributors to the Repository Intelligence Platform.

---

## 1. Git Hooks & Preventing Stale PRs

To prevent pushing stale branches that fail CI, enable the repository git hooks:

```bash
git config core.hooksPath .githooks
git config pull.rebase true
```

The `pre-push` hook automatically fetches from origin and verifies that your local branch contains the latest upstream commits before pushing.

---

## 2. Core Engineering Principles

1. **Follow the AI Master Guide**: Review [AGENTS.md](AGENTS.md) and [.agents/rules/](.agents/rules/) before making architectural changes.
2. **Deterministic First**: Always prefer Tree-sitter AST analysis, symbol graphs, and rule-based detection over non-deterministic LLM prompting.
3. **Layer 4 Fact Store Persistence**: All structural facts must be persisted to PostgreSQL Fact Store tables (`files`, `symbols`, `relationships`, `routes`, `database_objects`, `capabilities`, `capability_members`, `evidence`).
4. **Real-Time Task Updates**: Long-running background operations must publish progress through `task_manager.notify(...)` to push real-time status to the frontend via SSE.
5. **No Duplicate Implementations**: Never introduce parallel versions (`_v2`, `_new`, `_old`) of any module. Modify existing code in place.
6. **Cross-Database Compatibility**: Ensure all SQLAlchemy models use `JSONType = JSON().with_variant(JSONB, "postgresql")` to keep SQLite unit tests operational.

---

## 3. Pull Request Checklist

Before submitting a PR:
- [ ] All automated tests pass: `pytest backend/tests/ tests/`
- [ ] Code is formatted and linted (`tool.ruff` in pyproject.toml / `npm run lint` in frontend).
- [ ] No temporary files, debug `print()` statements, or dead imports are included.
- [ ] Relevant documentation in `docs/contracts/` or `API.md` is updated if contracts changed.
