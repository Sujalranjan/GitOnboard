# Comprehensive Logging System Guide

**Purpose:** Track all data flow from user query to LLM responses, identifying silent failures and debugging issues.

---

## Overview

The comprehensive logging system captures:
1. **Frontend Queries** - What users ask
2. **LLM Requests** - What's sent to the model (system prompt, context, tools)
3. **LLM Responses** - What the model returns (text, tokens, stop reason)
4. **Tool Calls** - Every tool execution with arguments and results
5. **RIM Contributions** - How RIM metadata impacts each stage
6. **Metrics** - Comparison between baseline and RIM
7. **Errors** - Full stack traces and context

---

## Directory Structure

```
logs/
├── {session_id}_{repository}_{timestamp}/
│   ├── 01_query_{request_id}.json
│   ├── 02_llm_request_{request_id}_baseline.json
│   ├── 02_llm_request_{request_id}_rim.json
│   ├── 02_system_prompt_{request_id}_baseline.txt
│   ├── 02_system_prompt_{request_id}_rim.txt
│   ├── 03_llm_response_{request_id}_baseline.json
│   ├── 03_llm_response_{request_id}_rim.json
│   ├── 03_response_text_{request_id}_baseline.txt
│   ├── 03_response_text_{request_id}_rim.txt
│   ├── 04_tool_call_{request_id}_baseline_turn1_search_code.json
│   ├── 04_tool_call_{request_id}_baseline_turn2_read_file.json
│   ├── 04_tool_result_{request_id}_baseline_turn1_search_code.json
│   ├── 04_tool_result_{request_id}_baseline_turn2_read_file.json
│   ├── 04_tool_call_{request_id}_rim_turn1_query_rim.json
│   ├── 05_rim_contribution_{request_id}_metadata_building.json
│   ├── 05_rim_contribution_{request_id}_query_execution.json
│   ├── 06_metrics_{request_id}.json
│   ├── 07_completion_{request_id}.json
│   └── 99_error_{request_id}_{stage}.json (if error occurs)
├── errors/
│   ├── {request_id}_{stage}.json
│   └── {request_id}_{repository}.json
└── [other type directories...]
```

---

## Log File Formats

### 01_query_{request_id}.json
**What:** Initial frontend query

```json
{
  "timestamp": "2026-09-02T13:22:00.123456",
  "repository": "Deep-Guard-Backend",
  "question": "How does user authentication work?",
  "session_id": "user123",
  "request_id": "abc12345",
  "user_email": "user@example.com"
}
```

### 02_llm_request_{request_id}_{baseline|rim}.json
**What:** LLM request before sending

```json
{
  "timestamp": "2026-09-02T13:22:01.234567",
  "request_id": "abc12345",
  "session_id": "user123",
  "model": "qwen3:4b-instruct",
  "provider": "ollama",
  "is_rim": false,
  "system_prompt_length": 2500,
  "system_prompt_hash": "a1b2c3d4e5f6g7h8",
  "user_message": "How does user authentication work?",
  "tools_available": ["search_code", "read_file", "get_symbol"],
  "context_tokens_estimate": 3500
}
```

**Related File:** `02_system_prompt_{request_id}_{baseline|rim}.txt` - Full system prompt text

### 03_llm_response_{request_id}_{baseline|rim}.json
**What:** LLM response received

```json
{
  "timestamp": "2026-09-02T13:22:05.567890",
  "request_id": "abc12345",
  "session_id": "user123",
  "response_text": "Based on the code analysis...",
  "stop_reason": "end_turn",
  "prompt_tokens": 1500,
  "completion_tokens": 800,
  "total_tokens": 2300,
  "latency_ms": 4250.5,
  "model": "qwen3:4b-instruct"
}
```

**Related File:** `03_response_text_{request_id}_{baseline|rim}.txt` - Full response text

### 04_tool_call_{request_id}_{baseline|rim}_turn{N}_{tool_name}.json
**What:** Individual tool execution

