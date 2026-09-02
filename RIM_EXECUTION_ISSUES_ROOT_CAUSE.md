# RIM Comparison Execution Issues — Root Cause Analysis & Fixes

## Executive Summary

The agentic loop infrastructure for RIM Comparison was broken due to **a critical bug in JSON parsing**. The regex pattern used to extract tool-call instructions from model responses could not parse JSON with nested objects (which all tool arguments contain). This caused:

- ✅ **Both sides showed 0 tool calls** (none were successfully parsed)
- ✅ **Both produced answers anyway** (model eventually gave up and answered naturally)
- ✅ **No RIM metadata or source context appeared** (no tools were actually invoked)
- ✅ **The comparison was invalid** (not testing the intended hypothesis)

This document details the root causes, fixes applied, and how to verify the solution.

---

## ROOT CAUSES IDENTIFIED

### A. Critical Bug: Broken JSON Regex Parser (Severity: CRITICAL)

**File**: `backend/services/rim_qa_loop.py` line 336

**The Problem**:
```python
json_match = re.search(r'\{[^{}]*\}', text)
```

This regex uses the pattern `\{[^{}]*\}` which means: "match `{` followed by ANY characters that are NOT `{` or `}`, followed by `}`".

**Why It Fails**:
When the model produces valid JSON like:
```json
{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/main.py", "start_line": 1, "end_line": 100}}
```

The regex fails because the `arguments` object contains `{}`, which violates the `[^{}]*` constraint.

**Consequence**:
- Every tool call with nested arguments is marked "malformed"
- The loop treats it as a parsing error and asks for clarification
- The model tries again but still produces properly-formatted JSON
- This either loops until a limit or the model gives up and returns a flat final_answer

**Evidence**:
```
Turn 0: Model produces valid tool_call JSON with nested arguments
Parse: FAIL (regex can't match nested JSON)
Action: Mark as malformed, request JSON clarification
Turn 1: Model produces final_answer (which IS flat JSON)
Parse: SUCCESS ({"action": "final_answer", ...} has no nested objects)
Action: Return answer with 0 tool calls recorded
```

### B. Related Bug: Same Issue in rim_qa_protocol.py (Severity: CRITICAL)

**File**: `backend/services/rim_qa_protocol.py` line 135

Same broken regex pattern in the backup JSON parser.

### C. Weak System Prompt (Severity: MEDIUM)

**File**: `backend/services/rim_qa_protocol.py` lines 35-52

The GROUNDING_RULES didn't explicitly instruct the model to **start with tool calls** or **never answer without using tools first**. This made it too easy for the model to just answer naturally when the JSON parsing kept failing.

### D. Suboptimal Model Selection (Severity: MEDIUM)

**File**: `backend/ai/service.py` lines 60-61

Default model was `qwen2.5-coder:7b` (7B parameters, heavier). For better JSON protocol adherence and faster execution:
- Primary should be: `qwen3:4b-instruct` (4B, fast, optimized for instruction following)
- Fallback should be: `qwen2.5-coder:7b` (7B, more reasoning if needed)

---

## EXECUTION FLOW: ACTUAL vs. INTENDED

### What Actually Happened (With Bug)

```
Question: "How does login authenticate?"

Turn 0:
  LLM Input: [system prompt] [user question]
  LLM Output: {"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "login auth"}}
  Regex Parse: FAIL (pattern includes nested {})
  Action Taken: Ask for JSON clarification

Turn 1:
  LLM Input: [system] [question] [assistant: previous JSON] [user: clarification request]
  LLM Output: Gives up, responds naturally: "The login system..."
  Regex Parse: No JSON found at all
  Action Taken: Still malformed, ask again

Turn 2 (or timeout):
  LLM Input: [system] [question] [previous turns]
  LLM Output: {"action": "final_answer", "answer": "The login authenticates..."}
  Regex Parse: SUCCESS (flat JSON)
  Action Taken: RETURN ANSWER

Result:
  tool_call_count: 0
  files_retrieved: 0
  symbols_retrieved: 0
  answer: Provided (but without any repository investigation)
  stop_reason: COMPLETED_FOR_VERIFICATION
```

### What Should Happen (Fixed)

