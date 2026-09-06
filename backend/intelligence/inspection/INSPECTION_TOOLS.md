# Phase 2L Inspection Tools

Reusable inspection tools for repository exploration. All tools leverage existing infrastructure: `RepositoryToolLayer`, `FactStore` database, and `QueryLayer`.

## Overview

The inspection tools provide five core operations:

1. **inspect_file()** - Get file structure and symbol outline (no source code)
2. **inspect_symbol()** - Get metadata about a specific symbol (no source code)
3. **read_symbol()** - Read exact source code of a symbol using canonical line boundaries
4. **read_lines()** - Read specific line range from a file (validated)
5. **read_file()** - Read entire file (warns if > 50KB)

## Architecture

### Data Flow

```
User Code
    ↓
Inspection Tool (inspect_file, inspect_symbol, read_symbol, etc.)
    ↓
RepositoryToolLayer
    ├─→ Active Worktree (filesystem)
    └─→ Blob Storage (Azure) via FactFile
    ├─→ FactFile metadata
    ├─→ FactSymbol for symbols
    ├─→ FactRelationship for relationships
    └─→ FactRoute for web routes
```

### Symbol Resolution Strategy

When resolving symbols, tools follow this pattern:

1. **Lookup FactFile** by analysis_id + path
2. **Query FactSymbol** by analysis_id + file_id + name (exact match)
3. **Handle Ambiguity**:
   - If 0 symbols: return error "Symbol not found"
   - If 1 symbol: return metadata with boundaries
   - If N > 1 symbols: return error + candidates list, let caller disambiguate

### Critical Design Decisions

#### 1. No String Matching for Symbol Location

Symbol boundaries come ONLY from `FactSymbol.line_start` and `FactSymbol.line_end`, which are populated by the parser during analysis. Do NOT use:
- String search in source
- Regex matching
- Fuzzy name matching

#### 2. Ambiguous Symbol Handling

If a file has multiple symbols with the same name (e.g., nested functions, overloads), return all candidates:

```python
{
    "success": False,
    "error": "Multiple symbols found with name 'func'",
    "candidates": [
        {
            "symbol_id": "sym_1",
            "qualified_name": "module.func",
            "line_start": 10,
            "line_end": 20,
        },
        {
            "symbol_id": "sym_2",
            "qualified_name": "module.Class.func",
            "line_start": 50,
            "line_end": 60,
        },
    ]
}
```

#### 3. File Size Limits

- `read_file()` warns if file > 50KB
- Does NOT silently truncate
- Suggests `inspect_file() + read_symbol()` for large files
- Can be called anyway (caller decides)

#### 4. Token Estimation

Uses approximate formula: `tokens ≈ len(text) / 4`

This is more accurate for code than prose. If precise tokenization needed later, integrate with `tiktoken` or transformers library.

## Tool APIs

### 1. inspect_file()

Get file structure WITHOUT reading full source.

```python
from backend.intelligence.inspection import inspect_file

result = inspect_file(
    file_path="backend/app.py",
    repo_name="GitOnboard",
    db=session,
    repo_root="/tmp/workspace",
    user_id=123,
)

# result.InspectFileResult:
# {
#     "file_path": "backend/app.py",
#     "language": "python",
#     "total_lines": 450,
#     "file_size_kb": 12.5,
#     "symbols": [
#         {
#             "name": "create_app",
#             "qualified_name": "app.create_app",
#             "symbol_type": "function",
#             "line_start": 15,
#             "line_end": 35,
#             "symbol_id": "sym_abc123",
#             "parent_symbol": None,
#         },
#         ...
#     ],
#     "success": True,
#     "error": None,
# }
```

**Reuses:** `RepositoryToolLayer.get_file_outline()`

---

### 2. inspect_symbol()

Get metadata about ONE symbol (name, type, relationships).

