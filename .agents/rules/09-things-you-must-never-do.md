---
trigger: always_on
---

# Prohibited Actions (Things You Must Never Do)

Every AI agent is strictly forbidden from doing the following:

1. **NEVER place backend code outside `backend/`** or frontend code outside `frontend/`.
2. **NEVER connect the frontend directly to the database** or filesystem. Frontend must consume FastAPI endpoints.
3. **NEVER invent new API endpoints or database columns** without verifying against the existing schemas and contracts.
4. **NEVER create duplicate implementations** or versioned files (`parser_v2.py`, `graph_new.py`, `model_old.py`).
5. **NEVER use `pip install` or create `requirements.txt`** — always use `uv`.
6. **NEVER import code from `archive/legacy/`** into active runtime modules.
7. **NEVER resurrect or recreate `Remaining Plan.md`** or obsolete aspirational roadmaps.
8. **NEVER leave placeholder code** (`pass`, `# TODO: implement later`) in committed features.
9. **NEVER perform large, unrequested refactors** while working on a specific task.
10. **NEVER leave the application in a broken or non-runnable state**.
