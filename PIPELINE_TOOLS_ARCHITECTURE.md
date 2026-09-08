# Pipeline Tools 1-5: Architecture & Purpose

## Quick Answer

**What:** 5 specialized tools for understanding code repositories  
**Where:** Different layers (internal utilities, API endpoints, orchestration)  
**Who uses them:** Both LLM (via Agent) and internal research pipeline

---

## The 5 Tools Explained

### Tool #1: Symbol Inspection
**What it does:**
- Parse source code to extract symbol metadata (functions, classes, methods)
- Get symbol locations (file path, line numbers)
- Read exact source code of symbols
- Understand code structure without parsing everything

**Example:**
```python
inspect_symbol(
    file_path="auth.py",
    symbol_name="authenticate_user"
)
# Returns: 
# {
#   "name": "authenticate_user",
#   "type": "function",
#   "file": "auth.py",
#   "lines": 15-35,
#   "docstring": "Verifies user identity",
#   "signature": "def authenticate_user(username, password):"
# }
```

**Where:** `/backend/intelligence/inspection/symbol_inspector.py` (internal utility)

---

### Tool #2: File Retrieval
**What it does:**
- Fetch file contents from the analyzed repository
- Validate file exists in the FactStore
- Return file content with line range validation
- Prevent access to files outside the repository

**Example:**
```
GET /repo/GitOnboard/files/backend/auth.py?start_line=15&end_line=35
# Returns: File content from lines 15-35
```

**Where:** `/backend/routers/repo/structure.py` (API endpoint)  
**Used by:** LLM (via agent tools)

---

### Tool #3: Graph Query
**What it does:**
- Traverse the relationship graph between code symbols
- Find who calls a function (incoming edges)
- Find what a function calls (outgoing edges)
- Discover dependencies and relationships

**Example:**
```
GET /repo/GitOnboard/graph/authenticate_user?direction=incoming
# Returns: All functions that call authenticate_user
```

**Where:** `/backend/routers/repo/graph.py` (API endpoint)  
**Used by:** LLM (via agent tools)

---

### Tool #4: Symbol Search
**What it does:**
- Search for symbols by name/pattern
- Get symbol explanations from LLM
- Find all instances of a symbol
- Provide context about what a symbol does

**Example:**
```
POST /repo/GitOnboard/symbols/explain
{
  "name": "authenticate_user",
  "file_path": "backend/auth.py"
}
# Returns: LLM-generated explanation of what the function does
```

**Where:** `/backend/routers/repo/symbols.py` (API endpoint)  
**Used by:** LLM (via agent tools)

---

### Tool #5: Context Assembly
**What it does:**
- Combine information from Tools 1-4 into a coherent context
- Select relevant files and symbols for a query
- Assemble the "briefing" that goes to the LLM
- Manage token budgets and context windows

**Example (internal process):**
```
Query: "How does login work?"
  ↓
Stage 6 (Graph Query): Find all symbols related to login
  ↓ 
Stage 7 (Context Assembly): Select best files, symbols, and explanations
  ↓
Result: Assembled context with:
  - auth.py (login handler)
  - authenticate_user() (authentication logic)
  - database connections (data access)
  ↓
Send to LLM for analysis
```

**Where:** `/backend/intelligence/engine/orchestration/stage7_context_assembly.py` (pipeline stage)  
**Used by:** Internal research pipeline

---

## Why Different Paths?

```
┌─────────────────────────────────────────────────────────────────┐
│                  REPOSITORY INTELLIGENCE SYSTEM                 │
└─────────────────────────────────────────────────────────────────┘

        LLM Layer (What users ask questions to)
            ↓
    ┌───────────────────────────────┐
    │   Agent Tools Wrapper         │
    │   (Converts LLM requests      │
    │    to tool calls)             │
    └───────────────────────────────┘
            ↓
  ┌─────────────────────────────────────────┐
  │        API Endpoints (routers)          │
  │  (/backend/routers/repo/)               │
  │  - structure.py (Tool #2: File)         │ ← Used by LLM via agent
  │  - graph.py (Tool #3: Graph)            │
  │  - symbols.py (Tool #4: Search)         │
  └─────────────────────────────────────────┘
            ↓
  ┌─────────────────────────────────────────┐
  │    Database & Fact Store                │
  │  (PostgreSQL + Azure Blob Storage)      │
  │  - FactSymbol, FactFile, FactRelation   │
  └─────────────────────────────────────────┘

        Internal Research Pipeline
            ↓
  ┌─────────────────────────────────────────┐
  │  Orchestration Pipeline                 │
  │  (/backend/intelligence/engine/)        │
  │  Stage 1-5: Extract & parse code        │
  │  Stage 6: Graph navigation (uses #3)    │ ← Uses Tool #3
  │  Stage 7: Context assembly (Tool #5)    │ ← Uses Tool #3 output
  │  Stage 8: Grounding (uses Tool #2)      │ ← Uses Tool #2
  └─────────────────────────────────────────┘

        Internal Utilities
            ↓
  ┌─────────────────────────────────────────┐
  │  Intelligence Module                    │
  │  (/backend/intelligence/inspection/)    │
  │  - symbol_inspector.py (Tool #1)        │ ← Used by pipeline stages
  └─────────────────────────────────────────┘
```

