# Repository Coverage Report

**Confidence:** Verified  
**Cross-reference:** [audit.log](./audit.log), [00-executive-summary.md](./00-executive-summary.md)

---

## Summary

| Metric | Value |
|--------|-------|
| Total top-level directories (excl. hidden/generated) | 9 |
| Total source files discovered | ~115 |
| Source files successfully analyzed | ~110 |
| Files skipped (intentionally) | 5 |
| Parser failures | 0 |
| Overall coverage | ~96% |

---

## Directories Analyzed

| Directory | Purpose | Analyzed |
|-----------|---------|---------|
| `backend/` | FastAPI application | ✅ Full |
| `backend/intelligence/` | Analysis engine (RIM) | ✅ Full |
| `backend/intelligence/engine/` | Analysis pipeline, analyzers | ✅ Full |
| `backend/intelligence/rim/` | Repository Intelligence Model | ✅ Full |
| `backend/intelligence/graphs/` | Graph query services | ✅ Full |
| `backend/intelligence/capabilities/` | Capability inference engine | ✅ Full |
| `backend/intelligence/features/` | Feature reconstruction engine | ✅ Full |
| `backend/routers/` | FastAPI routers | ✅ Full |
| `backend/models/` | SQLAlchemy models | ✅ Full |
| `backend/services/` | Background services | ✅ Full |
| `backend/dependencies/` | FastAPI DI functions | ✅ Full |
| `backend/tests/` | Test suite | ✅ Full (structure) |
| `frontend/app/` | Next.js App Router pages | ✅ Full |
| `frontend/components/` | React components | ✅ Full |
| `frontend/services/` | API service layer | ✅ Full |
| `frontend/hooks/` | Custom React hooks | ✅ Full |
| `frontend/utils/` | Utility functions | ✅ Full |
| `src/analysis/` | **Orphaned analysis framework** | ✅ Identified but UNUSED |
| `scripts/archive/` | Archived scripts | ⚠️ Skipped (explicitly archived) |
| `tests/` | Root test suite (for `src/`) | ✅ Identified |
| `docs/` | Documentation | ✅ Not analyzed (non-source) |

---

## Files Skipped

| File | Reason | Impact |
|------|--------|--------|
| `backend/main.py.orig` | 111,596-byte legacy monolith — not imported anywhere | **HIGH**: Contains old architecture; risk of confusion |
| `scripts/archive/*.py` | Explicitly archived development scripts | Low |
| `scripts/archive/*.js` | Explicitly archived development scripts | Low |
| `data/repos/**` | User data (cloned repositories) | None |
| `uv.lock` | Dependency lock file | None |

---

## Parser Failures

**None.** All source files that were targeted were successfully read.

---

## Impact of Coverage Gaps

The only significant gap is `backend/main.py.orig`. This 111,596-byte file was not analyzed. It appears to be the original monolithic version of the entire backend before it was restructured. Because it is **not imported anywhere** in the current codebase, it has no runtime impact. However, its presence is a maintenance risk (see [13-risk-assessment.md](./13-risk-assessment.md), Risk R-01).

The `src/analysis/` directory contains a complete, separate analysis framework (with models, plugins, and a registry). It is **not imported or connected to the current backend**. This is fully documented in [06-dead-code-report.md](./06-dead-code-report.md).
