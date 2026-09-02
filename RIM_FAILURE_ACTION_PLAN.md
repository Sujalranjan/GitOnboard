# RIM Pipeline Failure - Root Causes & Action Plan

**Status:** INVESTIGATING - Not Production Ready  
**Evidence Base:** Actual code review + production logs

---

## Root Causes Identified

### Problem 1: Retriever Returns Code Snippets, Not Entity Names

**Location:** `backend/services/rim_metadata.py:112`
```python
candidates = retriever.retrieve(question, top_k=5, expand_with_fact_store=False)
```

**What's happening:**
- Retriever returns RetrieverResult objects with fields: id, entity_name, entity_type, file_path, etc.
- BUT in production logs, retriever.retrieve("How does auth work?") returned code snippets from:
  - server.js (comment)
  - middleware/auth.js (error log line)
  - ARCHITECTURE.md (diagram)

**Evidence from logs (94f887ba):**
```
Search result 1: "// AUTH (no auth middleware here)" from server.js:44
Search result 2: "console.error("Auth middleware error:", err);" from middleware/auth.js:246
Search result 3: "A[Client] -->|Request + Token| B(Auth Middleware)" from ARCHITECTURE.md:117
```

**Problem:** These are code snippets, not entity definitions. When RIM tries to extract entity_name:
```python
entity_name = cand.entity_name  # Likely empty or wrong
```

The entity_name would be empty, resulting in seed resolution failure.

---

### Problem 2: Seed Resolution Requires Perfect Entity Name Match

**Location:** `backend/services/rim_metadata.py:137`
```python
target = resolver.resolve(entity_name)
```

**Implementation:**
```python
def resolve(self, entity_name: str) -> Optional[Any]:
    # Try FactSymbol with case-insensitive match
    symbol = self.db.query(FactSymbol).filter(
        FactSymbol.analysis_id == self.analysis_id,
        FactSymbol.name.ilike(entity_name),
    ).first()
```

**Problem:** 
- Requires `ilike` match on entity name
- If entity_name is empty or misspelled, resolve returns None
- Zero seeds → "No structural facts" message

**Evidence from logs:**
- Only 1 seed was resolved (authMiddleware)
- Should have found: authenticateToken, createSession, verifyIdentity, checkPermissions, hashToken

---

### Problem 3: Retriever Doesn't Extract Entity Names from Code Snippets

**Root Cause:** When HybridRetriever returns results for natural-language queries about code concepts, it returns best-matching CODE LOCATIONS, not entity DEFINITIONS.

**Question:** "How does auth work?"  
**Code snippet results:** Comments, error messages, diagrams  
**Expected entity results:** authMiddleware, authenticateToken, createSession, verifyIdentity

**Missing step:** Retriever needs to infer entity names from code locations, not just return code snippets.

---

### Problem 4: Graph Expansion is Shallow (1 Hop Only)

**Location:** `backend/services/rim_metadata.py:381-447`

**Current behavior:**
```python
for seed_name, target, _ in seeds:  # Only ONE seed (usually)
    for query_class in query_classes_to_traverse:
        result = traverser.traverse(intent, target)
        for entity in result.related_entities[:max_related_per_seed]:  # ONE hop
            # Add entity to facts
```

**Problem:**
- Depth limit of 1 hop
- If seed has weak connections (like hashToken), traversal terminates
- No recursive expansion to find distant but relevant entities

**Example failure from logs:**
```
Seed: authMiddleware
↓ (CALLS_FORWARD)
Destination: hashToken
↓ (CALLS_FORWARD) 
Result: NOTHING (dead end)
```

Should have done:
```
Seed: authMiddleware
↓ (CALLS_REVERSE)
Found: request handlers, routes
↓ Expand those
→ Find createSession, verifyIdentity, etc.
```

---

### Problem 5: Entity Name Extraction Fails for Real Repository Data

**Location:** `backend/services/rim_metadata.py:359-362`

```python
entity_name = ""
if hasattr(cand, "entity_name"):
    entity_name = cand.entity_name
elif isinstance(cand, dict):
    entity_name = cand.get("entity_name") or cand.get("name") or cand.get("match_name") or ""
```

**Problem:**
When retriever returns code snippet results, none of these fields are populated:
- cand.entity_name → empty
- cand.name → empty (or is "authMiddleware" when lucky)
- cand.match_name → empty

**Missing:** Code to extract entity names from file paths + code context

Example:
```python
# Code snippet: "console.error("Auth middleware error:", err);"
# Location: middleware/auth.js:246
# Should infer: Entity name = "authMiddleware"
# Currently: Returns empty → Seed resolution fails
```

---

## Why This Escaped Testing

### Synthetic Tests ✗
- Hand-wired entity names
- Perfect FactSymbol definitions
- No entity name extraction needed

### Unit Tests ✗
- Mocked retriever
- Returned perfect RetrieverResult objects
- No code snippet parsing

### Real Production ✗
- Retriever returns code snippets
- Entity names missing
- Seed resolution fails
- Graph expansion stops

---

## Action Items

### IMMEDIATE (Before ANY deployment)

