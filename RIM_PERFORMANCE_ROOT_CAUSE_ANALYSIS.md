# ROOT CAUSE ANALYSIS: Why RIM is Performing Poorly

## 🔴 Critical Finding: query_rim Tool Never Called

**Evidence:**
- RIM has `query_rim` tool available in its tool list
- But NO tool calls to `query_rim` exist in the logs
- RIM Entities Accessed = 0 (because query_rim was never used)
- Symbols Retrieved: 1 vs 4 (Baseline found more)

---

## ❌ What's Happening

### RIM Tool Call Sequence (8 calls total)
```
Turn 0: search_repository("login feature")          → Found results
Turn 1: search_repository("authentication")         → Found results  
Turn 2: get_symbol("authenticate")                  → ❌ Wrong symbol name!
Turn 3: get_symbol("authenticate")                  → ❌ Called same thing again!
Turn 4: search_code("login", file_pattern)          → Tried file search
Turn 5: find_files(pattern)                         → Looked for files
Turn 6: search_repository("login route")            → Searched again
Turn 7: search_repository("login function")         → Searched again
(Never called query_rim)
```

### Baseline Tool Call Sequence (11 calls)
```
Turn 0: search_repository("login feature")         → Found results
Turn 1: search_repository("authentication")        → Found results
Turn 2: get_symbol("login")                        → Tried symbol
Turn 3: search_repository("login function")        → Searched again
Turn 4: search_repository("auth")                  → Different query
Turn 5: get_symbol("auth")                         → Found symbol
Turn 6: get_callees("authenticateToken")          → ✅ Found real function!
Turn 7: get_callers("authenticateToken")          → ✅ Analyzed relationships!
Turn 8: get_symbol("authMiddleware")               → ✅ Found key component!
Turn 9: get_callees("authMiddleware")              → ✅ Analyzed it!
Turn 10: get_symbol("hashToken")                   → ✅ Found auth component!
```

---

## 🎯 Why RIM Fails

### Problem #1: LLM Doesn't Know About RIM Metadata
- RIM system prompt **should** include:
  ```
  ### RIM_METADATA
  Repository Intelligence Graph facts (structural relationships):
  [... metadata facts here ...]
  Use these facts to understand the repository structure. Query the `query_rim` tool for additional details.
  ```
- **But**: Metadata is likely EMPTY or NOT BEING INCLUDED

### Problem #2: LLM Never Chooses to Use query_rim
- Even though query_rim is in the tool list
- LLM makes 8 tool calls but never calls query_rim
- Suggests: Either metadata wasn't shown, or it's not helpful

### Problem #3: Wrong Symbol Names
- RIM tries `get_symbol("authenticate")` twice (turns 2-3)
- But there's no symbol called "authenticate" 
- Should have tried "authenticateToken" (what Baseline found)
- Without metadata guidance, LLM picks wrong symbols

### Problem #4: Metadata Might Be Empty
- Check: Is `build_rim_metadata_block()` finding any entities for "login"?
- The HybridRetriever might not be finding "login" related facts
- If metadata is empty → RIM section won't be included → No guidance

---

## 📊 Token Usage Reveals the Issue

From the UI comparison:
```
RIM Metadata Tokens: 25 (should be much higher if metadata was substantial!)
```

- If RIM had good metadata, we'd see 100+ tokens of metadata
- 25 tokens = very minimal metadata (maybe just header text)
- This suggests: **RIM metadata block is nearly empty**

---

## 💡 The Real Issues (In Order of Severity)

1. **🔴 RIM Metadata Generation Failure**
   - `build_rim_metadata_block()` is returning empty or minimal metadata
   - HybridRetriever isn't finding "login"-related entities
   - FactStore might not have login functions cached

2. **🔴 System Prompt Truncation in Logging**
   - Logs only capture first 500 chars of system prompt
   - Can't see if metadata was actually included
   - Need to check actual prompt sent to LLM

3. **🟡 LLM Strategy Without Guidance**
   - Without metadata, LLM tries random symbol names ("authenticate")
   - Gets stuck on wrong symbol twice
   - Never thinks to use query_rim tool

4. **🟡 Fallback to Broad Searches**
   - RIM resorts to repeated searches and file patterns
   - Uses search_code, find_files (tools Baseline doesn't use)
   - But never gets good results

---

## ✅ How to Fix This

1. **Verify RIM Metadata Generation**
   ```python
   # Check what entities are found for "login"
   retriever.search("login", top_k=5)
   # Should return: login functions, auth middleware, etc.
   ```

2. **Log the Full System Prompt**
   - Currently only logging first 500 chars
   - Should log full prompt to see if metadata is included
   - Or at least log metadata block size

3. **Verify FactStore Contents**
   - Is login-related data indexed?
   - Are relationships stored?
   - Is graph traversal working?

4. **Check HybridRetriever**
   - Is semantic search working?
   - Is lexical indexing finding auth terms?
   - Are seeds identified correctly?

---

## 📋 Summary

**Without RIM:** Baseline systematically finds key components (authMiddleware, authenticateToken, hashToken) through intelligent exploration

**With RIM:** LLM tries random guesses (authenticate, authenticate again) and gives up

**Root Cause:** RIM metadata is empty or not being shown to the LLM

**Impact:** RIM is WORSE than baseline because it has no guidance and wastes turns guessing

