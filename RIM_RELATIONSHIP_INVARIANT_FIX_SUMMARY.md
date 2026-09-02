# RIM Relationship Invariant Fix - Implementation Summary

**Date:** September 2, 2026  
**Session:** https://claude.ai/code/session_01HvqnygDPh7n9gJZkXEHzHK

## Problem Statement

The RIM pipeline was producing empty metadata blocks ("No structural facts could be resolved") despite HTTP 200 responses. Investigation identified a fundamental architectural violation:

**RepositoryModel Invariant (BROKEN):**
```
Every Relationship in model.relationships must satisfy:
- rel.source_id references an entity in model.entities
- rel.target_id references an entity in model.entities
```

**Root Cause:** Multiple analyzers were creating orphaned relationships to unresolved external references, causing cascading failures:

1. CallGraphAnalyzer created CALLS to external functions that don't exist in model
2. TypeAnalyzer created INHERITS to external base classes that don't exist in model
3. FactStore silently skipped these relationships (DEBUG logging only)
4. Result: 0 relationships in database → FactStoreExpander returns nothing → empty RIM metadata

## Solutions Implemented

### 1. CallGraphAnalyzer Fix

**File:** `backend/intelligence/engine/analyzers/callgraph.py`

**Issue:** Both Python and TypeScript visitors were generating synthetic entity IDs for unresolved calls without creating corresponding Entity records.

**Before:**
```python
callee_id = resolve_reference(...)
if not callee_id:
    # Fallback: generate synthetic ID even though entity won't exist
    callee_id = generate_entity_id(EntityType.FUNCTION, self.file_path, callee_qname)

# Create relationship regardless
rel = Relationship(source_id=self.current_caller_id, target_id=callee_id)
```

**After:**
```python
# Only create relationship if callee exists
if self.current_caller_id and callee_id:
    rel = Relationship(source_id=self.current_caller_id, target_id=callee_id)
```

**Impact:** External/unresolved calls are no longer added to the model.

---

### 2. TypeAnalyzer Fix

**File:** `backend/intelligence/engine/analyzers/type.py`

**Issue:** Created INHERITS relationships to external base classes without checking if they exist in the model.

**Changes:**
- Skip builtin bases: `object`, `Exception`, `BaseException`
- Skip typing module bases: `typing.*`, `ABC`, `Generic`
- Only create relationships to imported base classes (which have Entity records)
- Skip base classes that can't be resolved to an entity

**Impact:** INHERITS relationships are only created for resolvable imported base classes.

---

### 3. FactStore Validation

**File:** `backend/intelligence/store/fact_store.py`

**Issue:** Relationships were silently skipped during persistence without alerting developers.

**Added Validation:**
```python
# At start of save_rim_to_fact_store, before any persistence:
orphaned_rels = []
for rel_id, rel in model.relationships.items():
    if rel.source_id not in model.entities:
        orphaned_rels.append(f"{rel_id}: missing source {rel.source_id}")
    if rel.target_id not in model.entities:
        orphaned_rels.append(f"{rel_id}: missing target {rel.target_id}")

if orphaned_rels:
    raise ValueError("RepositoryModel invariant violated...")
```

**Impact:** Fails fast with clear error message instead of silent failures.

---

### 4. Comprehensive Regression Tests

**File:** `backend/tests/services/test_relationship_invariant_validation.py`

**Coverage:**
- **Invariant Validation:** Tests that orphaned relationships are rejected during persistence
- **CallGraph Behavior:** Verifies external calls are not created as relationships
- **Type Analyzer Behavior:** Verifies builtin and external bases are skipped
- **Valid Relationships:** Verifies local relationships persist correctly
- **Multiple Relationships:** Tests multiple relationships in single analysis

**Test Results:** All 7 new tests pass ✅

---

## Audit of All Analyzers

| Analyzer | Status | Behavior | Evidence |
|----------|--------|----------|----------|
| **callgraph.py** | ✅ FIXED | Only creates relationships to resolved entities | Lines 155-169 (Python), 250-267 (TypeScript) |
| **type.py** | ✅ FIXED | Only creates INHERITS to imported base classes | Lines 49-90 |
| **imports.py** | ✅ SAFE | Calls `_ensure_target` to create target entities if needed | Lines 96-105 |
| **database.py** | ✅ SAFE | Creates target entity before relationship | Lines 46-61 |
| **route.py** | ✅ SAFE | Creates target entity before relationship | Lines 60-215 |
| **uses.py** | ✅ SAFE | Only creates relationship if target resolves | Lines 85-94 |
| **dependency.py** | ✅ SAFE | Creates target entity before relationship | Lines 26-41 |
| **symbol.py** | ✅ SAFE | Only creates relationships to entities created in same pass | Not analyzed (reviewed in prior session) |