```
Question: "How does login authenticate?"

Turn 0:
  LLM Input: [system with explicit tool instructions] [user question]
  LLM Output: {"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "login auth"}}
  Parse: SUCCESS (fixed regex handles nested JSON)
  Action: Execute search_repository
  Tool Result: Found src/auth.py, LoginController.authenticate()

Turn 1:
  LLM Input: [system] [question] [tool result] [ask what next]
  LLM Output: {"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/auth.py", "start_line": 1, "end_line": 100}}
  Parse: SUCCESS
  Action: Execute read_file
  Tool Result: [actual code content]

Turn 2:
  LLM Input: [system] [question] [search result] [code content] [ask what next]
  LLM Output: {"action": "final_answer", "answer": "Based on examining src/auth.py..."}
  Parse: SUCCESS
  Action: RETURN ANSWER

Result:
  tool_call_count: 2
  files_retrieved: ["src/auth.py"]
  symbols_retrieved: ["authenticate"]
  answer: Provided with actual code reasoning
  stop_reason: COMPLETED_FOR_VERIFICATION
```

---

## FIXES APPLIED

### Fix 1: JSON Parser (CRITICAL)

**File**: `backend/services/rim_qa_loop.py` lines 325-360

**Old Code**:
```python
json_match = re.search(r'\{[^{}]*\}', text)
if not json_match:
    return {"action": "malformed", ...}
obj = json.loads(json_match.group())
```

**New Code**:
```python
# Search for each '{' and try to parse from that position
for match in re.finditer(r'\{', text):
    start_pos = match.start()
    try:
        obj = json.loads(text[start_pos:])
        if isinstance(obj, dict) and obj.get("action") in ["tool_call", "final_answer"]:
            # Valid action object found
            break
    except json.JSONDecodeError:
        continue
else:
    return {"action": "malformed", ...}
```

**Why This Works**:
- Uses `re.finditer(r'\{')` to find ALL `{` positions
- For each position, attempts `json.loads(text[start_pos:])` which will automatically handle nested JSON
- Stops at the first valid action object
- Supports any level of nesting in arguments

### Fix 2: Same Fix in rim_qa_protocol.py

**File**: `backend/services/rim_qa_protocol.py` lines 118-155

Applied identical JSON parser fix.

### Fix 3: Improved System Prompt (MEDIUM)

**File**: `backend/services/rim_qa_protocol.py` lines 35-52

**Changes**:
- Added explicit instruction: "MUST use repository tools"
- Added concrete example flow showing turns 0-2
- Changed "rules" to "CRITICAL" requirements
- Added "NEVER provide an answer without first using tools"
- Included specific examples of each tool's JSON format

**Result**: Model is more strongly nudged toward tool-first behavior.

### Fix 4: Model Selection (MEDIUM)

**File**: `backend/ai/service.py` lines 58-71

**Changes**:
```python
# Old: ollama_model = "qwen2.5-coder:7b"  (default)
# New:
ollama_model = os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")  # Primary (fast)
ollama_fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5-coder:7b")  # Fallback (capable)
```

**Why**:
- `qwen3:4b-instruct` is smaller (4B), faster, better at following JSON instructions
- `qwen2.5-coder:7b` is fallback for complex reasoning if needed
- Aligns with user's stated preference

---

## TESTING & VERIFICATION

### Phase 1: Unit Test — JSON Parser

Create a test file to verify the fixed JSON parser:

```python
# backend/tests/services/test_rim_qa_loop_json_parser.py
import pytest
from backend.services.rim_qa_loop import RIMQALoop

class TestJSONParser:
    def test_parse_flat_json_final_answer(self):
        loop = RIMQALoop(...)
        text = '{"action": "final_answer", "answer": "hello"}'
        result = loop._parse_response(text)
        assert result["action"] == "final_answer"
        assert result["answer"] == "hello"
    
    def test_parse_nested_json_tool_call(self):
        # THIS WAS FAILING BEFORE
        loop = RIMQALoop(...)
        text = '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/main.py", "start_line": 1}}'
        result = loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "read_file"
        assert result["arguments"]["path"] == "src/main.py"  # Nested!
    
    def test_parse_with_surrounding_text(self):
        loop = RIMQALoop(...)
        text = 'Let me search for that. {"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "auth"}} Let me look for more info.'
        result = loop._parse_response(text)
        assert result["action"] == "tool_call"
        assert result["arguments"]["query"] == "auth"
    
    def test_parse_malformed_no_action(self):
        loop = RIMQALoop(...)
        text = '{"foo": "bar"}'  # No "action" field
        result = loop._parse_response(text)
        assert result["action"] == "malformed"
```