```json
{
  "timestamp": "2026-09-02T13:22:02.345678",
  "request_id": "abc12345",
  "session_id": "user123",
  "turn_number": 1,
  "tool_name": "search_code",
  "tool_arguments": {
    "query": "authentication",
    "limit": 5
  },
  "is_rim": false,
  "execution_time_ms": 125.3,
  "success": true,
  "error": null,
  "result_size_bytes": 2450,
  "result_summary": "{\"results\": [{\"file\": \"auth.js\", \"line\": 42, ...}]}"
}
```

**Related File:** `04_tool_result_{request_id}_{baseline|rim}_turn{N}_{tool_name}.json` - Full result

### 05_rim_contribution_{request_id}_{stage}.json
**What:** How RIM metadata contributed at each stage

```json
{
  "timestamp": "2026-09-02T13:22:03.456789",
  "request_id": "abc12345",
  "session_id": "user123",
  "stage": "metadata_building",
  "rim_entities_found": 12,
  "rim_relationships_found": 23,
  "rim_confidence_score": 0.85,
  "impacted_tools": ["query_rim", "search_code"],
  "metadata_block_size_bytes": 5120
}
```

**Stages:**
- `metadata_building` - Building RIM metadata block
- `query_execution` - Using RIM for query execution
- `tool_selection` - RIM guiding tool choice
- `answer_refinement` - RIM improving final answer

### 06_metrics_{request_id}.json
**What:** Final comparison metrics

```json
{
  "timestamp": "2026-09-02T13:22:10.789012",
  "request_id": "abc12345",
  "session_id": "user123",
  "repository": "Deep-Guard-Backend",
  "question": "How does user authentication work?",
  "baseline_tool_calls": 7,
  "rim_tool_calls": 5,
  "baseline_files_retrieved": 2,
  "rim_files_retrieved": 1,
  "baseline_symbols_retrieved": 3,
  "rim_symbols_retrieved": 2,
  "rim_entities_accessed": 5,
  "baseline_latency_ms": 2500.0,
  "rim_latency_ms": 1800.0,
  "semantic_degradation": null,
  "answer_quality_score": null,
  "failure_detected": false,
  "failure_reason": null
}
```

### 99_error_{request_id}_{stage}.json
**What:** Complete error information

```json
{
  "timestamp": "2026-09-02T13:22:08.123456",
  "request_id": "abc12345",
  "session_id": "user123",
  "stage": "llm_request",
  "error_type": "TimeoutError",
  "error_message": "LLM request timed out after 60 seconds",
  "traceback": "Traceback (most recent call last):\n  File \"...\", line 123, in run_comparison\n    ...",
  "context": {
    "model": "qwen3:4b-instruct",
    "provider": "ollama",
    "is_rim": true,
    "retry_count": 3
  }
}
```

---

## Finding Failures

### Method 1: Check Error Directory
```bash
ls -lart /home/dheeraj/repository_intelligence_platform/logs/errors/
# Shows most recent errors
```

### Method 2: Search for Silent Failures
```bash
# Find requests where failure_detected=true
grep -l "\"failure_detected\": true" /home/dheeraj/repository_intelligence_platform/logs/*/06_metrics_*.json

# Check specific failure
cat /home/dheeraj/repository_intelligence_platform/logs/errors/{request_id}_{stage}.json
```

### Method 3: Find Incomplete Requests
```bash
# Find requests with no completion file
for session_dir in /home/dheeraj/repository_intelligence_platform/logs/*/; do
  if [ ! -f "$session_dir/07_completion_"*.json ]; then
    echo "Incomplete: $session_dir"
  fi
done
```

### Method 4: Trace Request Through All Stages
```bash
# Find all files for a specific request
REQUEST_ID="abc12345"
find /home/dheeraj/repository_intelligence_platform/logs -name "*${REQUEST_ID}*" | sort

# View all stages in order
ls -1 /home/dheeraj/repository_intelligence_platform/logs/*/${REQUEST_ID}* | head -20
```

