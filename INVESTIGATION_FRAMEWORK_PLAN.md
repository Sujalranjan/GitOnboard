# Multi-Agent Investigation Framework — Implementation Plan

## Current State

**Existing Infrastructure**:
- ✓ Agent foundation: `backend/agent/`
- ✓ Orchestrators: `backend/agent/planning/`, `backend/agent/tasks/`, `backend/verification/`
- ✓ Test infrastructure: `backend/tests/unit/` with orchestrator tests
- ✓ Investigation structure: `investigations/phase_8a/` (just created)

**What's Missing**:
- Investigation-specific framework (Scout, Verification, Ground-Truth agents)
- Finding packet schema and state machine
- Evidence artifact organization
- Context minimization mechanism
- Ground-truth validation framework
- Phase 8A protection mechanism

## Design Decisions

### 1. Reuse Existing Orchestrators
Use existing `backend/agent/tasks/orchestrator.py` and `backend/verification/orchestrator.py` as the foundation.

Do NOT create new orchestration logic.

Instead, create investigation-specific **concerns** on top:
- Finding schemas
- Evidence classification
- Ground-truth validation
- Verification workflows

### 2. Investigation Artifact Structure

```
backend/
├── investigation/
│   ├── __init__.py
│   ├── framework.py                    # Main investigation orchestrator
│   ├── agents.py                        # Scout, Verification, GT agents
│   ├── finding.py                       # Finding schema & state machine
│   ├── evidence.py                      # Evidence classification & artifacts
│   ├── ground_truth.py                  # Ground-truth validation
│   ├── verification.py                  # Contradiction checking
│   └── summary.py                       # Context minimization
│
├── tests/unit/
│   └── test_investigation_framework.py  # Comprehensive tests

investigations/
├── phase_8a/                            # Existing phase 8a
├── templates/
│   ├── finding-template.json
│   ├── evidence-template.json
│   └── trace-template.json
└── schemas/
    ├── finding.schema.json
    └── evidence.schema.json
```

### 3. Core Components

#### A. Finding Schema (`backend/investigation/finding.py`)

```python
@dataclass
class Finding:
    finding_id: str                    # RETRIEVAL-001
    severity: Literal["P0", "P1", "P2"]
    status: Literal[
        "OBSERVED",
        "HYPOTHESIS", 
        "GROUND_TRUTH_VERIFIED",
        "INVESTIGATED",
        "INDEPENDENTLY_VERIFIED",
        "CONFIRMED",
        "REFUTED",
        "UNRESOLVED"
    ]
    claim: str
    evidence_files: List[str]          # Pointers to JSON/artifacts
    next_investigation: str            # What to do next
```

#### B. Evidence Classification (`backend/investigation/evidence.py`)

```python
@dataclass
class Evidence:
    type: Literal["DIRECT", "INDIRECT", "INFERRED", "UNVERIFIED"]
    source: str                         # source code, parser output, etc.
    location: str                       # file:line or path
    observation: str
    confidence: float                   # 0.0 - 1.0
```

#### C. Ground-Truth Validator (`backend/investigation/ground_truth.py`)

```python
def validate_ground_truth(
    claim_type: Literal["EXISTS", "ABSENT", "MISSING", "FUNCTIONAL"],
    target: str,
    repository: Repository
) -> Literal["CONFIRMED_EXISTS", "CONFIRMED_ABSENT", "UNRESOLVED"]:
    """
    Directly inspect repository to verify existence claims.
    Never accept test fixtures or previous reports as ground truth.
    """
```

#### D. Scout Agent Factory (`backend/investigation/agents.py`)

```python
class ScoutAgent:
    """Generic evidence collector. Do NOT modify code."""
    
class VerificationAgent:
    """Attempt to disprove findings."""
    
class GroundTruthAgent:
    """Verify existence/absence claims before other investigations."""
```

#### E. Investigation Orchestrator (`backend/investigation/framework.py`)

```python
class InvestigationLeader:
    """
    Main investigation orchestrator.
    Launches scouts in parallel.
    Coordinates verification.
    Minimizes context for main agent.
    """
    
    def start_parallel_scouts(findings: List[str]) -> List[FindingPacket]:
        """Launch independent scouts for different areas."""
        
    def verify_ground_truth(finding: Finding) -> bool:
        """Mandatory for negative claims."""
        
    def coordinate_verification(finding: Finding) -> Verdict:
        """Try to disprove finding independently."""
        
    def generate_summary(findings: List[Finding]) -> CompactSummary:
        """Keep main context small."""
```

### 4. Investigation State Machine

```
[OBSERVED]
    ↓ (scout reports hypothesis)
[HYPOTHESIS] ← (no ground truth yet)
    ↓ (must verify ground truth for negative claims)
[GROUND_TRUTH_VERIFIED]
    ↓ (investigate if ground truth confirmed)
[INVESTIGATED]
    ↓ (independent verification)
[INDEPENDENTLY_VERIFIED]
    ↓ (result)
[CONFIRMED | REFUTED | UNRESOLVED]
```

