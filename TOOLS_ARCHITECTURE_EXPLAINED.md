# Tools Architecture: Pipeline vs Agent Tools

## The Two Different Tool Systems

```
┌─────────────────────────────────────────────────────────────────────┐
│                     REPOSITORY INTELLIGENCE SYSTEM                  │
└─────────────────────────────────────────────────────────────────────┘

                    ↓↓↓ TIME: IMPORT PHASE ↓↓↓

┌──────────────────────────────────────────────────────────────────────┐
│           PIPELINE TOOLS (Stages 1-5+) - RUN ONCE                    │
│        Extract knowledge from repository into knowledge base         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Tool 1: Symbol Inspection                                           │
│  ├─ What: Parse code and extract symbols (functions, classes, etc) │
│  ├─ When: During import, runs ONCE                                 │
│  ├─ Input: Source code files on disk                               │
│  └─ Output: FactSymbol records in PostgreSQL                       │
│                                                                       │
│  Tool 2: File Retrieval                                              │
│  ├─ What: Index and store file contents in blob storage            │
│  ├─ When: During import, runs ONCE                                 │
│  ├─ Input: All repository files                                     │
│  └─ Output: Snapshots in Azure Blob Storage                         │
│                                                                       │
│  Tool 3: Graph Query                                                 │
│  ├─ What: Build relationship graph (calls, references, etc)        │
│  ├─ When: During import, runs ONCE                                 │
│  ├─ Input: Parsed symbols and ASTs                                  │
│  └─ Output: FactRelationship records in PostgreSQL                  │
│                                                                       │
│  Tool 4: Symbol Search                                               │
│  ├─ What: Build BM25 lexical index of all symbols                  │
│  ├─ When: During import, runs ONCE                                 │
│  ├─ Input: All FactSymbol records                                   │
│  └─ Output: BM25 index in AnalysisArtifact table                    │
│                                                                       │
│  Tool 5: Context Assembly                                            │
│  ├─ What: Assemble multi-layer context for LLM queries             │
│  ├─ When: During import, runs ONCE                                 │
│  ├─ Input: Symbols, relationships, files                            │
│  └─ Output: Semantic index (Chroma) in AnalysisArtifact table       │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘

                  ✅ RESULT: Knowledge Base Built

                        ↓↓↓ TIME: QUERY PHASE ↓↓↓

┌──────────────────────────────────────────────────────────────────────┐
│         AGENT TOOLS (10 tools) - RUN MANY TIMES                      │
│    Query the knowledge base to answer LLM questions                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Agent Tool 1: search_code                                           │
│  ├─ What: Search repository files/code for patterns                │
│  ├─ When: During query, called by LLM as needed                    │
│  ├─ Input: Natural language query → "search for auth"              │
│  └─ Output: List of matching code snippets                          │
│                                                                       │
│  Agent Tool 2: search_symbols                                        │
│  ├─ What: Find symbols by name/pattern                             │
│  ├─ When: During query, called by LLM as needed                    │
│  ├─ Input: Natural language query → "find auth functions"          │
│  └─ Output: List of matching symbols                                │
│                                                                       │
│  Agent Tool 3: get_symbol                                            │
│  ├─ What: Look up definition of a specific symbol                  │
│  ├─ When: During query, called by LLM as needed                    │
│  ├─ Input: Symbol name → "authenticate"                            │
│  └─ Output: Symbol details (type, file, location)                   │
│                                                                       │
│  Agent Tool 4: get_callers                                           │
│  ├─ What: Find all functions that call a specific function         │
│  ├─ When: During query, called by LLM as needed                    │
│  ├─ Input: Function name → "save"                                   │
│  └─ Output: List of caller functions                                │
│                                                                       │
│  Agent Tool 5: get_callees                                           │
│  ├─ What: Find all functions called by a specific function         │
│  ├─ When: During query, called by LLM as needed                    │
│  ├─ Input: Function name → "process"                               │
│  └─ Output: List of called functions                                │
│                                                                       │
│  [Remaining Agent Tools: 6-10]                                      │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Key Differences

| Aspect | Pipeline Tools (1-5) | Agent Tools (10) |
|--------|---------------------|-----------------|
| **Purpose** | Extract & index knowledge | Query the knowledge base |
| **When** | During repository import (once) | During user queries (many times) |
| **Input** | Source code files on disk | Natural language queries |
| **Output** | Database records + indexes | Structured results for LLM |
| **Frequency** | 1x per analysis | 10-100x per user session |
| **Duration** | Minutes (full repository) | Milliseconds (single query) |
| **Data** | Reads from filesystem | Reads from PostgreSQL + blob storage |
| **Storage** | Writes to PostgreSQL + Azure | No writes (read-only) |
| **User Awareness** | Invisible (background) | User-facing (LLM visible) |

---

## Data Flow Example

### Pipeline Tools (Import Phase)

```
User clicks: "Import https://github.com/user/repo"
                    ↓
           Tool 1: Symbol Inspection
           ├─ Parse all .py files
           ├─ Extract: functions, classes, methods
           └─ Save: 5,000 FactSymbol rows
                    ↓
           Tool 2: File Retrieval
           ├─ Read all files (source, config, tests)
           ├─ Compress and upload to Azure
           └─ Save: 84 file snapshots
                    ↓
           Tool 3: Graph Query
           ├─ Analyze AST for relationships
           ├─ Build: who-calls-who, who-references-who
           └─ Save: 12,000 FactRelationship rows
                    ↓
           Tool 4: Symbol Search
           ├─ Tokenize all 5,000 symbols
           ├─ Build: BM25 inverted index
           └─ Save: 1 BM25 artifact (indexed)
                    ↓
           Tool 5: Context Assembly
           ├─ Run embedding model on 5,000 symbols
           ├─ Build: Chroma semantic vector index
           └─ Save: 1 Semantic artifact (indexed)
                    ↓
        ✅ Analysis Complete - Knowledge Base Ready
