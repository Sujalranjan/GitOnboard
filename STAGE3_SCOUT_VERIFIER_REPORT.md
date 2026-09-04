# Stage 3: Scout and Verification Agents

## Summary

Successfully completed **Stage 3: Scout and Verification Agents** for the Multi-Agent Investigation Framework. Established the first real multi-agent investigation workflow with independent roles while preserving all Stage 1 and Stage 2 safety guarantees.

**Key Achievement**: Scout produces hypotheses; Verification independently validates them.

## Files Changed

| File | Status | Purpose |
|------|--------|---------|
| `backend/investigation/scout.py` | Created | ScoutAgent, ScoutHypothesis, ScoutStrategy |
| `backend/investigation/verifier.py` | Created | VerificationAgent, VerificationContext, VerificationResult |
| `backend/tests/unit/test_scout_and_verifier.py` | Created | 21 comprehensive adversarial tests |
| `backend/investigation/__init__.py` | Modified | Export Scout and Verification components |

## Scout Architecture

```
Investigation Query
    ↓
ScoutAgent
    ├─ Search repository using QueryLayer
    ├─ Generate hypotheses (not confirmations)
    └─ Classify evidence conservatively (INDIRECT, not DIRECT)
    ↓
ScoutHypothesis
    ├─ claim (what Scout found)
    ├─ strategy (how Scout found it)
    ├─ evidence (INDIRECT search results)
    ├─ evidence_locations (for navigation, not proof)
    └─ requires_ground_truth (for negative claims)
```

### Scout Responsibilities

- Discover potential claims from repository
- Generate hypotheses (allowed to be wrong)
- Use QueryLayer for repository search
- Classify evidence by what was actually observed
- Never upgrade evidence classification (INDIRECT stays INDIRECT)
- Cannot mark findings as confirmed

### Scout Evidence Classification