### Method 5: Compare Tool Call Differences
```bash
# Find tool calls that succeeded in baseline but failed in RIM
for f in /home/dheeraj/repository_intelligence_platform/logs/*/04_tool_call_*_rim_*.json; do
  if grep -q "\"success\": false" "$f"; then
    request_id=$(basename "$f" | cut -d_ -f4)
    baseline_version="${f/_rim_/_baseline_}"
    if [ -f "$baseline_version" ]; then
      if grep -q "\"success\": true" "$baseline_version"; then
        echo "Tool failed in RIM but succeeded in baseline: $f"
      fi
    fi
  fi
done
```

---

## Common Silent Failure Patterns

### 1. Semantic Degradation Not Logged
**Symptom:** Metrics show `"semantic_degradation": null` but RIM response incomplete

**How to Find:**
```bash
# Check if semantic degradation is set
grep "semantic_degradation" /home/dheeraj/repository_intelligence_platform/logs/*/06_metrics_*.json

# If null, check retriever logs for warnings
grep "Semantic" /home/dheeraj/repository_intelligence_platform/logs/*/04_tool_call_*.json
```

### 2. Tool Call Arguments Not Captured
**Symptom:** Tool result is empty but arguments look correct

**How to Find:**
```bash
# Check tool arguments
cat /home/dheeraj/repository_intelligence_platform/logs/*/*/*_tool_call_*.json | \
  grep -A5 "tool_arguments"

# Check if result file exists
ls -la /home/dheeraj/repository_intelligence_platform/logs/*/04_tool_result_*.json
```

### 3. LLM Stop Reason Unexpected
**Symptom:** Response incomplete but no error logged

**How to Find:**
```bash
# Find unusual stop reasons
grep "stop_reason" /home/dheeraj/repository_intelligence_platform/logs/*/03_llm_response_*.json

# Find max_tokens stops
grep '"stop_reason": "length"' /home/dheeraj/repository_intelligence_platform/logs/*/03_llm_response_*.json
```

### 4. RIM Metadata Not Used
**Symptom:** RIM has slower response but no RIM contribution logs

**How to Find:**
```bash
# Check RIM contribution logs exist
ls -la /home/dheeraj/repository_intelligence_platform/logs/*/05_rim_contribution_*.json

# If missing, RIM metadata building failed
grep "rim_contribution" /home/dheeraj/repository_intelligence_platform/logs/*/99_error_*.json
```

### 5. Tool Results Not Used
**Symptom:** Tool executes successfully but doesn't appear in LLM response

**How to Find:**
```bash
# Compare tool arguments with LLM response
REQUEST_ID="abc12345"
echo "Tool executed:"
cat /home/dheeraj/repository_intelligence_platform/logs/*/04_tool_call_*${REQUEST_ID}*.json | \
  grep -E "tool_name|success"

echo "LLM response mentions:"
cat /home/dheeraj/repository_intelligence_platform/logs/*/03_response_text_*${REQUEST_ID}*.txt
```

---

## Analysis Commands