```

### Agent Tools (Query Phase)

```
User asks LLM: "Who handles authentication in this repo?"
                    ↓
        LLM decides to use Agent Tool 4: get_callers
                    ↓
        Query PostgreSQL:
        SELECT * FROM FactSymbol WHERE name LIKE '%authenticate%'
                    ↓
        Agent Tool returns:
        [{name: "authenticate_user", file: "auth.py", type: "function"}]
                    ↓
        LLM uses result in response:
        "The authenticate_user function in auth.py handles authentication"
```

---

## Why Both Systems?

### Pipeline Tools (Stages 1-5)
**Problem they solve:** How do we extract meaningful knowledge from source code?
- Extract symbols from millions of lines of code
- Build relationships between symbols
- Create searchable indexes
- Build embeddings for semantic search

**Example:** Without Symbol Inspection (Tool 1), we'd have no FactSymbol records to query

---

### Agent Tools (10 tools)
**Problem they solve:** How does the LLM interact with the knowledge we extracted?
- User asks a question in natural language
- LLM needs to search the knowledge base
- LLM needs to traverse relationships
- LLM needs to read specific files

**Example:** Without Agent Tool 4 (get_callers), the LLM couldn't answer "who calls save()?"

---

## Current Status

### Pipeline Tools (Stages 1-5)
❓ **Status:** Need clarification on which files implement these

The user mentioned:
1. Symbol Inspection
2. File Retrieval
3. Graph Query
4. Symbol Search
5. Context Assembly

But I need to verify:
- Are these in `/backend/intelligence/stages/` ?
- Are these in `/backend/intelligence/engine/` ?
- Do they have different names in the codebase?

### Agent Tools
✅ **Status:** ALL 5 TESTED & VERIFIED
- search_code: ✅ PASS
- search_symbols: ✅ PASS
- get_symbol: ✅ PASS
- get_callers: ✅ PASS
- get_callees: ✅ PASS

---

## Next Steps

**For Pipeline Tools (1-5):**
- Identify exact file locations
- Write integration tests
- Verify they work end-to-end during import

**For Agent Tools (6-10):**
- Create tests for remaining tools
- Verify tool chaining scenarios
- Test on real user queries

---

## Summary

- **Pipeline Tools** = The extraction + indexing machinery (runs during import)
- **Agent Tools** = The query interface for the LLM (runs during user questions)

Both are essential but serve different purposes in different phases of the system.