Scout evidence is always conservative:
- **EXISTS claim with function found**: INDIRECT (0.7 confidence)
- **ABSENT claim**: INDIRECT (0.5-0.7 confidence from retrieval)
- Never produces DIRECT evidence (Verification's role)

## Verification Architecture

```
ScoutHypothesis
    ↓
VerificationAgent
    ├─ Parse claim independently
    ├─ Inspect repository (QueryLayer)
    ├─ Use GroundTruthValidator for ground truth
    ├─ Attempt bounded second investigation if needed
    └─ Return CONFIRMED / REFUTED / UNRESOLVED
    ↓
VerificationResult
    ├─ Finding with DIRECT evidence
    ├─ ground_truth_evidence (actual Evidence object)
    └─ verdict (CONFIRMED, REFUTED, or UNRESOLVED)
```

### Verification Responsibilities

- Independent repository inspection (does NOT trust Scout)
- Use GroundTruthValidator for repository truth
- Distinguish CONFIRMED / REFUTED / UNRESOLVED
- Bounded verification attempts (max 2)
- Refute false claims with contradicting evidence
- Return UNRESOLVED (conservative) when uncertain

### Independence Proof

Test `test_verification_is_independent_from_scout` proves:
```python
Scout evidence:      INDIRECT (0.7 confidence)
Verification evidence: DIRECT (0.95 confidence)
→ Different evidence, different confidence, different source
```

## Self-Correction Loop

Verification implements bounded self-correction:

```
Pass 1: GroundTruthValidator.validate_symbol_exists()
    ↓
    Not found?
    ↓
Pass 2: QueryLayer.find_function() + QueryLayer.get_class()
    ↓
    Result: CONFIRMED / REFUTED / UNRESOLVED
```

**Bounded**: Maximum 2 attempts per claim
**Targeted**: Second pass uses different inspection method
**Safe**: Cannot loop infinitely

## Ground Truth Integration

Verification uses `GroundTruthValidator` for all repository-grounded claims:

```python
gt_result = self.validator.validate_symbol_exists("login_user")

if gt_result.status == VerificationStatus.VERIFIED_PRESENT:
    finding.ground_truth_evidence = gt_result.evidence
    finding.ground_truth_claim = "EXISTS"
    verdict = "CONFIRMED"
```

## Context Minimization

Context passed from Scout to Verification is minimal:

```python
VerificationContext:
    ├─ hypothesis (Scout claim + evidence)
    ├─ repository_model (for inspection)
    └─ max_verification_attempts (2)
```

**NOT passed**:
- Raw LLM responses
- Complete source files
- Entire RIM
- Unfiltered search results
- Large artifacts

## Test Results

### Stage 1 Tests (Evidence Framework)
```
test_investigation_framework.py:              20 tests ✅
test_investigation_framework_hardened.py:     30 tests ✅
test_stage1_evidence_integrity.py:             8 tests ✅
───────────────────────────────────────────────────────
Subtotal Stage 1:                             58 tests ✅
```

### Stage 2 Tests (Ground-Truth Validator)
```
test_ground_truth_validator.py:               24 tests ✅
───────────────────────────────────────────────────────
Subtotal Stage 2:                             24 tests ✅
```

### Stage 3 Tests (Scout & Verification)
```
test_scout_and_verifier.py:                   21 tests ✅

Test categories:
  - Scout Agent (8 tests)
    - Find function/class (2)
    - Return None for missing (1)
    - Generate absence hypothesis (2)
    - Evidence classification (1)
    - Feature discovery (1)
    - Finding creation (1)

  - Verification Agent (5 tests)
    - Confirm existing symbol (1)
    - Refute false existence claim (1)
    - Refute false absence claim (1)
    - Independence from Scout (1)
    - Bounded attempts (1)
    - Unresolved absence (1)

  - Phase 8A Regression (4 tests)
    - setupMockHTTPServer rejected (1)
    - False claim refuted (1)
    - handleAuthFlow rejected (1)
    - LoginComponent rejected (1)

  - Workflow Integration (3 tests)
    - Full workflow confirmed (1)
    - Full workflow unresolved (1)
    - Scout evidence not as ground truth (1)
───────────────────────────────────────────────────────
Subtotal Stage 3:                             21 tests ✅

TOTAL ALL STAGES:                            103 tests ✅
```

## Phase 8A Regression Prevention

Scout and Verification prevent Phase 8A cascade failure:

**Attack Vector**: Scout claims fabricated entities exist

**Defense**:
1. Scout searches repository for "setupMockHTTPServer"
2. Entity not found → Scout returns None
3. If fabricated claim manually created:
   - Verifier independently inspects
   - GroundTruthValidator finds nothing
   - Result: UNRESOLVED (not CONFIRMED)
4. Cannot use as ground truth

**Regression Tests**:
- `test_phase8a_setupMockHTTPServer_rejected` ✅
- `test_phase8a_false_claim_refuted` ✅
- `test_phase8a_handleAuthFlow_rejected` ✅
- `test_phase8a_LoginComponent_rejected` ✅

All Phase 8A test entities are rejected as ground truth.

## Backward Compatibility

✅ All Stage 1 tests remain passing (58/58)
✅ All Stage 2 tests remain passing (24/24)
✅ No changes to Finding or Evidence safety invariants
✅ Scout and Verification are independent modules

## Architecture Diagram

```
Investigation Framework (Stages 1-3)

┌─────────────────────────────────────────────────────┐
│                  Stage 3: Multi-Agent               │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Scout Agent              VerificationAgent        │
│  ├─ Discover claims       ├─ Independent check     │
│  ├─ Generate hypotheses   ├─ Use GroundTruthValidator
│  └─ INDIRECT evidence     └─ DIRECT evidence      │
│                                                     │
└──────────────────────────────────────────────────────┤
                                                      │
┌──────────────────────────────────────────────────────┤
│                  Stage 2: Ground Truth               │
├──────────────────────────────────────────────────────┤
│                                                      │
│  GroundTruthValidator                              │
│  ├─ QueryLayer on RIM                              │
│  └─ VERIFIED_PRESENT / UNRESOLVED                  │
│                                                      │
└──────────────────────────────────────────────────────┤
                                                      │
┌──────────────────────────────────────────────────────┤
│            Stage 1: Evidence Integrity               │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Finding:                 Evidence:                 │
│  ├─ State machine         ├─ Type validation        │
│  ├─ Evidence objects      ├─ Confidence bounds      │
│  └─ Ground truth objects  └─ Separation from metadata
│                                                      │
└──────────────────────────────────────────────────────┘
```

## Remaining Limitations

Intentional boundaries for Stage 3:

1. **Scout uses QueryLayer only**: No source code parsing
2. **Verification is reactive**: Responds to Scout claims, not proactive
3. **Negative claims conservative**: Returns UNRESOLVED, not VERIFIED_ABSENT
4. **No fuzzy matching**: Exact names only
5. **No multi-agent scheduling**: Simple sequential flow
6. **No persistent agent memory**: Stateless agents

These are appropriate for Stage 3. Stage 4+ enhancements could include proactive agent strategies, fuzzy matching, multi-agent scheduling, and persistent context.

## Integration Pattern

Stage 4 orchestrator would use Stage 3 like this:

```python
from backend.investigation import ScoutAgent, VerificationAgent, VerificationContext

# Scout discovers
scout = ScoutAgent(rim_model)
hypothesis = scout.investigate_symbol("login_user")

if hypothesis:
    # Verify independently
    verifier = VerificationAgent(rim_model)
    context = VerificationContext(hypothesis, rim_model)
    result = verifier.verify(context)

    if result.verdict == "CONFIRMED":
        # Finding is ready for main agent
        print(f"Confirmed: {result.finding.claim}")
    else:
        # Investigation continues or stops
        print(f"Status: {result.verdict}")
```

## Commits

Commit hash: [pending - will be created after verification]

Message: `Stage 3: Add scout and independent verification agents`

## Acceptance Criteria Status

- [x] Scout Agent exists
- [x] Verification Agent exists
- [x] Scout generates hypotheses, not confirmations
- [x] Verification independently checks Scout claims
- [x] GroundTruthValidator remains the repository truth authority
- [x] Existing Evidence model is reused
- [x] Existing Finding state machine is reused
- [x] Scout cannot manufacture trusted ground truth
- [x] Verification cannot manufacture trusted ground truth
- [x] INDIRECT evidence cannot become DIRECT by agent assertion
- [x] Negative claims remain conservative
- [x] Verification supports CONFIRMED / REFUTED / UNRESOLVED
- [x] Self-correction is bounded
- [x] Repeated identical searches are prevented by design
- [x] Context passed between agents is compact
- [x] Phase 8A fabricated-entity regression is covered
- [x] Stage 1 tests remain passing (58/58)
- [x] Stage 2 tests remain passing (24/24)
- [x] No Stage 4+ functionality is implemented

## What's Next

No further work in this session. Stage 3 is complete.

**Future work** (Stage 4+):
- InvestigationOrchestrator for multi-agent coordination
- Scout → Verification → MainAgent flow
- Artifact persistence for evidence
- Context minimization with FindingPacket
- Autonomous investigation loops
- LLM integration for claim generation