```python
from backend.intelligence.inspection import inspect_symbol

result = inspect_symbol(
    file_path="backend/app.py",
    symbol_name="create_app",
    repo_name="GitOnboard",
    db=session,
    user_id=123,
)

# result.InspectSymbolResult:
# {
#     "symbol_id": "sym_abc123",
#     "name": "create_app",
#     "qualified_name": "app.create_app",
#     "symbol_type": "function",
#     "file_path": "backend/app.py",
#     "line_start": 15,
#     "line_end": 35,
#     "language": "python",
#     "signature": "def create_app(config_path: str) -> Flask",
#     "docstring": "Initialize Flask application...",
#     "relationships": {
#         "calls": [
#             {
#                 "name": "load_config",
#                 "file_path": "backend/config.py",
#                 "symbol_id": "sym_xyz789",
#                 "qualified_name": "config.load_config",
#             }
#         ],
#         "called_by": [...],
#         "imports": [...],
#         "imported_by": [...],
#         "uses": [...],
#         "used_by": [...],
#     },
#     "success": True,
#     "error": None,
# }
```

**If Ambiguous (multiple symbols with same name):**

```python
# {
#     "success": False,
#     "error": "Multiple symbols found with name 'func'",
#     "candidates": [
#         {"symbol_id": "sym_1", "qualified_name": "...", "line_start": 10, "line_end": 20},
#         {"symbol_id": "sym_2", "qualified_name": "...", "line_start": 50, "line_end": 60},
#     ]
# }
```

**Reuses:** `RepositoryToolLayer.get_symbol()`, database FactSymbol/FactRelationship queries

---

### 3. read_symbol()

Read EXACT source code of a symbol using canonical boundaries.

```python
from backend.intelligence.inspection import read_symbol

result = read_symbol(
    file_path="backend/app.py",
    symbol_name="create_app",
    repo_name="GitOnboard",
    db=session,
    user_id=123,
)

# result.SourceReadResult:
# {
#     "file_path": "backend/app.py",
#     "source": """   15 | def create_app(config_path: str) -> Flask:
#                   16 |     \"\"\"Initialize Flask application.\"\"\"
#                   17 |     app = Flask(__name__)
#                   ...
#                   35 |     return app
#     """,
#     "raw_text": "def create_app(config_path: str) -> Flask:\n...\n    return app",
#     "line_start": 15,
#     "line_end": 35,
#     "total_lines": 450,
#     "file_size_kb": 12.5,
#     "language": "python",
#     "symbol_id": "sym_abc123",
#     "symbol_name": "create_app",
#     "estimated_tokens": 85,
#     "success": True,
#     "error": None,
# }
```

**If Ambiguous:**

```python
# {
#     "success": False,
#     "error": "Multiple symbols found with name 'func'",
#     # No source code returned
# }
```

**Reuses:** `RepositoryToolLayer.read_file()` with symbol boundaries from FactSymbol

---

### 4. read_lines()

Read specific line range (validated).

```python
from backend.intelligence.inspection import read_lines

result = read_lines(
    file_path="backend/app.py",
    start_line=15,
    end_line=35,
    repo_name="GitOnboard",
    db=session,
    user_id=123,
)

# result.SourceReadResult:
# {
#     "file_path": "backend/app.py",
#     "source": """   15 | def create_app(config_path: str) -> Flask:
#                   ...
#                   35 |     return app
#     """,
#     "raw_text": "def create_app(...)",
#     "line_start": 15,
#     "line_end": 35,
#     "total_lines": 450,
#     "file_size_kb": 12.5,
#     "language": "python",
#     "estimated_tokens": 85,
#     "success": True,
#     "error": None,
# }
```

**Validation:**
- Rejects: `start_line < 1` or `end_line < 1`
- Rejects: `start_line > end_line`
- Returns error if line range out of bounds

**Reuses:** `RepositoryToolLayer.read_file()` with validated range

---

### 5. read_file()

Read entire file (expensive operation).

```python
from backend.intelligence.inspection import read_file

result = read_file(
    file_path="backend/app.py",
    repo_name="GitOnboard",
    db=session,
    user_id=123,
)

# result.SourceReadResult:
# {
#     "file_path": "backend/app.py",
#     "source": """    1 | import flask
#                  2 | from typing import Optional
#                  ...
#                450 | # end of file
#     """,
#     "raw_text": "import flask\nfrom typing import Optional\n...",
#     "line_start": 1,
#     "line_end": 450,
#     "total_lines": 450,
#     "file_size_kb": 12.5,
#     "language": "python",
#     "estimated_tokens": 3200,
#     "success": True,
#     "error": None,
#     "warning": None,
# }
```

**If File > 50KB:**

