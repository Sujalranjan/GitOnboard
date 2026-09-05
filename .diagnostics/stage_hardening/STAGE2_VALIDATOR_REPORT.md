# Stage 2: Ground-Truth Validator

## Summary

Successfully completed **Stage 2: Ground-Truth Validator** for the Multi-Agent Investigation Framework. The validator independently inspects the RIM (Repository Intelligence Model) to establish whether investigation claims correspond to actual repository reality.

**Key Achievement**: No LLM involved. Repository is the sole authority.

## Files Changed

| File | Status | Purpose |
|------|--------|---------|
| `backend/investigation/ground_truth.py` | Created | GroundTruthValidator, VerificationStatus, GroundTruthResult |
| `backend/tests/unit/test_ground_truth_validator.py` | Created | 24 comprehensive adversarial tests |
| `backend/investigation/__init__.py` | Modified | Export validator components |

## Ground-Truth Architecture

```
Investigation Claim
    ↓
GroundTruthValidator
    ↓
Query RIM (Repository Intelligence Model)
    ├─ QueryLayer.find_function(name)
    ├─ QueryLayer.get_class(name)
    ├─ QueryLayer.get_file(path)
    ├─ Query Entity types, locations, metadata
    └─ Query Capabilities
    ↓
Repository-Grounded Evidence
    ├─ Entity found → DIRECT evidence with location
    ├─ Entity not found + coverage sufficient → VERIFIED_ABSENT
    └─ Entity not found + insufficient coverage → UNRESOLVED
    ↓
GroundTruthResult (VERIFIED_PRESENT | VERIFIED_ABSENT | UNRESOLVED)
    ↓
Evidence object (confidence 0.9-1.0, EvidenceType.DIRECT)
    ↓
Finding.ground_truth_evidence
```

## Evidence Integrity

The validator prevents:

| Attack Vector | Prevention | Mechanism |
|---|---|---|
| Fake evidence paths | ❌ Blocked | Must inspect actual Entity objects |
| Agent assertions | ❌ Blocked | Repository inspection only, no LLM |
| Metadata-only proof | ❌ Blocked | Evidence requires SourceLocation data |
| Search zero-results | ❌ Blocked | Returns UNRESOLVED, not VERIFIED_ABSENT |
| Retrieval-based ground truth | ❌ Blocked | Only DIRECT repository evidence accepted |

**Critical**: The validator distinguishes:
```
Search result: 0 items found
        ≠
Repository ground truth: Symbol verified absent
```

## Negative Claim Safety

For absence claims, the validator implements strict semantics:

**UNRESOLVED** (conservative default)
- Symbol not found in indexes
- RIM coverage may be incomplete
- Cannot confirm absence without examining all entities
- Example: "setupMockHTTPServer" not in indexes → UNRESOLVED

**VERIFIED_ABSENT** (never produced in current implementation)
- Would require exhaustive repository coverage
- Not implemented in Stage 2
- Future enhancement: repository scans with coverage metrics

**Key principle**: When in doubt, return UNRESOLVED, never fake certainty.

## Test Results

### Stage 1 Tests
```
test_investigation_framework.py:              20 tests ✅
test_investigation_framework_hardened.py:     30 tests ✅
test_stage1_evidence_integrity.py:             8 tests ✅
───────────────────────────────────────────────────────
Subtotal Stage 1:                             58 tests ✅
```

### Stage 2 Tests
```
test_ground_truth_validator.py:               24 tests ✅

Test categories:
  - Positive claims (6 tests): Functions, classes, files, routes, services, features
  - Negative claims (3 tests): Entity not found → UNRESOLVED
  - Agent assertion bypass (2 tests): Assertions cannot become ground truth
  - Search zero-results protection (2 tests): Zero results ≠ verified absent
  - Phase 8A regression (4 tests): Fabricated entities rejected
  - Result validation (4 tests): Safety invariants enforced
  - Provenance (3 tests): Evidence includes source location
───────────────────────────────────────────────────────
Subtotal Stage 2:                             24 tests ✅

Total:                                        82 tests ✅
```

## Phase 8A Regression Prevention