---

## Who Uses What?

### LLM Uses (via Agent Tools):
```
User Question
    ↓
LLM (Claude)
    ↓
Agent Tool Invocation
    ↓ Calls via HTTP
API Endpoints:
  - Tool #2 (File Retrieval) - GET /files/...
  - Tool #3 (Graph Query) - GET /graph/...
  - Tool #4 (Symbol Search) - POST /symbols/...
    ↓ Queries
Fact Store Database
    ↓
Results back to LLM
```

### Internal Pipeline Uses:
```
Repository Import
    ↓
Stage 1-5: Extract symbols, parse ASTs
    ↓
Stage 6: Graph Navigation
    ↓ Uses
Tool #3 (Graph Query) API internally
    ↓
Find related symbols
    ↓
Stage 7: Context Assembly (Tool #5)
    ↓ Uses
Tool #2 (File Retrieval)
Tool #3 (Graph Query)
Tool #1 (Symbol Inspection)
    ↓
Assemble context briefing
    ↓
Stage 8: Grounding
    ↓ Uses
Tool #2 (File Retrieval)
    ↓
Ready for LLM
```

---

## Location Rationale

### Why Tools #2, #3, #4 are in `/backend/routers/repo/`?
- They are **HTTP API endpoints**
- Exposed for external callers (LLM, agents, frontend)
- Need request/response handling
- Need authentication/authorization
- Need explicit error codes (400/404/500)

### Why Tool #1 is in `/backend/intelligence/inspection/`?
- It's an **internal utility module**
- Used by pipeline stages, not directly by LLM
- No HTTP exposure needed
- Pure Python functions

### Why Tool #5 is in `/backend/intelligence/engine/orchestration/`?
- It's a **pipeline orchestration stage**
- Part of the analysis workflow
- Doesn't need to be an API endpoint
- Used only internally during analysis

---

## Data Flow: End-to-End Example

### Scenario: User asks "How does authentication work?"

```
1. USER ASKS QUESTION
   "How does authentication work?"
   
2. LLM THINKS & DECIDES TO USE TOOLS
   "I need to understand the auth system"
   
3. LLM CALLS AGENT TOOLS (via HTTP)
   → Tool #3 (Graph Query): "Find all symbols related to auth"
   → Tool #2 (File Retrieval): "Get auth.py file"
   → Tool #4 (Symbol Search): "Explain authenticate_user()"
   
4. API ENDPOINTS PROCESS REQUESTS
   ✓ /repo/GitOnboard/graph/auth?direction=both
   ✓ /repo/GitOnboard/files/backend/auth.py
   ✓ /repo/GitOnboard/symbols/explain?name=authenticate_user
   
5. RESULTS RETURNED TO LLM
   ← Calling functions (graph)
   ← File content (auth.py)
   ← Function explanation (what it does)
   
6. LLM GENERATES ANSWER
   "Authentication in GitOnboard works by..."
```

### Behind the Scenes: Repository Analysis

```
1. REPOSITORY IMPORT
   User: "Analyze https://github.com/user/repo"
   
2. STAGE 1-5 (Internal)
   Extract all symbols, parse ASTs
   Build internal representations
   
3. STAGE 6 (Uses Tool #3)
   Graph Navigation stage calls:
   → Tool #3 (Graph Query) internally to traverse relationships
   → Finds all connected symbols
   
4. STAGE 7 (Tool #5: Context Assembly)
   Assembles context by using:
   → Tool #3 results (which symbols to include)
   → Tool #2 (get file contents)
   → Tool #1 (get symbol metadata)
   
5. STAGE 8 (Grounding)
   Uses Tool #2 to retrieve source code
   Validates answers against actual code
   
6. RESULT: Knowledge Base Ready
   ✓ FactStore populated
   ✓ Indexes built
   ✓ Ready for LLM queries
```

---

## Summary

| Tool | Purpose | Location Type | HTTP? | Used By | When |
|------|---------|---------------|-------|---------|------|
| #1 | Extract symbol metadata | Internal utility | No | Pipeline stages | During analysis |
| #2 | Retrieve file contents | API endpoint | Yes | LLM + Pipeline | Query time + Analysis |
| #3 | Traverse relationships | API endpoint | Yes | LLM + Pipeline | Query time + Analysis |
| #4 | Search & explain symbols | API endpoint | Yes | LLM | Query time |
| #5 | Assemble context | Pipeline stage | No | Internal | During analysis |

---

## Key Insights

1. **Different locations = Different purposes**
   - API endpoints (2,3,4) for external use
   - Internal utilities (1) for pipeline
   - Pipeline stage (5) for orchestration

2. **Tools are layered**
   - LLM sees Tools 2, 3, 4 (via HTTP)
   - Pipeline sees Tools 1, 2, 3 (via direct function calls)
   - Tool 5 coordinates everything

3. **Reusable across contexts**
   - Same Tool #3 used by both:
     - LLM queries ("find who calls this")
     - Pipeline stages (graph navigation)
   - Same Tool #2 used by both:
     - LLM queries ("show me this file")
     - Pipeline stages (context assembly)

4. **Isolation & Independence**
   - Each tool can work independently
   - API endpoints don't require database
   - Internal utilities don't require HTTP
   - Clean separation of concerns
