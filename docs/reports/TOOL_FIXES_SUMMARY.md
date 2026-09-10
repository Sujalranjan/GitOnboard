# Tool #2 and Tool #3 Fixes - Implementation Summary

## Overview
Fixed critical validation issues in Tool #2 (File Retrieval) and Tool #3 (Graph Query) to prevent false positives and ensure explicit error handling for LLM integration.

## Tool #2: File Retrieval (`/backend/routers/repo/structure.py`)

### Issue
The endpoint could return 200 with empty content for nonexistent files, and relied on GitHub API fallback which could return results for files not in the analyzed repository.

### Changes Made
1. **Removed GitHub API fallback** - File MUST exist in current analysis (FactStore)
2. **Strict file existence validation** - Check FactFile exists in current analysis BEFORE reading
3. **Explicit error responses**:
   - 404: File not found in analysis
   - 400: Invalid path (traversal attempt) or invalid line range
   - 500: Storage infrastructure errors (blob not found, storage read failure)
4. **Parameter validation** - Validate all line range parameters upfront:
   - `start_line >= 1`
   - `end_line >= start_line`
   - `end_line <= total_lines`
   - Both `start_line` and `end_line` required together
5. **Analysis isolation** - Query includes `analysis_id` filter to prevent cross-analysis contamination

### Behavior Changes
**Before:**
```
GET /repos/repo/file?path=how_does_login_work
→ 200 with empty content (if GitHub fallback found nothing)
```

**After:**
```
GET /repos/repo/file?path=how_does_login_work
→ 404 File not found in storage or repository: 'how_does_login_work'
```

**Valid file retrieval:**
```
GET /repos/repo/file?path=backend/auth.py
→ 200 with full content (if exists in FactStore)

GET /repos/repo/file?path=backend/auth.py&start_line=10&end_line=20
→ 200 with lines 10-20 only (validated against total_lines)
```

### Error Cases Handled
1. **File not found**: 404 with clear message
2. **Path traversal**: 400 "path traversal detected"
3. **Invalid line range**: 400 with specific error (start<1, end<start, end>total)
4. **Storage infrastructure failure**: 500 with clear distinction from file-not-found
5. **Natural language paths**: 404 (same as any nonexistent file)

### Validation Order
1. Path format (normalize_relative)
2. Line range parameters (if provided)
3. File existence in analysis
4. Storage availability
5. Line range extraction

---

## Tool #3: Graph Query (`/backend/routers/repo/graph.py`)

### Issue
The endpoint accepted any node_id without validation and returned empty graph (nodes: [], edges: []) for nonexistent nodes, making it impossible for LLM to distinguish between "valid node with no relationships" vs "node doesn't exist".

### Changes Made
1. **Strict parameter validation**:
   - `node_id`: Not empty (required)
   - `direction`: Must be "incoming" | "outgoing" | "both"
   - `depth`: 1-10 (prevents query explosion)
   - `max_nodes`: 1-1000 (prevents memory exhaustion)
   - `relationship_type`: Must be valid type (calls, imports, depends_on, inherits, renders)

2. **Node existence validation** - Verify node_id exists in model BEFORE traversal:
   ```python
   if node_id not in service.model.entities:
       raise HTTPException(404, "Node not found in repository graph")
   ```

3. **Clear error responses**:
   - 400: Invalid parameters
   - 404: Node doesn't exist
   - 200: Valid query result (even if graph is empty)

4. **Explicit distinction**:
   - Node not found: 404 error
   - Valid node with no relationships: 200 with nodes: [node_id], edges: []

### Behavior Changes
**Before:**
```
POST /repos/repo/graph/query
{
  "node_id": "urn:function:nonexistent.py#fake",
  "direction": "outgoing"
}
→ 200 with {"nodes": [], "edges": []}  ← False positive, impossible to tell node is invalid
```

**After:**
```
POST /repos/repo/graph/query
{
  "node_id": "urn:function:nonexistent.py#fake",
  "direction": "outgoing"
}
→ 404 Node 'urn:function:nonexistent.py#fake' not found in repository graph
```

**Valid node with no relationships:**
```
POST /repos/repo/graph/query
{
  "node_id": "urn:function:backend/util.py#helper",
  "direction": "outgoing"
}
→ 200 {"nodes": [{"id": "urn:function:...", "label": "helper", ...}], "edges": []}
```

### Error Cases Handled
1. **Node not found**: 404 with clear message
2. **Empty node_id**: 400 "node_id cannot be empty"
3. **Invalid direction**: 400 lists valid values
4. **Invalid depth**: 400 specifies allowed range (1-10)
5. **Invalid max_nodes**: 400 specifies allowed range (1-1000)
6. **Invalid relationship_type**: 400 lists valid types
7. **Parameter validation**: Happens BEFORE model building (fail fast)

### Validation Order
1. Input parameter validation (node_id, direction, depth, max_nodes, relationship_type)
2. Model building
3. Node existence check
4. Graph traversal
5. Return result

---