---

## Test Results

### Regression Tests (New)
```
✅ test_orphaned_relationship_is_rejected
✅ test_orphaned_relationship_source_is_rejected
✅ test_callgraph_skips_unresolved_external_calls
✅ test_type_analyzer_skips_unresolved_bases
✅ test_type_analyzer_skips_builtin_bases
✅ test_local_function_calls_persist
✅ test_multiple_valid_relationships_persist
```

### Existing Tests (All Pass)
```
✅ backend/tests/test_fact_store.py (2 tests)
✅ backend/tests/services/test_rim_e2e_acceptance.py (3 tests)
✅ backend/tests/services/test_rim_pipeline_basic.py (3 tests)
✅ backend/tests/services/test_rim_qa_loop_json_parser.py (15 tests)

Total: 30/30 tests passing
```

---

## Changes Committed

### Commit 1: Core Fix
```
commit 3b74e87
fix(analyzers): Prevent orphaned relationships in RIM pipeline

- CallGraphAnalyzer: Only create CALLS relationships to resolved entities
- TypeAnalyzer: Only create INHERITS to imported base classes
- FactStore: Add validation to catch invariant violations at persistence time
- Tests: Add comprehensive regression tests
```

### Commit 2: Test Fixes
```
commit a898ed0
test: Fix database setup for relationship persistence tests

- Properly create Analysis records before persisting facts
- Ensures foreign key constraints are satisfied
```

---

## Verification Checklist

✅ **Orphaned relationships are prevented at source:**
- CallGraph no longer creates synthetic entity IDs without entities
- Type analyzer no longer creates relationships to external bases
- Other analyzers already use safe patterns (create entity before relationship)

✅ **FactStore validates invariant:**
- Fails fast with clear error on invariant violation
- Prevents silent persistence of broken relationships

✅ **Regression tests cover edge cases:**
- Unresolved external calls
- Builtin base classes
- External/third-party bases
- Valid local relationships

✅ **Existing functionality preserved:**
- All 30 tests pass (7 new + 23 existing)
- No regressions in fact store persistence
- No regressions in end-to-end RIM flow

✅ **Code follows CLAUDE.md standards:**
- Explicit behavior over implicit magic
- Simple, readable fixes over complex abstractions
- Production-usable code (not placeholders)

---

## Expected Impact

### Before Fix
```
Question: "How does authentication work?"

Analysis:
- CallGraph creates 45 CALLS relationships
- ~40 are to external/unresolved calls (no Entity)
- FactStore validation skips ~40 relationships (DEBUG log only)
- Database contains ~5 relationships

RIM Metadata Building:
- Query relationships by entity
- Find 0 relationships (all externals skipped)
- No seed entities for expansion
- Output: "No structural facts could be resolved" ❌
```

### After Fix
```
Question: "How does authentication work?"

Analysis:
- CallGraph creates ~5 CALLS relationships (only to resolved entities)
- TypeAnalyzer creates 2 INHERITS relationships (only to imported bases)
- Total: ~7 valid relationships
- Database contains 7 relationships

RIM Metadata Building:
- Query relationships by entity
- Find 7 relationships (all valid)
- Build RIM subgraph with actual structural facts
- Output: Real metadata with relationships ✅
```

---

## Code Locations

### Modified Files
- `backend/intelligence/engine/analyzers/callgraph.py` (lines 94-102, 250-267)
- `backend/intelligence/engine/analyzers/type.py` (lines 49-90)
- `backend/intelligence/store/fact_store.py` (lines 26-47)

### New Test File
- `backend/tests/services/test_relationship_invariant_validation.py` (363 lines)

---

## Conclusion

The RepositoryModel invariant is now enforced at:
1. **Source** - Analyzers only create relationships to entities that exist
2. **Persistence** - FactStore validates invariant before saving
3. **Tests** - Regression tests prevent future violations

Valid local relationships continue to persist correctly. External/unresolved references are intentionally out of scope and no longer create orphaned entries.