**1. Fix Retriever Entity Name Extraction**
- [ ] Investigate what HybridRetriever.retrieve() actually returns for "How does auth work?"
- [ ] Verify it's code snippets vs. entity definitions
- [ ] Add entity name inference from code location + context
- [ ] Test with real repository data

**2. Expand Seed Set**
- [ ] Don't rely on single seed (authMiddleware)
- [ ] Extract ALL high-confidence entities from retrieval results
- [ ] Use top_k=5 instead of max_seed_entities=1
- [ ] Test with multiple seeds

**3. Deepen Graph Traversal**
- [ ] Implement recursive traversal instead of 1-hop
- [ ] Traverse bidirectionally (both callers AND callees)
- [ ] Add depth limit (e.g., 3-4 levels) to prevent explosion
- [ ] Implement entity deduplication

**4. Fix Seed Resolution**
- [ ] Add logging for every resolution attempt
- [ ] Show what entity names are being resolved
- [ ] Show which resolve to FactSymbol vs. None
- [ ] Add fallback: if resolve fails, search FactStore directly

**5. Instrumentation**
- [ ] Log candidate count before seed extraction
- [ ] Log seed count after resolution
- [ ] Log graph traversal depth and entity count
- [ ] Log final fact line count
- [ ] Output before/after metrics

### VERIFICATION (After fixes)

**Real End-to-End Test:**
```
Query: "How does login feature work?"
Expected: 10+ entities, 15+ relationships
Actual: [TBD - run after fixes]

Baseline comparison:
Baseline entities found: 10+
RIM entities found: [TBD]
Baseline relationships: 15+
RIM relationships: [TBD]
```

---

## Code Changes Needed

### Change 1: Entity Name Extraction from Code Snippets
**File:** `backend/services/rim_metadata.py`
**Method:** Add function to infer entity name from code location

```python
def infer_entity_name_from_location(file_path: str, line_content: str, code_context: str) -> Optional[str]:
    """Infer entity name from code location and context.
    
    Example:
    file_path: "middleware/auth.js"
    line_content: "function authMiddleware(...)"
    → Returns: "authMiddleware"
    """
    # Parse file, function name, or class name from context
    # This is code-specific logic
```

### Change 2: Multi-Seed Extraction
**File:** `backend/services/rim_metadata.py`
**Location:** Lines 354-375 (seed extraction)

```python
# Before: 
seeds = []
for cand in candidates[:max_seed_entities]:  # Only 3
    # Try to resolve

# After:
seeds = []
extracted_names = []
for cand in candidates:  # ALL candidates
    entity_name = extract_entity_name(cand)
    if entity_name and entity_name not in extracted_names:
        extracted_names.append(entity_name)
        target = resolver.resolve(entity_name)
        if target:
            seeds.append((entity_name, target, cand))
```

### Change 3: Recursive Graph Traversal
**File:** `backend/services/rim_metadata.py` or new file `backend/intelligence/rim/graph_expansion.py`

```python
def expand_graph_recursively(seed, max_depth=3):
    """Recursively expand graph from seed."""
    visited = set()
    frontier = [(seed, 0)]  # (entity, depth)
    
    while frontier and len(visited) < 50:  # Cap total entities
        entity, depth = frontier.pop(0)
        if entity.id in visited:
            continue
        visited.add(entity.id)
        
        if depth >= max_depth:
            continue
            
        # Traverse both directions
        for direction in [FORWARD, REVERSE]:
            related = traverser.traverse(..., direction=direction)
            for rel_entity in related:
                if rel_entity.id not in visited:
                    frontier.append((rel_entity, depth + 1))
```

---

## Current State vs. Expected

### Current (Broken)
```
Query: "How does auth work?"
↓
HybridRetriever.retrieve()
→ [code snippet 1, code snippet 2, code snippet 3]
↓
Seed Extraction
→ entity_name = "" (empty)
↓
Seed Resolution
→ No matches
↓
Result: "No structural facts"
```

### Expected (After Fixes)
```
Query: "How does auth work?"
↓
HybridRetriever.retrieve()
→ [code snippet with authMiddleware, ...]
↓
Entity Name Inference
→ ["authMiddleware", "authenticateToken", ...]
↓
Seed Extraction & Resolution
→ [FactSymbol(authMiddleware), FactSymbol(authenticateToken), ...]
↓
Recursive Graph Expansion
→ 10+ entities, 15+ relationships
↓
Metadata Construction
→ Complete RIM_METADATA with structural facts
↓
LLM Context
→ Rich repository knowledge
↓
Result: Grounded answer
```

---

## Non-Negotiable Requirement

**The acceptance test MUST use real repository data and real RIM queries.**

Test script must:
1. Load actual Deep-Guard-Backend analysis
2. Run "How does login feature work?"
3. Verify:
   - Seed entities: authMiddleware, authenticateToken, createSession, etc.
   - Relationships found: 10+
   - Metadata facts: non-empty
   - LLM context: incorporates RIM facts

**Only THEN can we declare the system production-ready.**

---

**Status: WAITING FOR IMPLEMENTATION**

Do not proceed with semantic retrieval enhancements or synthetic tests until this pipeline is fixed on real data.