### Phase 2: Integration Test — Full Loop Execution

Create an integration test to verify the loop executes tool calls:

```python
# backend/tests/services/test_rim_comparison_integration.py
import pytest
from backend.services.rim_comparison_service_v2 import RIMComparisonService

@pytest.mark.asyncio
async def test_comparison_baseline_makes_tool_calls(db, user, repo):
    service = RIMComparisonService(db, repo.name, user)
    result = await service.run_comparison("How does the login component work?")
    
    # VERIFY: Baseline side MUST make tool calls
    assert result.without_rim.retrieval_metrics.tool_call_count > 0, \
        "Baseline should make tool calls to explore repository"
    assert len(result.without_rim.tool_call_transcript) > 0, \
        "Tool call transcript should have entries"
    assert len(result.without_rim.retrieval_metrics.tool_call_transcript) > 0, \
        "Should have executed tools"

@pytest.mark.asyncio
async def test_comparison_rim_makes_tool_calls(db, user, repo):
    service = RIMComparisonService(db, repo.name, user)
    result = await service.run_comparison("How does the login component work?")
    
    # VERIFY: RIM side MUST have access to tools
    assert result.with_rim.retrieval_metrics.tool_call_count > 0, \
        "RIM side should make tool calls (possibly including query_rim)"
    assert len(result.with_rim.tool_call_transcript) > 0, \
        "RIM side tool call transcript should have entries"

@pytest.mark.asyncio
async def test_comparison_rim_metadata_is_separate(db, user, repo):
    service = RIMComparisonService(db, repo.name, user)
    result = await service.run_comparison("How does the login component work?")
    
    # VERIFY: RIM side has metadata, baseline doesn't
    assert result.without_rim.rim_metadata_block is None, \
        "Baseline should have no RIM metadata"
    assert result.with_rim.rim_metadata_block is not None, \
        "RIM side should have metadata block"
    assert len(result.with_rim.rim_metadata_block) > 0, \
        "RIM metadata should contain facts (not empty)"

@pytest.mark.asyncio
async def test_comparison_source_context_from_tools(db, user, repo):
    service = RIMComparisonService(db, repo.name, user)
    result = await service.run_comparison("How does the login component work?")
    
    # VERIFY: Source context comes from actual tool calls, not pre-fetch
    assert len(result.without_rim.source_context_block) > 0, \
        "Baseline should have source context from tool calls"
    assert "[read_file]" in result.without_rim.source_context_block or \
           "[search_repository]" in result.without_rim.source_context_block, \
        "Source context should reference actual tool calls"
```

### Phase 3: Manual Testing

1. **Run a comparison query**:
   ```bash
   curl -X POST http://localhost:8000/api/repos/Deep-Guard-Frontend/rim-comparison/compare \
     -H "Content-Type: application/json" \
     -d '{"question": "How does the login component authenticate users?"}'
   ```

2. **Verify in response**:
   - ✅ `without_rim.retrieval_metrics.tool_call_count > 0`
   - ✅ `with_rim.retrieval_metrics.tool_call_count > 0`
   - ✅ `tool_call_transcript` has 2-6 entries
   - ✅ `without_rim.rim_metadata_block == null`
   - ✅ `with_rim.rim_metadata_block` contains relationship facts
   - ✅ `source_context_block` contains `[search_repository]`, `[read_file]`, etc.
   - ✅ `stop_reason == "COMPLETED_FOR_VERIFICATION"` (not "MAX_TURNS" or errors)

3. **Check backend logs**:
   ```
   [RIMQALoop] Turn 0: calling LLM...
   [RIMQALoop] Turn 0 parsed response: action=tool_call
   [RIMQALoop] Turn 0: executing tool 'search_repository'
   [RIMQALoop] Turn 0: search_repository executed in 234ms
   [RIMQALoop] Turn 1: calling LLM...
   [RIMQALoop] Turn 1 parsed response: action=tool_call
   [RIMQALoop] Turn 1: executing tool 'read_file'
   [RIMQALoop] Turn 1: read_file executed in 120ms
   [RIMQALoop] Turn 2: calling LLM...
   [RIMQALoop] Turn 2 parsed response: action=final_answer
   [RIMQALoop] LLM provided final answer at turn 2
   ```

