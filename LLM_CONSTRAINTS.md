# LLM Constraints & Configuration

**Date:** 2026-09-08  
**Status:** Current Configuration

---

## 1. Response Limits

### Token Limits
```
Max Response Tokens:    4,096 tokens
Temperature:            0.2 (low, more deterministic)
Default Timeout:        600 seconds (10 minutes)
```

### Token Breakdown (Example)
```
Prompt Tokens:          Variable (depends on context)
Completion Tokens:      Up to 4,096
Total Tokens:           Prompt + Completion
```

---

## 2. Tool Limits

### Tool Calling System
```
Number of Tools:        Unlimited (defined per request)
Tools per Request:      All registered tools available
Concurrent Tool Calls:  Sequential (one at a time)
Tool Timeout:           Inherits from LLM timeout (600s)
```

### Tool Call Format
```
Tool Name:              String identifier
Parameters:             JSON schema validated
Tool Call ID:           Tracked for request correlation
Max Parameters:         Unlimited
```

### Current Agent Tools
```
Agent Tool #1:          Symbol Inspection
Agent Tool #2:          Read File (100 KB per call)
Agent Tool #3:          Query Graph (index-based search)
Agent Tool #4:          Explain Symbol (cached lookups)
Agent Tool #5:          Feature Analysis (multi-step)
```

---

## 3. Model Selection

### LOCAL Mode (Development)
```
Primary Model:          qwen3:4b-instruct
  ├─ Speed:             Fast
  ├─ Memory:            4B parameters (~2-3 GB RAM)
  ├─ Best For:          Quick responses, JSON protocol
  └─ Reasoning:         Good for simple tasks

Fallback Model:         qwen2.5-coder:7b
  ├─ Speed:             Slower
  ├─ Memory:            7B parameters (~4-6 GB RAM)
  ├─ Best For:          Complex coding tasks
  └─ Reasoning:         Better for complex logic

Ollama Timeout:         600 seconds (configurable)
```

### PROD Mode (Production)
```
Primary Provider:       Google Gemini
  ├─ Status:            Priority 1
  ├─ Token Limit:       See Gemini API docs
  └─ Fallback:          Enabled if key provided

Secondary Provider:     OpenRouter
  ├─ Status:            Priority 2
  ├─ Token Limit:       See OpenRouter API docs
  └─ Fallback:          Enabled if key provided

Fallback Chain:         Gemini → OpenRouter → Error
```

### Model Status
```
Temperature:            0.2 (low randomness)
Response Format:        Text or JSON (structured)
Tool Support:           All models support tool calling
```

---

## 4. Request Limits

### Message Constraints
```
Max Messages:           Unlimited (per request)
Message Role Types:     system, user, assistant, tool
Message Content:        String (any length)
Total Context:          Model dependent (~4K-32K tokens)
```

### Conversation Context
```
System Message:         Included in context
Previous Messages:      All included (no auto-truncation)
Max Conversation:       Until token limit reached
Context Window:         4,096 tokens response limit
```

---

## 5. Rate Limiting

### LOCAL (Ollama)
```
Request Rate:           No hard limit (depends on hardware)
Concurrent Requests:    1 at a time (sequential)
Queue Depth:            Handled by FastAPI
Throttling:             None configured
```

### PROD (Cloud)
```
Rate Limit:             Provider specific
  ├─ Gemini:            See Gemini API quotas
  ├─ OpenRouter:        See OpenRouter rate limits
  └─ Fallback:          Auto-retry if rate limited

Error Handling:         Automatic fallback to next provider
Retry Strategy:         Sequential (one provider at a time)
Max Retries:            1 per provider (MAX_PROVIDER_RETRIES)
```

---

## 6. Error Handling

### Retriable Errors (Auto-Fallback)
```
Status Codes:           429, 502, 503, 504
Errors:                 Rate limit, service unavailable, timeout
Action:                 Try next provider
Fallback Chain:         All providers tried in order
```

### Non-Retriable Errors (Immediate Fail)
```
Status Codes:           400, 401, 403
Errors:                 Bad request, auth, schema validation
Action:                 Raise immediately, no fallback
Response:               Error to client
```

---

## 7. Structured Output Limits

### JSON Response Schema
```
Max Schema Fields:      Unlimited
Field Types:            Any valid JSON type
Nested Depth:           Unlimited (JSON limitations apply)
Validation:             Pydantic schema enforced
Timeout:                Same as regular requests (600s)
```

### Response Parsing
```
Format:                 Structured JSON
Validation:             Strict Pydantic validation
Failure Action:         Return NonRetriableError
Retry:                  No retry (schema errors are fatal)
```

---

## 8. File & Context Limits

