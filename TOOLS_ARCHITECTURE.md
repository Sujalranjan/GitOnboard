# Repository Tools Architecture

This document explains the design of the repository inspection tools and how they work together.

## Core Principle

The tools use a **hybrid approach**: PostgreSQL for fast indexed metadata queries, and Azure Blob Storage for complete repository snapshots.

```
PostgreSQL (Fast Metadata Index)       Azure Blob Storage (Complete Snapshots)
├── FactSymbol (code symbols)          repositories/{hash}/snapshots/local_clone/
├── FactRelationship (call graph)      ├── README.md
├── FactRoute (HTTP routes)            ├── backend/
├── FactFile (indexed files only)      │   ├── main.py
└── FactCapability (features)          │   └── routers/
                                       ├── frontend/
                                       ├── .gitignore
                                       └── ... (ALL files)
```

## Tool Categories

### 1. Fast Code Navigation Tools (PostgreSQL Only)

These tools are optimized for finding **important code-related entities** quickly. They use the PostgreSQL index, which means:

- ✅ **Very fast** (instant results)
- ✅ **Structured data** (symbols, call graph, routes)
- ❌ **Limited scope** (only indexed code files, ignores non-code files and hidden directories)

#### Tools in this category:

| Tool | Query | Data Source | Use Case |
|------|-------|-------------|----------|
| **search_symbols** | Find files/symbols by name pattern | PostgreSQL FactFile + FactSymbol | "Find the auth middleware function" |
| **get_symbol** | Look up symbol definition (function, class, method) | PostgreSQL FactSymbol | "What does `authenticate()` do?" |
| **get_callers** | Find what calls a specific function | PostgreSQL FactRelationship | "Who calls the `verify_token()` function?" |
| **get_callees** | Find what a function calls | PostgreSQL FactRelationship | "What does `authenticate()` call?" |
| **get_route** | Find HTTP routes by path | PostgreSQL FactRoute | "What endpoint handles `/api/users`?" |
| **get_feature** | Find detected architectural capabilities | PostgreSQL FactCapability | "Does this have authentication?" |

**What gets indexed:**
- Python/TypeScript/JavaScript source files
- Function/class/method definitions
- HTTP route definitions
- Database model definitions
- Import relationships

**What is NOT indexed:**
- Markdown documentation (.md files)
- Configuration files (except route/model definitions)
- Hidden directories (.git, .github, .venv, etc.)
- Binary files
- Vendored/compiled code

---

### 2. Complete Repository Access Tools (Blob Storage)

These tools access the **complete repository snapshot** in Azure Blob Storage, showing ALL files regardless of type.

#### Tools in this category:

| Tool | Query | Data Source | Use Case |
|------|-------|-------------|----------|
| **get_tree** | Directory tree from any path | Blob Storage | "Show me the entire backend/ directory structure" |
| **read_file** | Read file content (any file type) | Blob Storage | "What's in README.md?" or "Show me config.json" |
| **search_code** | Search file contents (any file type) | Blob Storage (+ FactFile for file list) | "Find all references to 'JWT' in the codebase" |

**What these access:**
- ✅ ALL files (code, docs, config, hidden directories)
- ✅ Complete repository structure
- ✅ Any file content (text or binary)

---

## Decision Matrix: Which Tool to Use?

```
User asks about:                        Use this tool:
─────────────────────────────────────────────────────────────
"Find the login function"               → search_symbols or get_symbol
"Who calls authenticate()?"             → get_callers
"What does authenticate() do?"          → read_file (get the source)
"Find all JWT references"               → search_code
"Show me the directory structure"       → get_tree
"What's in README.md?"                  → read_file
"Find the /auth endpoint handler"       → get_route → read_file (for impl)
"What HTTP routes exist?"               → search via get_route
```

---

## Example: End-to-End Investigation

**User asks: "How does the authentication flow work?"**

### Step 1: Find the route (PostgreSQL)
```
Tool: get_route
Query: "/auth" or "/login"
Result: Finds route handler symbol (e.g., "handle_login in backend/routers/auth.py")
```