The validator prevents the exact Phase 8A.6 failure:

**Phase 8A.6 Attack**:
```
1. Fixture contains: setupMockHTTPServer (fabricated)
2. Test passes: setupMockHTTPServer "verified present"
3. Cascade effect: Diagnosis based on false positive
```

**Stage 2 Defense**:
```
1. Claim: "setupMockHTTPServer exists"
2. Validator inspects RIM
3. Result: UNRESOLVED (not found in indexes)
4. Not VERIFIED_PRESENT → Cannot use as ground truth
5. Investigation cannot proceed with false entity
```

**Regression Test Coverage**:
- `test_phase8a_setupMockHTTPServer_not_accepted` ✅
- `test_phase8a_handleAuthFlow_not_accepted` ✅
- `test_phase8a_LoginComponent_not_accepted` ✅
- `test_phase8a_fixture_path_cannot_establish_truth` ✅

All Phase 8A fabricated entities return UNRESOLVED, never VERIFIED_PRESENT.

## Remaining Limitations

The validator has intentional scope limitations:

1. **VERIFIED_ABSENT not implemented**: Would require exhaustive repository scan with coverage metrics. Returns UNRESOLVED instead.

2. **Single RIM query**: Does not perform multiple inspection strategies. Uses QueryLayer indexes (functions, classes, files).

3. **No regex/fuzzy matching**: Exact name matching only. Could miss partial matches or aliased symbols.

4. **Feature validation**: Keyword/capability search only. Does not parse code to confirm features.

5. **No schema validation**: Assumes RIM EntityType classification is correct.

These are appropriate boundaries for Stage 2. Advanced features belong in Stage 3+.

## Backward Compatibility

✅ All Stage 1 tests remain passing (58/58)
✅ No changes to Finding or Evidence safety invariants
✅ GroundTruthValidator is independent module
✅ Can integrate with Finding without breaking existing code

## Acceptance Criteria Status

- [x] GroundTruthValidator exists
- [x] Uses repository-grounded inspection (QueryLayer on RIM)
- [x] Is deterministic (no randomness, no LLM)
- [x] Has no LLM dependency
- [x] Positive claims require independent repository evidence
- [x] Negative claims distinguish VERIFIED_ABSENT from UNRESOLVED
- [x] Search zero-results cannot automatically prove absence
- [x] Agent assertions cannot establish ground truth
- [x] Metadata/file paths cannot establish ground truth
- [x] Ground-truth output uses actual Evidence objects
- [x] Provenance identifies what was inspected and why
- [x] Phase 8A fabricated-entity regression is covered
- [x] Adversarial tests cover positive and negative cases
- [x] All Stage 1 tests still pass
- [x] No Stage 3+ functionality is implemented

## Integration Notes

**For Stage 3 (Multi-Agent Orchestrator)**:

```python
# Scout agent discovers claim
claim = "redis_connection_pool exists"

# Ground-Truth Validator verifies
from backend.investigation import GroundTruthValidator
validator = GroundTruthValidator(rim_model)
result = validator.validate_symbol_exists("redis_connection_pool")

if result.status == VerificationStatus.VERIFIED_PRESENT:
    # Use result.evidence as Finding.ground_truth_evidence
    finding.ground_truth_evidence = result.evidence
    finding.ground_truth_claim = "EXISTS"
elif result.status == VerificationStatus.UNRESOLVED:
    # Cannot proceed with investigation
    finding.status = FindingStatus.UNRESOLVED
else:  # VERIFIED_ABSENT
    finding.ground_truth_claim = "ABSENT"
    finding.ground_truth_evidence = result.evidence
```

## Commit

Commit hash: [pending - will be created after verification]

Message: `Stage 2: Add repository-grounded ground truth validator`

## What's Next

No further work in this session. Stage 2 is complete.

**Future work** (Stage 3+):
- Multi-agent orchestrator (Scout, Verification, Main agents)
- Scout agent evidence gathering with actual Evidence objects
- Verification agent contradiction testing
- Main agent confirmation decisions
- Context minimization for LLM (FindingPacket < 500 chars)
- Integration with investigation loop
