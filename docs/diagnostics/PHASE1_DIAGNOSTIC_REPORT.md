# Phase 1 Diagnostic Report: Retrieval → LLM Data Flow

## Executive Summary

**FAILURE CONFIRMED** at the serialization/formatting boundary.

The `search_repository` tool returns valid results with 6 items, but the formatter silently strips all useful information, passing only empty placeholder text to the LLM.

## Execution Path Evidence

### 1. USER QUERY
```
"How does login work?"
```

### 2. LLM MAKES TOOL CALL
```json
{
  "action": "tool_call",
  "tool_name": "search_repository",
  "arguments": {"query": "login"}
}
```

### 3. RETRIEVER RETURNS RAW RESULTS ✓
**File**: `backend/repository_tools/tools.py:457-509`  
**Function**: `RepositoryToolLayer.search_repository()`

Raw result count: **6 items**

Result structure (correct):
```python
[
  {
    "type": "file",
    "file": "src/login.py",
    "size": 297,
    "match_source": "filename_manifest"
  },
  {
    "type": "code",
    "file": "src/auth.py",
    "line": 1,
    "snippet": "def login(username, password):",
    "match_source": "lexical"
  },
  # ... 4 more results with "file" key
]
```

### 4. TOOL DISPATCH PRESERVES DATA ✓
**File**: `backend/services/rim_tool_dispatch.py:352-372`  
**Function**: `ToolDispatchTable._handle_search_repository()`

Returns `ToolObservation`:
- `success=True`
- `data=[6 results with "file" key]` ✓
- All results intact

### 5. GUARDRAILS SANITIZE (PRESERVES) ✓
**File**: `backend/agent/loop/guardrails.py:115-146`  
**Function**: `LoopGuardrails.sanitize_observation()`

Sanitized data:
- Type: `list`
- Length: 6 items ✓
- Content: unchanged (no truncation applied)

### 6. FORMATTER CORRUPTS DATA ❌
**File**: `backend/services/rim_qa_loop.py:546-553`  
**Function**: `RIMQALoop._format_tool_observation()`

**PROBLEM CODE:**
```python
elif tool_name == "search_repository" and isinstance(data, list):
    summary = f"[search_repository] Found {len(data)} results:\n"
    for result in data[:10]:
        # LINE 549: Tries to access "path" key that doesn't exist
        path = result.get("path", "?") if isinstance(result, dict) else str(result)[:50]
        summary += f"  - {path}\n"
```

Result:
```
[search_repository] Found 6 results:
  - ?
  - ?
  - ?
  - ?
  - ?
  - ?
```

**ROOT CAUSE:**
- `search_repository` returns results with `"file"` key
- Formatter looks for `"path"` key
- `.get("path", "?")` returns default `"?"`
- LLM receives no usable information

### 7. LLM RECEIVES WORTHLESS DATA ❌

Message appended to conversation:
```
[search_repository] Found 6 results:
  - ?
  - ?
  - ?
  - ?
  - ?
  - ?
```

The LLM cannot extract any paths, filenames, or search results from this message.

## Failure Metrics

| Boundary | Result Count | Content Size | LLM-Visible Content |
|----------|--------------|--------------|---------------------|
| Retriever | 6 | ~1.2KB | Should be present |
| Tool Dispatch | 6 | ~1.2KB | ✓ Present |
| Sanitizer | 6 | ~1.2KB | ✓ Present |
| Formatter | 6 | ~200B | ❌ Lost (shows "?") |
| **LLM Receives** | 6 | ~0B useful | ❌ None |

## Root Cause Analysis

**Mismatch between data structure and formatter:**

1. **Data structure returned by retriever:**
   - Symbol matches: `{"type": "symbol", "file": "...", "symbol": "...", ...}`
   - File matches: `{"type": "file", "file": "...", "size": ..., ...}`
   - Code matches: `{"type": "code", "file": "...", "line": ..., "snippet": "...", ...}`

2. **Formatter expects (incorrectly):**
   - `result.get("path", "?")` — but key is `"file"`, not `"path"`

3. **Result:**
   - All 6 results formatted as `"?"`
   - LLM sees no useful information
   - Cannot perform follow-up file reads

## What Should Happen

Fixed formatter should:
```python
path = result.get("file", "?")  # Use correct key
summary += f"  - {path}\n"

# For code matches, also include line number:
if "line" in result:
    summary += f" (line {result['line']})\n"
```

Expected output:
```
[search_repository] Found 6 results:
  - src/login.py
  - src/auth.py (line 1)
  - src/auth.py (line 2)
  - src/login.py (line 1)
  - src/login.py (line 2)
  - src/login.py (line 3)
```

## Invariant Violation

**Critical invariant broken:**
```
search_repository(query) → 6 results
            ↓
ToolObservation.data → 6 results (content preserved)
            ↓
Sanitizer → 6 results (size OK, no truncation)
            ↓
Formatter → "?" × 6 (content lost)
            ↓
LLM context → no usable information
```

The contract is broken at the formatter boundary.

## Required Fix

**File**: `backend/services/rim_qa_loop.py`  
**Lines**: 546-553  
**Scope**: Fix `_format_tool_observation()` method for `search_repository` case

**Change**: Use correct field name(s) from actual result structure

**Tests needed**: 
- Unit test: formatter receives search_repository results, outputs correct paths
- Integration test: search_repository → LLM sees usable information
- Regression test: "How does login work?" produces non-empty repository context
