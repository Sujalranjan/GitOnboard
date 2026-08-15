---
trigger: always_on
---

# Dependency Governance

Strictly manage dependencies using modern, standardized tooling.

## Python Dependencies (uv)
- This project uses `uv` for Python package management with `pyproject.toml` and `uv.lock`.
- **Allowed commands**:
  - `uv add <package>`: Add a new dependency.
  - `uv remove <package>`: Remove a dependency.
  - `uv sync`: Synchronize environment with lockfile.
  - `uv run pytest`: Execute tests in the managed virtual environment.
- **Prohibited commands**:
  - Never use raw `pip install`, `pip freeze`, or manually generate `requirements.txt`.
  - Never manually create ad-hoc virtual environments (`python -m venv`).

## Frontend Dependencies (npm)
- The frontend uses `npm` with Next.js 16 and React 19.
- Use `npm install <package>` from the `frontend/` directory.

## Dependency Justification
- Favor the Python Standard Library before adding third-party packages.
- Always check if an existing installed library (`sqlalchemy`, `fastapi`, `tree-sitter`, `httpx`, `chromadb`) can fulfill the requirement.
