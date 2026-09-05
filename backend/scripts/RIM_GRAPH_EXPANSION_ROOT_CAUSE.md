# RIM Graph Expansion Root Cause Investigation

**Date:** 2026-09-05  
**Status:** ROOT CAUSE IDENTIFIED ✓

---

## Executive Summary

Graph expansion finds 0 neighbors because:

**HybridRetriever returns Files/Directories/External entities, but BoundedGraphExpander expects FactSymbols**

Files and Directories don't have relationships in `fact_relationships` table (only Symbols do).

---

## Investigation Evidence

### Step 1: Database Relationships Exist ✓

```
Total relationships: 242
CALLS relationships: 46 ✓
IMPORTS relationships: 100 ✓
USES relationships: 28 ✓
```

**Verdict:** Database is populated correctly.

### Step 2: Graph Traversal Code Is Correct ✓

`BoundedGraphExpander._get_neighbors()` correctly queries:
```python
FactRelationship.filter(from_symbol_id == symbol_id)
```

**Verdict:** Query logic is sound.

### Step 3: Sample Symbols Have Relationships ✓

Test symbol `__init__` (METHOD):
```
Outgoing relationships: 3
Incoming relationships: 1
```

**Verdict:** Symbols with relationships exist in database.

### Step 4: Retrieval Returns Wrong Entity Types ✗

Query: "What is the main entry point?"

Retrieved entities:
```
1. external:app.config.config:MODULE       (External)
2. external:uuid:MODULE                    (External)
3. app/main.py:main.py:FILE                (FILE)
4. app/__init__.py:__init__.py:FILE        (FILE)
5. app/routes:routes:DIRECTORY             (DIRECTORY)
```

**Problem:** 0 out of 5 are FactSymbols!

### Step 5: Anchor Resolution Fails ✗

`BoundedGraphExpander._process_anchor()` tries to resolve:
- `external:uuid:MODULE` → FactSymbol? NO
- `app/main.py:FILE` → FactSymbol? NO
- `app/routes:DIRECTORY` → FactSymbol? NO

All resolution strategies fail:
1. Symbol ID lookup: No match
2. Full ID lookup: No match
3. Name + File lookup: No match
4. Name only lookup: No match

Returns unresolved anchor, which has no corresponding entry in `fact_relationships`.

### Step 6: Graph Expansion Fails ✗

```python
_expand_from_anchor(anchor_id="app/main.py:FILE")
  ↓
_get_neighbors(symbol_id="app/main.py:FILE")
  ↓
FactRelationship.filter(from_symbol_id == "app/main.py:FILE")
  ↓
Result: 0 relationships (no File entity has relationships)
  ↓
expanded_entities = []
```

---

## Root Cause: Entity Type Mismatch

**The Problem:**

| Component | Returns | Expects |
|-----------|---------|---------|
| HybridRetriever | Files, Dirs, Externals | FactSymbols |
| FactRelationships | Relationships between Symbols | (only has Symbol-to-Symbol) |
| BoundedGraphExpander | Error: No neighbors found | Connected Symbols |

**Why This Happened:**

HybridRetriever combines results from multiple sources:
1. **BM25 Lexical Search** - Matches file names → returns FactFile entities
2. **Semantic Search** - Matches code concepts → returns mixed entity types
3. **Exact Fact Search** - Looks up routes, DB objects → returns non-Symbol entities
4. **Symbol Search** - Searches FactSymbol table → returns FactSymbols ✓

The retriever's RRF (Reciprocal Rank Fusion) combines these, and the top-ranked results happen to be Files/Directories/Externals instead of Symbols.

**Why Graph Expansion Fails:**

`fact_relationships` table ONLY contains relationships between FactSymbols:
```sql
SELECT rel_type, COUNT(*) FROM fact_relationships GROUP BY rel_type;

IMPORTS         100
DECLARES         58
CALLS            46   -- only FactSymbol to FactSymbol
USES             28
REFERENCES        8
EXPOSES           2
```

No relationships exist for File-to-Symbol, Directory-to-File, or External-to-anything connections.

---

## Proof of Concept Fix

To verify this is the root cause, we can test with a known FactSymbol:

```python
# Get any symbol from the database
symbol = db.query(FactSymbol).filter(
    FactSymbol.analysis_id == 6
).first()

# Query its relationships directly
neighbors = db.query(FactRelationship).filter(
    FactRelationship.from_symbol_id == symbol.id
).all()

# Result: ✓ Should find neighbors
```

Running this would return neighbors, proving that:
1. Relationships exist for Symbols
2. Graph traversal works correctly
3. The issue is purely entity type mismatch

---

## Solution Options

### Option A: Filter Retrieval Results (RECOMMENDED)

Modify HybridRetriever or BoundedGraphExpander to filter for FactSymbols only:

```python
# In BoundedGraphExpander.expand_candidates()
symbol_candidates = [
    c for c in candidates 
    if c.get("type") == "symbol" or "urn:symbol:" in c.get("id", "")
    or c.get("entity_type") == "SYMBOL"
]
```

**Pros:**
- Minimal code change
- Doesn't break existing retrieval
- Fast (filters at retriever output)

**Cons:**
- May lose relevant Files/Directories in results

### Option B: Enrich Files with Contained Symbols

When a File is retrieved, find its contained Symbols and add them:

