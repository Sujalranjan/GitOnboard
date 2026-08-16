---
trigger: always_on
---

# Dependency Governance

Strictly manage dependencies using modern, standardized tooling.

## Python Dependencies (uv)
- This project uses uv for Python package management with pyproject.toml and uv.lock in the workspace root.
- **Allowed commands**:
  - `uv add <package>`: Add a new dependency to pyproject.toml and update uv.lock.
  - `uv add --dev <package>`: Add a development/testing dependency.
  - `uv remove <package>`: Remove a dependency.
  - `uv sync`: Synchronize the local .venv environment with uv.lock.
  - `uv run pytest <args>`: Execute tests in the managed virtual environment.
  - `uv run python <script>`: Execute python scripts within the managed .venv.
- **Prohibited commands**:
  - NEVER use raw pip install, pip3, python -m pip, pip freeze, or manually generate requirements.txt.
  - NEVER use --break-system-packages or install into global/user site-packages.
  - NEVER manually create ad-hoc virtual environments (python -m venv).
  - Always clean up temporary caches and never accumulate pip download stores.

## Frontend Dependencies (npm)
- The frontend uses npm with Next.js 16 and React 19.
- Use npm install <package> from the frontend/ directory.

## Dependency Justification
- Favor the Python Standard Library before adding third-party packages.
- Always check if an existing installed library (sqlalchemy, fastapi, tree-sitter, httpx, chromadb, azure-storage-blob) can fulfill the requirement.
