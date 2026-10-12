# Comprehensive Empirical Audit: LLM Tool Usage, Execution Dynamics, and Failure Modes

**Audit Date:** 2026-09-29  
**Target Dataset:** Local log runs (`logs/` directory, spanning September 15, 2026 – September 29, 2026)  
**Evaluated Target Repositories:** `Deep-Guard-Integrated-Backend`, `Deep-Guard-Frontend`, `RAG_ASSIGNMENT_LEGAL`  
**Evaluated Models:** `qwen3:4b-instruct`, `openai/gpt-oss-120b`, `nvidia/nemotron-3-ultra-550b-a55b:free`, `gemini-3.8-flash`  
**Execution Context:** GitOnBoard QA Loop Agent (`backend.services.qa_loop`, `backend.services.qa_protocol`)

---

## Executive Summary

An exhaustive empirical audit was conducted on all execution traces, tool call logs, turn diagnostics, system prompts, and model responses stored in the `logs/` directory. Across **33 recorded sessions** comprising **233 distinct tool calls**:

* **Total Tool Calls Executed:** 233
  * **Successful Calls:** 224 (96.1%)
  * **Failed Calls:** 9 (3.9%)
* **Final Session Outcomes:**
  * **Genuinely Completed Textual Answers:** 2 sessions (6.1%)
  * **Incomplete / Empty Final Answers (Max Tool Call Budget Hit with Truncation/Empty Turn):** 13 sessions (39.4%)
  * **Raw Tool Call XML Leaks (Unparsed/Unexecuted Tool Calls returned as Final Answer):** 12 sessions (36.4%)
  * **Aborted / Zero-Tool Call Sessions:** 6 sessions (18.2%)

While tool execution at the infrastructure level boasts a high success rate (96.1%), the **end-to-end task completion rate is severely compromised (only 6.1% valid completed answers)** due to agent looping, tool-call syntax leaks, line-range overflows, and missing synthesis transitions.

---

## 1. Tool Usage Frequency & Success Rates

Tools are ranked from most used to least used across all logged sessions:

| Rank | Tool Name | Total Calls | Successful Calls | Failed Calls | Success Rate (%) | Primary Usage Objective |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | `read_file` | **107** | 99 | 8 | 92.5% | Reading file source code slices and notebooks |
| **2** | `search_repository` | **75** | 75 | 0 | 100.0% | Broad semantic/keyword discovery across repository |
| **3** | `search_code` | **25** | 25 | 0 | 100.0% | Regex/literal symbol searches in code files |
| **4** | `get_tree` | **12** | 12 | 0 | 100.0% | Directory hierarchy inspection |
| **5** | `get_file_outline` | **7** | 7 | 0 | 100.0% | Structural AST file outline (classes, functions, lines) |
| **6** | `get_callers` | **4** | 4 | 0 | 100.0% | Graph backward dependency tracing |
| **7** | `get_callees` | **2** | 2 | 0 | 100.0% | Graph forward call hierarchy tracing |
| **8** | `query_rim` | **2** | 2 | 0 | 100.0% | Direct graph relationship extraction (Layer 4 Fact Store) |
| **9** | `repo_browser.print_tree` | **1** | 0 | 1 | 0.0% | Erroneous hallucinated tool namespace |
| **Total** | | **233** | **224** | **9** | **96.1%** | |

---

## 2. Tool Selection and Justification

Evaluating each tool call against user query intent reveals distinct patterns in tool selection:

### Appropriate Tool Selection
* **Architecture & Authentication Exploration:**  
  * Queries like *"How does authentication work?"* (`2_Deep-Guard-Frontend_20260928_155727`) began logically with `search_repository({'query': 'auth,authentication,login,session'})`, followed by targeted `read_file` calls on `lib/auth.ts`, `middleware.ts`, `Login.tsx`, and `lib/api.ts`. This sequence provided complete factual evidence.
* **Component-Specific Queries:**  
  * Queries like *"List out the filters of the cnn used"* correctly triggered `search_code` and `get_callers` targeting `fileFilter` and CNN layer definitions.

### Suboptimal & Unjustified Selection
* **Namespace Hallucination (`repo_browser.print_tree`):**  
  * In `2_Deep-Guard-Frontend_20260927_221537` (Turn 5), the model invoked `repo_browser.print_tree` instead of `get_tree`, indicating prompt drift or confusion from legacy tools.
* **Excessive `search_repository` Churn in Jupyer Notebook Repos:**  
  * In `1_RAG_ASSIGNMENT_LEGAL_20260922_134637` (*"How does vector database work in this project?"*), the agent called `search_repository` and `search_code` 8 consecutive times with overlapping queries (`vector database`, `embedding`, `RAG, retrieval`, `agent, langgraph`, `langgraph workflow`) without opening the primary notebook where the pipeline was implemented.