### Step 2: Read the handler (Blob Storage)
```
Tool: read_file
Query: path="backend/routers/auth.py", start_line=..., end_line=...
Result: Source code of the handler
```

### Step 3: Trace the call graph (PostgreSQL)
```
Tool: get_callees
Query: "handle_login"
Result: Functions it calls (authenticate, verify_token, etc.)
```

### Step 4: Inspect each function (Blob Storage)
```
Tool: read_file or get_symbol → read_file
Query: Each function from step 3
Result: Implementation details
```

### Step 5: Search for related code (Blob Storage)
```
Tool: search_code
Query: "JWT" or "session"
Result: All file locations mentioning JWT/session
```

---

## Why This Design?

### PostgreSQL (Indexed Metadata)
- **Purpose**: Fast navigation for code analysts
- **Trade-off**: Only indexes "important" files (code, routes, models)
- **Benefit**: Instant results, structured relationships, call graph

### Blob Storage (Complete Snapshots)
- **Purpose**: Comprehensive file access (docs, config, non-code)
- **Trade-off**: Slightly slower (file I/O)
- **Benefit**: Access to anything (README, configs, data files, etc.)

### Together
- Developers navigate code quickly via PostgreSQL
- Access complete repository for documentation, configuration, or unexpected file types
- No tool can break - if PostgreSQL tool doesn't find it, Blob Storage tools still work

---

## Important Notes

### Analysis Snapshots Are Immutable

All tools work against the **repository snapshot** captured at analysis time:
- `get_tree` shows the snapshot structure (may include deleted files)
- `read_file` reads from the snapshot (not live repo)
- `search_code` searches the snapshot (not live repo)

If the repository has changed since analysis, the snapshot will be stale. Re-run the analysis to get a fresh snapshot.

### PostgreSQL Index Scope

The `FactFile` table tracks all indexed files, but `FactSymbol`, `FactRelationship`, etc. only contain indexed entities:
- A markdown file exists in `FactFile` but has no `FactSymbol` entries
- Use `read_file` or `search_code` to access markdown content

### When to Use Each Approach

| Scenario | Tool | Why |
|----------|------|-----|
| "Find the function" | search_symbols → get_symbol | PostgreSQL is fast |
| "Show me usage" | get_callers | PostgreSQL has call graph |
| "Read the code" | read_file | Blob Storage has content |
| "Find keyword" | search_code | Blob Storage searches content |
| "Explore structure" | get_tree | Blob Storage has complete tree |
| "Find config value" | search_code or read_file | PostgreSQL doesn't index configs |

---

## Implementation Details

### PostgreSQL Tables Used

- `fact_files`: File metadata (path, is_binary, blob_name)
- `fact_symbols`: Symbol definitions (name, type, location)
- `fact_relationships`: Call/import/inherit relationships
- `fact_routes`: HTTP route definitions
- `fact_capabilities`: Detected architectural features

### Blob Storage Structure

```
repositories/{repository_hash}/snapshots/local_clone/{file_path}

Example:
repositories/8c4b6e32-55d5-495c-9bd9-94faaeb64882/snapshots/local_clone/
├── backend/routers/auth.py
├── backend/services/github_oauth.py
├── README.md
├── .env.example
└── ... (all repository files)
```

### Tool Registration

All tools are registered in `backend/services/tool_dispatch.py`:
- Exposed via `/api/llm/analyze/stream` endpoint
- Dispatched through `ToolDispatchTable.execute()`
- Each tool has a handler that calls the appropriate backend

---

## For Future Developers

When adding a new tool:

1. **For code navigation**: Use PostgreSQL (FactSymbol, FactRelationship, etc.)
   - Fast
   - Structured data
   - Limited to indexed code files

2. **For complete access**: Use Blob Storage (via `storage.get_object_text()`)
   - Slower but comprehensive
   - Any file type
   - Shows complete repository snapshot

3. **Hybrid approach**: Use both
   - Query PostgreSQL to find candidates
   - Read from Blob Storage to get content

4. Always document which data source your tool uses
