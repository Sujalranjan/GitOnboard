---
trigger: always_on
---

# Documentation & Testing Governance

Keep documentation, specifications, and test suites synchronized with implementation.

## Documentation Rules
- When modifying an architectural contract, update the corresponding file in `docs/contracts/` and `API.md` / `DATA_MODEL.md`.
- Keep documentation concise, accurate, and actionable. Avoid speculative future documentation.
- Never document non-existent components as if they are currently implemented. Explicitly label components as **ACTIVE**, **PLANNED**, or **LEGACY**.

## Testing Standards
- Automated test suites reside in `tests/` and `backend/tests/`.
- Every new capability, parser enhancement, or Fact Store modification must include automated tests.
- When fixing a bug, write a regression test verifying the fix.
- All test suites must execute cleanly via `pytest` without uncaught exceptions or hangs.
