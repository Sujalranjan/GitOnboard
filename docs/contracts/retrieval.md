# Contract: Code Retrieval & Semantic Context

**Status**: `ACTIVE (Implemented & Tested)`

## 1. Purpose
Defines the contract for querying repository intelligence facts, graph relationships, execution paths, and semantic vector embeddings to answer technical questions and ground AI reasoning.

## 2. Query Capabilities

### A. Graph & Structural Queries (`backend/intelligence/graphs/`)
- `get_files()`: Enumerates all file entities and directory hierarchy.
- `get_symbols()`: Retrieves AST symbols by name, kind, file, or line range.
- `get_dependencies()`: Returns file-to-file and module-to-module import dependencies.
- `get_call_graph()`: Traverses `CALLS` relationships across function and method symbols.

### B. Feature & Trace Queries (`backend/intelligence/features/`, `backend/routers/repo/trace.py`)
- `reconstruct_feature()`: Assembles the end-to-end execution path for an API endpoint (`Route ──► Handler ──► Service / Helper ──► Model / Database Object`).
- Returns ordered node lists, call parameters, and role classifications.

### C. ChromaDB Vector & Semantic Search (`backend/routers/repo/semantic.py`)
- Indexes code chunks, function signatures, and docstrings.
- Endpoint: `GET /api/repos/{repo_name}/semantic-search?query=...`
- Returns top-k matching code snippets with file paths, line ranges, and similarity scores.

### D. Context Builder Engine (`backend/routers/repo/intelligence.py`)
- Endpoint: `GET /api/repos/{repo_name}/context`
- Aggregates metadata, architectural style, top entrypoints, key framework dependencies, and feature execution paths into a unified JSON context for LLM synthesis.

## 3. Invariants
- Semantic search results must always include file paths and valid line ranges.
- Graph traversals must detect and prevent infinite loops in cyclic call graphs.
- Vector store cache must persist across backend restarts via the `chroma_cache` volume.

## 4. Test Verification
- `tests/test_context_builder.py`: Context builder endpoint structure and output.
- `tests/test_feature_discovery.py`: Feature discovery and route sorting.