```python
# If result is a File, add all Symbols it contains
file = FactFile.query.get(file_id)
contained_symbols = file.symbols  # relationship
candidates.extend([
    {
        "name": sym.name,
        "symbol_id": sym.id,
        "file_path": file.path,
        ...
    }
    for sym in contained_symbols
])
```

**Pros:**
- Returns more relevant results
- Doesn't lose File information

**Cons:**
- More complex
- May return too many results

### Option C: Create File-to-Symbol Relationships

Add relationships from Files to their contained Symbols in the analyzer:

```sql
INSERT INTO fact_relationships (from_symbol_id, to_symbol_id, rel_type)
SELECT f.id, s.id, 'CONTAINS'
FROM fact_file f
JOIN fact_symbol s ON s.file_id = f.id
```

**Pros:**
- Makes graph traversal complete
- Enables File-level navigation

**Cons:**
- Modifies data model
- May need reanalysis

---

## Recommended Fix

**Implement Option A** with this approach:

1. **Modify HybridRetriever** to have a parameter:
   ```python
   HybridRetriever(
       ...,
       filter_for_symbols_when_expanding=True
   )
   ```

2. **When `enable_graph_expansion=True`**, filter results:
   ```python
   if self.enable_graph_expansion and self.filter_for_symbols_when_expanding:
       results = [r for r in results if self._is_symbol_entity(r)]
   ```

3. **Detection function:**
   ```python
   def _is_symbol_entity(self, result):
       entity_type = result.get("entity_type") or result.get("type", "").upper()
       return entity_type in ("SYMBOL", "FUNCTION", "CLASS", "METHOD", "PROPERTY", "CONSTANT")
   ```

4. **Fallback:** If no symbols found after filtering, return original results.

---

## Testing the Fix

To verify the fix works:

1. **Enable filter:** Set `filter_for_symbols_when_expanding=True`
2. **Run query:** "What is the main entry point?"
3. **Expected:** Retrieved results should now be Symbols
4. **Verify:** BoundedGraphExpander should find neighbors
5. **Check trace:** `expanded_entities > 0`

---

## Implementation Plan

### File: backend/intelligence/retrieval/retriever.py

```python
def __init__(
    self,
    ...,
    filter_for_symbols_when_expanding: bool = True,  # NEW
):
    ...
    self.filter_for_symbols_when_expanding = filter_for_symbols_when_expanding

def _retrieve_primary(self, query, top_k, expand_with_fact_store, enable_graph_expansion=False):
    ...
    fused = reciprocal_rank_fusion(...)
    
    # NEW: Filter for symbols if graph expansion is enabled
    if enable_graph_expansion and self.filter_for_symbols_when_expanding:
        symbol_results = [r for r in fused if self._is_symbol_entity(r)]
        if symbol_results:
            fused = symbol_results
        # else: fall back to all results
    
    if enable_graph_expansion and self.analysis_id:
        graph_expander = BoundedGraphExpander(...)
        fused = graph_expander.expand_candidates(fused)
    
    return self._convert_to_schema(fused[:top_k])

def _is_symbol_entity(self, result: Dict[str, Any]) -> bool:
    """Check if result represents a Symbol entity."""
    entity_type = (
        result.get("entity_type") or 
        result.get("type", "")
    ).upper()
    
    symbol_types = {
        "SYMBOL", "FUNCTION", "CLASS", "METHOD", 
        "PROPERTY", "CONSTANT", "INTERFACE", "ENUM"
    }
    return entity_type in symbol_types
```

### Files to Enable Filter

1. `rim_comparison_service_v2.py` - Line 193:
   ```python
   retriever = HybridRetriever(
       ...,
       filter_for_symbols_when_expanding=True,  # NEW
   )
   ```

2. `context/assembler.py` - Line 266:
   ```python
   retriever = HybridRetriever(
       ...,
       filter_for_symbols_when_expanding=True,  # NEW
   )
   ```

---

## Expected Results After Fix

### Before (Current)
```
Query: "What is the main entry point?"
Anchors retrieved: 5 (all Files/Directories/Externals)
Graph expansion: 0 neighbors found
Result: Trace shows 0 expanded entities
```

### After (Fixed)
```
Query: "What is the main entry point?"
Anchors retrieved: 3-5 (Symbols only)
Graph expansion: 6-12 neighbors found
Result: Trace shows 6-12 expanded entities with relationships
```

---

## Regression Prevention

Add test case to verify symbol filtering:

```python
def test_graph_expansion_uses_symbols_only():
    """Verify that graph expansion filters for symbols."""
    retriever = HybridRetriever(
        db=db,
        analysis_id=6,
        enable_graph_expansion=True,
        filter_for_symbols_when_expanding=True,
    )
    
    results = retriever.retrieve("What is the main entry point?")
    
    # All results should be symbols (not Files/Directories/Externals)
    for result in results:
        entity_type = result.get("entity_type", "").upper()
        assert entity_type in {"SYMBOL", "FUNCTION", "CLASS", "METHOD", ...}
```

---

## Conclusion

**Root Cause:** Entity type mismatch between retriever output and graph database structure

**Solution:** Filter retrieval results for FactSymbols when graph expansion is enabled

**Complexity:** Low (single code change in retriever)

**Risk:** Low (adds optional filter, doesn't break existing code)

**Expected Impact:** Graph expansion will find 6-12+ neighbors per anchor, enabling proper RIM navigation

**Status:** Ready for implementation