---

## 3. Tool Execution & Argument Validation

Overall argument formatting is strong, but recurrent edge-case bugs degrade execution:

### 1. Line Range Overflow Violations (Safe Limit = 250 lines)
The system imposes a guardrail capping single `read_file` queries to 250 lines to prevent context window blowouts. Multiple models repeatedly violated this constraint:
* **Session `1_Deep-Guard-Integrated-Backend_20260923_112402` (Turn 2):**  
  * `read_file({'start_line': 1, 'end_line': 400, 'path': 'app/Deep-Guard-Backend/controllers/authcontroller.js'})`
  * *Error:* `"The requested line range (1-400) spans 400 lines, which exceeds the safe read limit (250 lines)..."`
* **Identical Violations:** Repeated in `2_Deep-Guard-Integrated-Backend_20260927_104011` (Turn 2) and `2_Deep-Guard-Integrated-Backend_20260927_114015` (Turn 2). Models default to arbitrary `400`-line chunks instead of adhering to the documented 250-line maximum.

### 2. Unbounded Reads on Large Files
* **Session `1_Deep-Guard-Integrated-Backend_20260923_103900` (Turn 1):**  
  * Called `read_file({'path': 'app/Deep-Guard-Backend/controllers/authcontroller.js'})` without `start_line`/`end_line`.
  * *Error:* `"Refusing full file read: 'authcontroller.js' has 523 lines... Reading the entire file without line boundaries will cause context overflow..."`
* **Session `1_RAG_ASSIGNMENT_LEGAL_20260922_132130` (Turn 6):**  
  * Full read attempted on `RAG_Assg_Legal_Documents_Starter.ipynb` (755 lines).

### 3. File Non-Existence & Path Guessing
* **Session `1_Deep-Guard-Integrated-Backend_20260922_145943` (Turn 3):**  
  * `read_file({'path': 'app/Deep-Guard-Backend/start.sh'})` -> `File not found`.
* **Session `1_RAG_ASSIGNMENT_LEGAL_20260922_104550` (Turn 9):**  
  * `read_file({'path': 'backend/routers/__init__.py'})` -> `File not found` (path did not exist in that repository).

### 4. Reading Beyond File Bounds
* **Session `1_Deep-Guard-Integrated-Backend_20260922_151825` (Turn 7):**  
  * `read_file({'path': 'app/Deep-Guard-Backend/middleware/fileupload.js', 'start_line': '24', 'end_line': '30'})`
  * *Error:* `"Start line 24 exceeds total file lines (23)"`.

---

## 4. Tool Result Utilization

Tool output synthesis exhibits extreme variance depending on whether the session reaches completion:

* **Exemplary Utilization (`2_Deep-Guard-Frontend_20260928_155727`):**  
  * The model read `lib/auth.ts`, `middleware.ts`, `Login.tsx`, `Signup.tsx`, and `lib/api.ts`. In the final answer, it accurately synthesized the multi-tier flow:
    * Cookie-based session with `accessToken` & `refreshToken`
    * 14-minute client refresh interval from `Login.tsx`
    * Automatic token refresh and 401 interception in `lib/api.ts`
    * Sub-request cookie proxying via Next.js rewrites in `next.config.ts`
* **Complete Non-Utilization (13 Empty Answer Sessions):**  
  * In 13 sessions, models executed between 1 and 10 tool calls, accumulated thousands of tokens of accurate source code, and then terminated with `response_text: ""` or crashed into guardrails without presenting any findings to the user.

---

## 5. Missed and Redundant Calls

Empirical analysis identified substantial redundancy across multiple sessions:

### Exact Duplicate Tool Calls (Same Tool + Identical Arguments)

```text
1. 1_Deep-Guard-Integrated-Backend_20260922_151825:
   Turn 8 & 9: get_callers({"symbol_name": "fileFilter"}) (Exact duplicate)

2. 1_Deep-Guard-Integrated-Backend_20260923_103900:
   Turn 1 & 8: read_file({"path": ".../authcontroller.js", "start_line": 1, "end_line": 100})
   Turn 2 & 9: read_file({"path": ".../authcontroller.js", "start_line": 100, "end_line": 250})

3. 1_RAG_ASSIGNMENT_LEGAL_20260922_104550:
   Turn 1 & 5: read_file({"path": "RAG_Assg_Legal_Documents_Starter.ipynb"})

4. 2_Deep-Guard-Frontend_20260927_221537:
   Turn 7 & 8: search_repository({"path": "lib", "query": "store"})

5. 2_Deep-Guard-Frontend_20260928_155930:
   Turn 1, 3, 5: read_file({"path": "lib/auth.ts", "start_line": 1, "end_line": 400}) (Executed 3 times!)
   Turn 7 & 9: read_file({"path": "lib/auth.ts", "start_line": 28, "end_line": 80})

6. 2_Deep-Guard-Integrated-Backend_20260929_063152:
   Turn 5, 6, 8: read_file({"path": ".../authcontroller.js", "start_line": 18, "end_line": 58}) (Executed 3 times!)
   Turn 7 & 9: read_file({"path": ".../authcontroller.js", "start_line": 126, "end_line": 171})
```

