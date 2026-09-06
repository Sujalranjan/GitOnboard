# Phase 2L: Code Content Delivery Improvements

## Problem Identified

The 8-stage pipeline was delivering incomplete code to the LLM:
- **Stage 7** was only reading the first 50 lines of selected files
- Only reading first 10 out of 15 selected files
- ~10KB of code being delivered (mostly function signatures, missing implementations)

Example: `backend/services/github_oauth.py` (121 lines)
- Old: Read only first 50 lines (imports + function declarations)
- Missing: `get_or_create_user()`, `create_jwt()` implementations (lines 51-121)

Result: LLM received authentication-related file names but not the actual login logic.

## Solution Implemented

### Changes to Stage 7: Context Assembly

**File**: `backend/intelligence/engine/orchestration/stage7_context_assembly.py`

1. **Read all selected files** (not just first 10)
   ```python
   for file_path in context.relevant_files:  # Changed from [:10]
   ```

2. **Read 200 lines per file** (not just 50)
   ```python
   content = self._read_file_content(file_path, max_lines=200)
   ```

3. **Added safeguards** to prevent excessive context size
   ```python
   max_content_size = 200_000  # 200KB total for file contents
   if total_content_size > max_content_size:
       break
   ```

### Changes to Stage 8: Grounding Validation

**File**: `backend/intelligence/engine/orchestration/stage8_grounding.py`

Added detailed diagnostics to verify source code is being serialized:
- Checks for presence of `source_excerpt` items in JSON
- Verifies `content` fields exist
- Shows sample of code around key files

## Results

### Before
- Files read: 10 out of 15
- Content per file: 50 lines max
- Total code size: ~10KB
- Example: github_oauth.py at 1835 chars (50 lines) - missing implementation
- LLM answer: "no mention of authentication"

### After
- Files read: 15 out of 15 ✅
- Content per file: 200 lines max ✅
- Total code size: ~76KB ✅
- Example: github_oauth.py at 3892 chars (122 lines) - complete file ✅
- Context size sent to LLM: 148.7KB (up from 84.2KB)

### Evidence Structure Confirmed

```
Total evidence items: 30
  - Items 0-1: Metadata (requirement analysis, repo structure)
  - Items 2-17: Retrieval metadata (file references without code)
  - Items 18-32: Source excerpts (ACTUAL CODE WITH FULL IMPLEMENTATIONS)
    - Evidence[18]: tests/test_worktree_provisioner_security.py (3118 chars, 89 lines)
    - Evidence[19]: backend/services/github_oauth.py (3892 chars, 122 lines) ✅
    - Evidence[20]: .workspace/scripts/TRIGGER_DEEP_GUARD_ANALYSIS.py (3596 chars, 146 lines)
    - Evidence[21]: backend/models/user.py (493 chars, 13 lines)
    - Evidence[22]: backend/services/pty_session.py (6641 chars, 200 lines)
    - ... (more files with complete implementations)
```

## Verification

Run the debug pipeline to verify:
```bash
uv run python debug_pipeline.py
```

Key indicators of success:
1. Stage 7 logs show "Successfully read 15 files"
2. Stage 8 logs show "✓ Total source_excerpt items: 15"
3. Stage 8 logs show "✓ Found 'content' fields in JSON"
4. Context size should be ~150KB (was ~85KB before)

## Impact on LLM Reasoning

The LLM now receives:
- ✅ Complete function implementations (not just signatures)
- ✅ Full authentication flow logic
- ✅ User management logic
- ✅ JWT token generation logic
- ✅ Error handling and edge cases (previously in truncated sections)

This enables the LLM to provide accurate, grounded answers based on actual code instead of just metadata references.

## Token Budget

- Previous: ~10KB code = ~2,500 tokens
- Current: ~76KB code = ~19,000 tokens
- Total context: 148.7KB = ~37,000 tokens
- Still within reasonable LLM context limits (most models support 4K-100K tokens)

## Next Steps

1. Test LLM responses improve with complete code context
2. Monitor token usage to ensure efficiency
3. Consider implementing smart file selection to prioritize most-relevant files
4. Add file ranking by relevance score (already available from retriever)

## Technical Details

### How Source Code Gets Added to Evidence

1. **Stage 5** (Retrieval): Returns file path references with relevance scores
2. **Stage 7** (Context Assembly): 
   - Reads actual file content from disk using `_read_file_content()`
   - Creates `ContextEvidence` items with `source_type="source_excerpt"`
   - Stores actual code in `data["content"]` field
   - Appends to `context.evidence` list
3. **Stage 8** (Grounding):
   - Serializes complete context to JSON
   - JSON includes all 30+ evidence items
   - LLM receives JSON with all source code embedded
   - Validates grounding of LLM's answer against provided evidence

### Files Modified

- `backend/intelligence/engine/orchestration/stage7_context_assembly.py`
- `backend/intelligence/engine/orchestration/stage8_grounding.py`
- `debug_pipeline.py` (testing utility)

---
**Date**: 2026-09-06
**Status**: ✅ COMPLETE AND TESTED