**Invariant**: Do NOT skip GROUND_TRUTH_VERIFIED for claims involving:
- Missing symbols
- Missing files
- Missing routes
- Retrieval failures
- Parser failures
- Index failures

### 5. Phase 8A Protection

Implement explicit guard:

```python
class Phase8AProtection:
    """
    Prevent: Bad test fixture → False retrieval failure → Parser fix
    
    Rule: Ground truth validation MUST happen before:
    - Retrieval recall diagnosis
    - Parser failure diagnosis
    - Index failure diagnosis
    - Pipeline failure diagnosis
    """
    
    def validate_before_pipeline_diagnosis(finding: Finding) -> bool:
        if finding.claim_type in ["RETRIEVAL_FAILURE", "PARSER_FAILURE"]:
            if not finding.ground_truth_verified:
                return False  # Block diagnosis
        return True
```

## Implementation Stages

### Stage 1: Foundation (Day 1)
- [x] Review existing orchestrators
- [ ] Create `backend/investigation/` package
- [ ] Implement Finding schema
- [ ] Implement Evidence schema
- [ ] Write 5 basic tests

### Stage 2: Ground-Truth Framework (Day 1-2)
- [ ] Implement GroundTruthValidator
- [ ] Write tests for positive/negative claims
- [ ] Test Phase 8A corruption detection
- [ ] Write 10 tests

### Stage 3: Scout & Verification (Day 2)
- [ ] Create ScoutAgent base
- [ ] Create VerificationAgent base
- [ ] Implement contradiction checking
- [ ] Write 8 tests

### Stage 4: Orchestration (Day 2-3)
- [ ] Create InvestigationLeader
- [ ] Implement parallel scout coordination
- [ ] Implement verification workflow
- [ ] Write 10 tests

### Stage 5: Context Minimization (Day 3)
- [ ] Create context summary generator
- [ ] Test summary quality
- [ ] Verify main context stays <2000 words
- [ ] Write 5 tests

### Stage 6: End-to-End Demo (Day 3-4)
- [ ] Create deliberate test issue (Phase 8A style)
- [ ] Run full investigation
- [ ] Verify corruption detected early
- [ ] Document lessons

### Stage 7: Documentation (Day 4)
- [ ] Framework architecture guide
- [ ] Agent usage guide
- [ ] Example investigations
- [ ] API reference

## Testing Strategy

### Unit Tests
- Finding state transitions
- Evidence classification
- Ground-truth validation
- Negative-claim protection
- Scout/verification workflows

### Integration Tests
- Parallel scout execution
- Verification contradiction flow
- Context summarization
- Full investigation pipeline

### Regression Tests
- Phase 8A corruption detection
- Bad fixture rejection
- Incomplete evidence blocking

### End-to-End Tests
- Deliberate planted issue
- Full investigation run
- Verification of verdict
- Context size verification

**Target**: 38+ tests covering all scenarios

## File Organization

```
backend/investigation/
├── __init__.py
├── framework.py          (main orchestrator, 250 lines)
├── agents.py             (agent bases, 200 lines)
├── finding.py            (finding schema, 150 lines)
├── evidence.py           (evidence schema, 120 lines)
├── ground_truth.py       (GT validator, 180 lines)
├── verification.py       (verification workflow, 150 lines)
└── summary.py            (context minimizer, 100 lines)

backend/tests/unit/
└── test_investigation_framework.py     (600 lines, 40+ tests)

investigations/
├── phase_8a/              (existing)
├── schemas/
│   ├── finding.json
│   └── evidence.json
└── templates/
    ├── scout-report.txt
    └── verification-result.txt
```

## Success Criteria

1. ✓ Framework prevents Phase 8A corruption from cascading
2. ✓ Main Claude Code context stays <2000 words for summaries
3. ✓ Scouts can investigate independently without main agent context
4. ✓ Ground truth validation blocks incorrect findings
5. ✓ Verification agents can disprove findings
6. ✓ All 40+ tests pass
7. ✓ End-to-end demo runs successfully
8. ✓ Documentation explains all patterns

## Non-Goals

- Do NOT replace existing orchestrators
- Do NOT create complex multi-agent autonomy
- Do NOT modify core agent loop
- Do NOT change parser/retrieval/RIM (observation only)
- Do NOT create enterprise framework

## Timeline

Total estimated effort: **3-4 days**
- Foundation & tests: 1 day
- Core framework: 1 day
- Orchestration & verification: 1 day
- Demo & documentation: 0.5-1 day

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Complexity bloat | Strict scope; reuse existing patterns |
| Test coverage gaps | Start with tests; write code to pass them |
| Poor integration | Build on top of existing orchestrators |
| Documentation unclear | Document as we go; include examples |

---

**Ready to proceed to Stage 1 implementation.**