### Root Cause of Repetitive Calls
When an LLM executes a tool call, if the tool result does not immediately contain the final answer or if the model's scratchpad loses state, smaller models (`qwen3:4b-instruct`, `openai/gpt-oss-120b`) re-issue the exact same tool call rather than progressing to callers, references, or synthesizing results.

---

## 6. Answer Correctness and Grounding

When answers were produced, grounding accuracy diverged drastically by scenario:

1. **Grounded & Factually Verifiable:**  
   * `2_Deep-Guard-Frontend_20260928_155727`: Directly cited line numbers (`lines 39-76`, `line 93-106`), accurately referenced Next.js rewrite mechanisms, and correctly identified endpoints (`/auth/login`, `/api/account/me`).
2. **Illusionary Grounding / Misinterpretation of Notebook Blobs:**  
   * In `1_RAG_ASSIGNMENT_LEGAL_20260922_104550`, the model read a raw Jupyter notebook output containing 200 lines of `pip install -r requirements.txt` terminal logs. Instead of extracting the vector database information (Qdrant), the model hallucinated that the user was running a terminal session:
     > *"It looks like the content you've shared is a long output from a Python environment (likely a pip install)..."*
     The model then provided a generic tutorial on building a LangChain RAG with FAISS (which was not used in the repository).
3. **Conversational Evasion:**  
   * In `1_Deep-Guard-Integrated-Backend_20260923_112402`, the user explicitly asked: *"How does authentication work?"*. The model ran `get_tree`, hit a line error on `read_file`, ran `get_file_outline`, and responded:
     > *"It looks like you’re exploring the Deep‑Guard‑Backend repository. Let me know what specific information or code details you’d like to see—e.g., how authentication works... and I’ll fetch the relevant source for you."*
     The model asked the user for permission to answer the very question that had already been asked.

---

## 7. Task Completion Rates

The overall pipeline demonstrates a severe **task completion deficit**:

```text
Total Sessions (33)
├── No Calls (Aborted at start)             :  6 (18.2%)
├── Leaked Tool Call XML (Never answered)   : 12 (36.4%)
├── Empty Answer (Max tool calls hit)       : 13 (39.4%)
└── Fully Completed Textual Answers         :  2 ( 6.1%)
```

* **Effective Task Completion Rate:** **6.1%** (2 out of 33 sessions).
* **Failure to Terminate:** In 25 out of 33 sessions (75.8%), the agent exhausted its maximum tool calls (10 turns) without ever transitioning from the exploration phase to the answering phase.

---

## 8. Tool Errors and Recovery

Analysis of how the agent system responded to failures:

| Failure Type | Count | Recovery Behavior Observed |
| :--- | :--- | :--- |
| **Line Range Exceeded (>250 lines)** | 3 | **Partial Recovery:** In `112402`, the model appropriately fell back to `get_file_outline`. In `104011` and `114015`, the model failed to adjust and hit maximum turns. |
| **File Not Found** | 2 | **Good Recovery:** Model adjusted file path or abandoned dead branch without crashing. |
| **Unbounded File Read (>250 lines)** | 2 | **Good Recovery:** Provided error prompt instructed model to pass `start_line` and `end_line`; model complied on subsequent turn. |
| **Tool Namespace Error (`repo_browser`)** | 1 | **Good Recovery:** Model switched back to `search_repository` on the next turn. |
| **Out-of-Bounds Line Query** | 1 | **Good Recovery:** Adjusted target inspection window. |

The defensive feedback messages embedded in tool execution errors (`"Refusing full file read..."`, `"Safe read limit is 250 lines..."`) successfully guided models in 7 out of 9 errors.

---

## 9. Missed Information and Untapped Tool Capabilities

1. **Underutilization of Structural RIM Tools:**  
   * `get_file_outline` was only called 7 times. Models frequently read blind line ranges (`1-250`, `1-400`) rather than first fetching symbol boundaries via `get_file_outline`.
   * `query_rim` was called only 2 times, and graph traversal tools (`get_callers`, `get_callees`) only 6 times combined. Instead of using indexed relational facts, models relied almost entirely on brute-force text reading (`read_file`, 107 calls).
