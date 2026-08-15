---
trigger: always_on
---

# Code Quality & Maintainability

Write clean, robust, and production-quality code.

## Readability & Naming
- Favor clear, descriptive variable and function names over brevity.
- Keep functions cohesive and focused on a single responsibility.
- Avoid deep conditional nesting (>3 levels). Use guard clauses and early returns.
- Add type annotations to all Python function signatures (`typing` / `pydantic`).
- Maintain TypeScript typing across all frontend code (`frontend/types/`).

## Anti-Duplication Rule
- Never create parallel or duplicate implementations of an existing subsystem.
- Do NOT create `_v2`, `_new`, `_fixed`, or `_old` variants of files.
- Search the repository before creating a new service, utility, parser, graph abstraction, API endpoint, or data model.
- If an existing module needs enhancement, modify the existing module in place while preserving backward compatibility.

## Error Handling & Logging
- Use standard Python `logging` (`logger = logging.getLogger(__name__)`).
- Never use bare `except:` blocks; catch specific exceptions and log tracebacks where appropriate.
- FastAPI routes must raise standard `HTTPException` with meaningful error details and status codes.
- Do NOT leave debug `print()` statements in production code.