```python
# {
#     "file_path": "very_large_file.py",
#     "file_size_kb": 120.5,
#     "source": "",
#     "raw_text": "",
#     "success": False,
#     "error": "File too large (120.5KB > 50KB)",
#     "warning": "Use inspect_file() + read_symbol() instead for large files",
# }
```

**Reuses:** `RepositoryToolLayer.read_file(path, 1, None)`

---

## Language Support

Supports 5 languages via extension detection:

| Extension | Language |
|-----------|----------|
| `.py` | python |
| `.js` | javascript |
| `.ts` | typescript |
| `.jsx` | jsx |
| `.tsx` | tsx |

Unknown extensions return `language: "unknown"`.

---

## Database Access Strategy

### With Database (Recommended)

When `db` session is provided:

```python
result = inspect_symbol(
    file_path="backend/app.py",
    symbol_name="func",
    db=session,  # SQLAlchemy session
)
```

- Queries FactFile, FactSymbol, FactRelationship directly
- Reads from Blob Storage if no active worktree
- Fast, accurate symbol boundaries
- Reliable relationship graph

### Without Database (Fallback)

When `db=None`:

```python
result = inspect_file(
    file_path="backend/app.py",
    repo_root="/tmp/workspace",  # filesystem path
)
```

- Falls back to filesystem only
- Uses RepositoryToolLayer to walk tree and parse
- Works for active worktrees
- May be slower than database queries

Both modes use identical tool signatures and return types.

---

## Error Handling

All tools return consistent error structure:

```python
{
    "success": False,
    "error": "Descriptive error message",
    # Other fields set to defaults (empty strings, empty lists, etc.)
}
```

Common errors:

| Error | Meaning |
|-------|---------|
| "File not found" | FactFile doesn't exist in analysis |
| "Symbol not found" | No FactSymbol matches name |
| "Multiple symbols found" | Ambiguous: N symbols with same name (see `candidates`) |
| "Invalid line numbers" | start_line < 1 or end_line < 1 |
| "Invalid line range" | start_line > end_line |
| "File too large" | File > 50KB (use read_symbol instead) |

---

## Integration with LLM Tools

These inspection tools are **not yet LLM tools** (that's Phase 2L Stage 8).

Currently they are:
- Internal Python functions
- Used by Agent 4 (Symbol Boundary Validation) for testing
- Callable from any backend code

Later they will be:
- Wrapped as LLM tool definitions
- Available to LLM agents for code exploration
- Published in `/intelligence/tools/` or similar

---

## Testing

Comprehensive tests in `backend/tests/unit/test_inspection_tools.py`:

```bash
# Run all inspection tests
python3 -m pytest backend/tests/unit/test_inspection_tools.py -v

# Run specific test class
python3 -m pytest backend/tests/unit/test_inspection_tools.py::TestLanguageDetection -v

# Run with coverage
python3 -m pytest backend/tests/unit/test_inspection_tools.py --cov=backend.intelligence.inspection
```

Test categories:
- Language detection (all 5 languages)
- Token estimation
- File size calculation
- Line numbering
- Symbol boundary validation
- Ambiguous symbol handling
- Input validation

---

## Performance Notes

### Database Queries

- FactSymbol lookup: O(1) by analysis_id + file_id + name
- Relationship queries: O(N) where N = relationships in analysis
- Indexed fields: analysis_id, path, name, qualified_name

### Fallback Filesystem

- File tree walk: O(F) where F = files in repo
- Line reading: O(1) with binary seek
- No caching (caller caches if needed)

### Token Estimation

- Uses fast approximation: `len(text) / 4`
- No external API calls
- No model loading

---

## Next Steps (Agent 4: Symbol Boundary Validation)

Agent 4 will:

1. Call tools against real workspace files
2. Verify symbol boundaries are exact (to character)
3. Verify language detection for all 5 languages
4. Test ambiguous symbol resolution
5. Test all error cases
6. Verify token estimation accuracy
7. Validate line numbering formatting

Expected test coverage:
- 20+ real workspace files
- All 5 languages (Python, JS, TS, JSX, TSX)
- 100+ symbols with various nesting levels
- Edge cases: empty files, single-line functions, large nested structures

---

## References

- **RepositoryToolLayer**: `backend/repository_tools/tools.py`
- **FactStore Models**: `backend/models/fact_store.py`
- **QueryLayer**: `backend/intelligence/query_layer.py`
- **Tests**: `backend/tests/unit/test_inspection_tools.py`