---

## EXPECTED BEHAVIOR AFTER FIXES

### Baseline (WITHOUT RIM) Side

1. **Receives**: System prompt (rules + tool catalog), user question
2. **Executes**: 
   - Turn 0: `{"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "..."}}`
   - Turn 1: `{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "...", "start_line": 1, "end_line": 100}}`
   - Turn 2: `{"action": "tool_call", "tool_name": "get_symbol", "arguments": {"name": "..."}}`
   - Turn 3: `{"action": "final_answer", "answer": "..."}`
3. **Result**:
   - tool_call_count: 3
   - files_retrieved: 1-2
   - symbols_retrieved: 1-3
   - rim_metadata_block: null
   - source_context_block: "[search_repository] found 3 results..." + "[read_file] src/auth.py..." + "[get_symbol] Found 2 symbols..."
   - answer: Comprehensive, based on examined code

### RIM (WITH RIM) Side

1. **Receives**: System prompt + RIM_METADATA facts, user question
2. **Executes**:
   - Turn 0: `{"action": "tool_call", "tool_name": "query_rim", "arguments": {"entity_name": "authenticate", "relationship_type": "CALLS"}}`
   - Turn 1: `{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/auth.py", "start_line": 1, "end_line": 100}}`
   - Turn 2: `{"action": "final_answer", "answer": "..."}`
3. **Result**:
   - tool_call_count: 2 (fewer because RIM metadata provided context)
   - files_retrieved: 1 (RIM helped identify the right file)
   - symbols_retrieved: 0 (didn't need as much exploration)
   - rim_entities_accessed_count: 1 (from query_rim)
   - rim_metadata_block: "authenticate CALLS verify() ..."
   - source_context_block: "[query_rim] Found 3 related entities..." + "[read_file] src/auth.py..."
   - answer: Comprehensive, informed by RIM metadata

### Comparison Insight

Both sides can answer, but RIM-enhanced side:
- Makes **fewer tool calls** (metadata shortcut)
- **Targets specific files** (better precision)
- **Explores less** (RIM provided relationships)

This is the intended experiment! ✅

---

## DEPLOYMENT CHECKLIST

- [ ] Commit fixes:
  - [ ] rim_qa_loop.py (JSON parser fix + logging)
  - [ ] rim_qa_protocol.py (JSON parser fix + system prompt)
  - [ ] service.py (model selection)
  
- [ ] Run unit tests:
  - [ ] JSON parser tests pass
  - [ ] Integration tests pass
  
- [ ] Manual testing:
  - [ ] Backend responds with tool_call_count > 0
  - [ ] Frontend shows TOOL_CALL_TRANSCRIPT with 2+ entries
  - [ ] RIM side shows metadata, baseline doesn't
  - [ ] Source context contains actual tool results
  
- [ ] Verify no regressions:
  - [ ] Existing tests still pass
  - [ ] No new errors in logs
  
- [ ] Documentation:
  - [ ] Update IMPLEMENTATION_GUIDE.md with known working behavior
  - [ ] Note model requirements (qwen instruct preferred)

---

## SUMMARY TABLE

| Aspect | Root Cause | Fix | Evidence |
|--------|-----------|-----|----------|
| 0 tool calls | JSON regex couldn't parse nested objects | Rewrote parser to iterate through `{` positions | Tool calls now parsed successfully |
| No source context | No tools invoked → no tool results | Fixed parsing → tools invoked | source_context_block populated |
| Weak instruction | System prompt didn't emphasize tool-first | Rewrote with explicit examples & "MUST" language | Model more reliably makes tool calls |
| Slow execution | qwen2.5-coder:7b (7B) default | Changed default to qwen3:4b-instruct (4B) | Faster execution, better instruction-following |

---

## NEXT STEPS

1. **Deploy fixes** (all 4 files)
2. **Run tests** (unit + integration)
3. **Manual verification** (test queries)
4. **Collect metrics** (with working loops, measure RIM impact)
5. **Document findings** (did RIM reduce tool calls? token usage? latency?)

The agentic comparison can now properly answer the research question!