### Get Complete Request Timeline
```bash
#!/bin/bash
REQUEST_ID=$1
SESSION_DIR="/home/dheeraj/repository_intelligence_platform/logs"

echo "=== Query ==="
cat "$SESSION_DIR"/*/01_query_${REQUEST_ID}.json 2>/dev/null | head -5

echo -e "\n=== Baseline Path ==="
echo "LLM Request:"
grep -H "\"is_rim\": false" "$SESSION_DIR"/*/02_llm_request_${REQUEST_ID}*.json 2>/dev/null
echo "Tool Calls:"
ls -1 "$SESSION_DIR"/*/04_tool_call_*${REQUEST_ID}*baseline* 2>/dev/null | wc -l
echo "LLM Response:"
grep '"total_tokens"' "$SESSION_DIR"/*/03_llm_response_*${REQUEST_ID}*baseline*.json 2>/dev/null

echo -e "\n=== RIM Path ==="
echo "LLM Request:"
grep -H "\"is_rim\": true" "$SESSION_DIR"/*/02_llm_request_${REQUEST_ID}*.json 2>/dev/null
echo "RIM Metadata:"
ls -1 "$SESSION_DIR"/*/05_rim_contribution_${REQUEST_ID}* 2>/dev/null | wc -l
echo "Tool Calls:"
ls -1 "$SESSION_DIR"/*/04_tool_call_*${REQUEST_ID}*rim* 2>/dev/null | wc -l
echo "LLM Response:"
grep '"total_tokens"' "$SESSION_DIR"/*/03_llm_response_*${REQUEST_ID}*rim*.json 2>/dev/null

echo -e "\n=== Metrics ==="
cat "$SESSION_DIR"/*/06_metrics_${REQUEST_ID}.json 2>/dev/null

echo -e "\n=== Errors (if any) ==="
ls -la "$SESSION_DIR"/*/99_error_${REQUEST_ID}* 2>/dev/null || echo "No errors"
```

### Find Requests With Divergence
```bash
#!/bin/bash
# Find requests where RIM and baseline diverged significantly

SESSION_DIR="/home/dheeraj/repository_intelligence_platform/logs"

for metrics in "$SESSION_DIR"/*/06_metrics_*.json; do
  baseline_calls=$(grep -o '"baseline_tool_calls": [0-9]*' "$metrics" | cut -d: -f2 | tr -d ' ')
  rim_calls=$(grep -o '"rim_tool_calls": [0-9]*' "$metrics" | cut -d: -f2 | tr -d ' ')
  
  if [ -n "$baseline_calls" ] && [ -n "$rim_calls" ]; then
    diff=$((baseline_calls - rim_calls))
    if [ "$diff" -gt 3 ]; then
      echo "Large divergence in: $metrics"
      echo "  Baseline: $baseline_calls, RIM: $rim_calls"
    fi
  fi
done
```

---

## Integration with Code

### Using Structured Logger in Services
```python
from backend.logging import StructuredLogger

# In your service
structured_log = StructuredLogger(session_id=user_id, repository=repo_name)

# Log query
structured_log.log_query(question, user_email)

# Log LLM request before sending
structured_log.log_llm_request(
    model="qwen3",
    provider="ollama",
    is_rim=False,
    system_prompt=system_prompt,
    user_message=question,
    tools_available=["search_code", "read_file"],
    context_tokens=2500
)

# Log tool call
structured_log.log_tool_call(
    tool_name="search_code",
    arguments={"query": "auth"},
    is_rim=False,
    turn_number=1,
    execution_time_ms=125.5,
    success=True,
    result=tool_result
)

# Log error
try:
    # something
except Exception as e:
    structured_log.log_error("stage_name", e, {"context_key": "value"})
```

---

## Silent Failure Detection Checklist

When investigating a silent failure:

- [ ] Check error directory for stack traces
- [ ] Verify completion file exists (07_completion)
- [ ] Check if tool calls succeeded (`"success": true`)
- [ ] Verify LLM responses have correct token counts
- [ ] Check RIM contribution logs exist for RIM side
- [ ] Compare baseline and RIM tool call counts
- [ ] Check semantic_degradation field in metrics
- [ ] Verify response_text files contain full responses
- [ ] Check tool_result files exist for successful calls
- [ ] Compare LLM stop_reason between paths
- [ ] Verify system_prompt files differ correctly

---

## Next Steps

1. **Deploy Updated Code** - Push changes to production/staging
2. **Monitor Logs** - Watch for errors as tests run
3. **Analyze Failures** - Use scripts above to find issues
4. **Fix Root Cause** - Stack trace in error files shows exact location
5. **Verify Fix** - Rerun same query and compare logs