### File Reading (Tool #2)
```
Max File Size:          100 KB per call
Encoding:               UTF-8
Timeout:                <500ms (blob storage)
Concurrent Reads:       Sequential
Caching:                Azure Blob Storage
```

### Graph Queries (Tool #3)
```
Max Results:            1,000+ symbols per query
Search Depth:           2 levels (configurable)
Query Time:             <100ms (indexed)
Relationship Edges:     1,000+ per symbol
Concurrent Queries:     Sequential
```

### Context Size
```
Average Context:        10-50 KB per agent run
Tool Responses:         <20 KB per tool call
Message History:        Unbounded (until token limit)
Total per Request:      Limited by max_tokens (4,096)
```

---

## 9. Timeouts

### LLM Timeouts
```
Ollama Request:         600 seconds (10 minutes)
Cloud Request:          Provider dependent
Tool Call:              600 seconds (inherited)
Concurrent Calls:       Sequential (no parallelism)
```

### Tool Timeouts
```
File Read:              <500ms (blob storage)
Graph Query:            <100ms (database index)
Symbol Inspection:      <200ms (cached)
Total Pipeline:         <2.5 seconds typical
```

---

## 10. Concurrent Usage

### Sequential Execution
```
LLM Calls:              One at a time (no parallelism)
Tool Calls:             Sequential per request
Agent Runs:             Independent (multiple users OK)
Database Connections:   Pool based (configurable)
```

### System Limits
```
Max Concurrent Agents:  Limited by database pool size
Ollama Concurrency:     Single GPU (4B/7B models)
Memory Limit:           System dependent
CPU Usage:              Shared (single process)
```

---

## 11. API Rate Limits

### FastAPI Rate Limiting
```
Global Rate Limit:      None configured
Per-Endpoint Limit:     None configured
Per-User Limit:         None configured
Throttling:             No built-in throttling
Custom Limits:          Can be added in middleware
```

### Authentication Rate Limits
```
Login Attempts:         None enforced
JWT Token Expiry:       10,080 minutes (7 days)
Session Timeout:        Based on JWT
Concurrent Sessions:    Unlimited per user
```

---

## 12. Current Configuration Summary

| Constraint | Value | Notes |
|---|---|---|
| **Max Response Tokens** | 4,096 | Configurable per request |
| **Temperature** | 0.2 | Low randomness |
| **Request Timeout** | 600s | 10 minutes |
| **Tools per Request** | Unlimited | All available |
| **Concurrent Requests** | Sequential | One at a time |
| **File Size Limit** | 100 KB | Per read |
| **Fallback Chain** | 2 providers | LOCAL: qwen3→qwen-coder |
| **Rate Limiting** | None | Built-in (can add) |
| **Model Context** | 4,096 tokens | Response limit |
| **Error Retry** | Per provider | Retriable vs non-retriable |

---

## 13. How to Increase Limits

### Token Limit
```python
# In backend/ai/schemas.py, LLMRequest class
max_tokens: int = 8192  # Change from 4096
```

### Timeout
```python
# In backend/ai/service.py
ollama_timeout = float(os.environ.get("OLLAMA_TIMEOUT", "1200.0"))  # 20 min
```

### Rate Limiting
```python
# Add to backend/routers/agent.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
@router.post("/runs", dependencies=[Depends(limiter.limit("10/minute"))])
```

### Model Selection
```bash
# Set environment variable
export OLLAMA_MODEL="qwen2.5-coder:7b"  # Use larger model
export OLLAMA_TIMEOUT="1200"            # Increase timeout
```

---

## 14. Monitoring

### Current Metrics Tracked
```
Token Usage:            prompt_tokens + completion_tokens
Response Time:          Measured server-side
Provider:               Which provider handled request
Model:                  Which model used
Tool Calls:             Count + timing per call
Errors:                 Logged with context
```

### To Monitor Limits
```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Monitor resource usage
docker stats repository_intelligence_platform-ollama-1

# Check logs
docker logs -f repository_intelligence_platform-backend-1 | grep LLMService
```

---

## 15. Recommendations

### For Development
✅ Default settings are good  
✅ Use qwen3:4b for speed  
✅ Increase timeout if needed for complex tasks  

### For Production
✅ Use Gemini + OpenRouter failover  
✅ Implement rate limiting  
✅ Monitor token usage  
✅ Add request logging  
✅ Set up alerts for errors  

### For Large Codebases
✅ Increase max_tokens to 8,192  
✅ Use qwen2.5-coder:7b model  
✅ Extend timeout to 900+ seconds  
✅ Implement token-based charging  

---

## Current Status

**All constraints are configurable** through:
1. Environment variables (.env file)
2. Pydantic settings (config.py)
3. Direct code changes (schemas.py)
4. Runtime deployment configuration

**No hard-coded limits** prevent scaling - all values can be adjusted based on your infrastructure.