2. **Ignoring Jupyter Notebook Code Cells:**  
   * In `RAG_ASSIGNMENT_LEGAL`, models repeatedly failed to locate Qdrant initialization because they searched `.py` files (`search_code` with `file_pattern: '*.py'`) when all logic resided in `.ipynb` files.

---

## 10. Tool Overuse vs. Underuse Analysis

### Overused Tools
* **`read_file` (Overused):** 107 calls. Models frequently read 100-line blocks of files sequentially (Turn 1: lines 1-100, Turn 2: lines 100-250, Turn 3: lines 250-350) without using `search_code` to jump directly to relevant methods.
* **`search_repository` (Overused in tight loops):** 75 calls. Repeated broad queries with minor keyword permutations rather than inspecting matches.

### Underused Tools
* **`get_file_outline` (Severely Underused):** 7 calls. Could have prevented 100% of line range overflow errors.
* **`query_rim` & Graph Tracing (`get_callers`, `get_callees`) (Severely Underused):** 8 calls combined. Pre-computed Layer 4 facts were ignored in favor of re-parsing text.

---

## 11. Root Cause Analysis & Concrete Failure Signatures

### Issue A: Tool Call Syntax Leak (`<tool_call>` in Final Answer)
* **Concrete Example:** Session `1_Deep-Guard-Integrated-Backend_20260922_145943`
  ```xml
  <tool_call>
  <invoke name="read_file">
  <parameter name="path">app/Deep-Guard-ML-Engine/app/services/model.py</parameter>
  <parameter name="start_line">51</parameter>
  <parameter name="end_line">100</parameter>
  </invoke>
  </tool_call>
  ```
* **Cause:** The model generated Hermes-style XML tool calls at turn 10. Because turn 10 was the hard ceiling (`max_tool_calls = 10`), the QA loop stopped tool execution and treated the raw completion as the user-facing answer without parsing or executing it.

### Issue B: The "Infinite Exploration Loop" (Reaching Turn 10 with Empty Answer)
* **Concrete Example:** Log trace in `app.log` (lines 5892–5927):
  ```text
  Turn 11: tool=read_file
  LoopGuardrails: Max tool calls exceeded (11 > 10)
  Tool call limit hit: StopReason.MAX_TOOL_CALLS_EXCEEDED
  [parse_hermes] No <tool_call> block found in response
  [parse_response] Hermes parse failed, trying JSON fallback for Qwen
  No valid JSON action object found in response
  [QALoop] Completed 13 turns | 10 tool calls | StopReason.MAX_TOOL_CALLS_EXCEEDED
  [router:sse:DIAGNOSTIC:final-answer] stop_reason=MAX_TOOL_CALLS_EXCEEDED answer_len=4162
  ```
* **Cause:** When the maximum tool limit was hit, the system prompted the model for a final synthesis. The model generated 4,162 characters of answer, but the parsing pipeline checked for tool call JSON/Hermes blocks, failed to recognize it as a plain markdown response, and discarded the answer text, resulting in `response_text: ""` saved to storage and streamed to the user.

---

## 12. Actionable Recommendations

1. **Fix Final Answer Parser Fallback in `qa_protocol.py`:**
   * When `StopReason.MAX_TOOL_CALLS_EXCEEDED` is triggered and a synthesis request is sent to the LLM, the output must be parsed as a **pure markdown final answer**, bypassing tool-call extraction. This single fix will immediately rescue ~40% of failed sessions.
2. **Enforce Mandatory `get_file_outline` Before Large Reads:**
   * Modify the system prompt or agent pre-flight guardrail to require calling `get_file_outline` on any file larger than 250 lines before issuing `read_file`.
3. **Hard Clamp `read_file` Range Arguments:**
   * Instead of raising an exception when `end_line - start_line > 250`, automatically clamp `end_line = start_line + 250` and return the slice with an informational notice: `[Notice: Clamped to safe limit of 250 lines]`.
4. **Stateful De-duplication in `LoopGuardrails`:**
   * Maintain a set of `(tool_name, args_hash)` in the active QA session. Reject identical duplicate calls with an immediate feedback error: `"You already called this tool with these exact arguments in Turn X. Synthesize or inspect other files."`
5. **Support `.ipynb` Analysis in `search_code`:**
   * Update file search filters to index code cells inside Jupyter notebooks so models do not miss implementation logic in data-science repositories.

---
*Report archived in documentation repository: `docs/reports/LLM_TOOL_USAGE_ANALYSIS_REPORT.md`*
