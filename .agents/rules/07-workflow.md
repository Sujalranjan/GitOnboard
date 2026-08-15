---
trigger: always_on
---

# AI Development Workflow

AI agents must follow a structured procedure for every code modification.

## 1. Pre-Modification Inspection
- Review relevant domain rules and contracts (`frontend/AGENTS.md`, `backend/AGENTS.md`, `docs/contracts/*`).
- Locate existing functions and types using search tools.
- Verify active database models and schemas before proposing changes.

## 2. Scoped Modification
- Apply minimal, localized changes.
- Ensure all imports are resolved and no circular dependencies are introduced.
- Preserve backward compatibility with existing API routes.

## 3. Validation & Reporting
- Execute relevant test suites:
  - Backend/Fact Store: `pytest backend/tests/ -v`
  - Integration/API: `pytest tests/ -v`
- Inspect `git diff` to ensure no unintended modifications or leftover temporary files remain.
- Report results clearly:
  - Files modified/created.
  - Implemented functionality.
  - Test verification results.
  - Known limitations or follow-up recommendations.