## Graph Search Endpoint Enhancement

Also added validation to the graph search endpoint:
- Rejects empty search queries (400)
- Logs search results for debugging

---

## Test Coverage

### Tool #2 Tests (`backend/tests/routers/test_file_retrieval_tool.py`)

**Valid Cases:**
- ✓ Get existing file
- ✓ Get file with line range
- ✓ Get file with empty content

**Error Cases:**
- ✓ File not found → 404
- ✓ Natural language paths → 404
- ✓ Path traversal → 400
- ✓ Empty path → 400
- ✓ Invalid line range (start < 1) → 400
- ✓ Invalid line range (end < start) → 400
- ✓ Invalid line range (end > total_lines) → 400
- ✓ Missing end_line when start_line given → 400

**Isolation:**
- ✓ Cross-analysis contamination prevention

### Tool #3 Tests (`backend/tests/routers/test_graph_query_tool.py`)

**Valid Cases:**
- ✓ Query existing node
- ✓ Different directions (incoming, outgoing, both)
- ✓ Different depths (1, 2, 5, 10)

**Error Cases:**
- ✓ Node not found → 404
- ✓ Empty node_id → 400
- ✓ Invalid direction → 400
- ✓ Invalid depth (< 1, > 10) → 400
- ✓ Invalid max_nodes (< 1, > 1000) → 400
- ✓ Invalid relationship_type → 400
- ✓ Empty search query → 400

**Search:**
- ✓ Valid search by name
- ✓ Empty search query rejection

---

## Key Design Decisions

### 1. Analysis-Level Isolation
Both tools strictly enforce analysis isolation:
- Tool #2: Queries `FactFile` with `analysis_id == current_analysis.id`
- Tool #3: Uses model from `get_or_build_model()` which is analysis-specific

### 2. No GitHub Fallback (Tool #2)
Removed GitHub API fallback because:
- Analyzed files MUST come from FactStore (the indexed/scanned repository)
- GitHub fallback would return files outside the analysis scope
- LLM integration requires deterministic, analysis-scoped behavior
- Can be re-added in future if explicitly needed, but not by default

### 3. Fail-Fast Parameter Validation (Tool #3)
Parameters validated BEFORE model building:
- Reduces computational overhead
- Returns 400 errors before expensive operations
- Clear user feedback about invalid parameters

### 4. Explicit vs Implicit Errors
- **404**: Resource doesn't exist (file, node)
- **400**: Invalid input (path format, parameters)
- **500**: Infrastructure failure (storage unavailable, blob corrupted)

---

## Backward Compatibility

### Breaking Changes

**Tool #2:**
- ❌ GitHub API fallback removed (BREAKING)
  - Files must exist in FactStore
  - Any external tools relying on GitHub fallback will break
  - Mitigation: Only valid for tools that expect analysis-scoped files

**Tool #3:**
- ❌ Node not found now returns 404 instead of 200 with empty graph (BREAKING)
  - Clients expecting empty graph for invalid nodes will need updating
  - Required for LLM integration clarity

### Non-Breaking Changes
- Tool #2: Line range support already existed, validation is enhancement
- Tool #3: Parameter validation is enhancement, query still works with valid inputs

---

## Logging

### Tool #2 Logs
```
[FILE_API] GET /repo/file?path=backend/main.py
[FILE_API] Clean path: backend/main.py
[FILE_API] FactFile found - blob_name: ..., size: 1024
[FILE_API] Blob read successful, content size: 5432
```

### Tool #3 Logs
```
[GRAPH_QUERY] repo=test_repo, node_id=urn:function:backend/auth.py#login, direction=outgoing, depth=1
[GRAPH_QUERY] Node found: login (type=FUNCTION)
[GRAPH_QUERY] Result: 3 nodes, 2 edges
```

---

## Next Steps

1. **Run test suite**: `uv run pytest backend/tests/routers/test_*.py -v`
2. **Test against real GitOnboard repository**: Verify behavior with actual data
3. **Integrate with LLM tool-calling system**: These fixes enable safe tool use
4. **Consider Tools #6 and #7**: Apply similar validation patterns if needed

---

## Files Modified

1. `/backend/routers/repo/structure.py` - Tool #2 implementation
2. `/backend/routers/repo/graph.py` - Tool #3 implementation
3. `/backend/tests/routers/test_file_retrieval_tool.py` - Tool #2 tests (NEW)
4. `/backend/tests/routers/test_graph_query_tool.py` - Tool #3 tests (NEW)

---

## Verification Checklist

- [x] Code compiles without syntax errors
- [x] No breaking changes to Tools #1, #4, #5, #6, #7
- [x] No natural language preprocessing added
- [x] No architecture redesign
- [x] Strict validation added to Tool #2
- [x] Strict validation added to Tool #3
- [x] Tests written for all error cases
- [x] Analysis isolation maintained
- [x] Logging added for debugging
- [ ] Run full test suite
- [ ] Test against real repository
- [ ] Verify LLM integration works correctly
