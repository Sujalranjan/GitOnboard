# Phase 8A.11: Verified Retrieval Validation Protocol

## Objective

Test retrieval (`search_repository`) for symbols confirmed to exist in Deep-Guard-Frontend source.

**Critical Principle**: Establish ground truth **before** measuring retrieval.

Do not repeat the Phase 8A.6 mistake of testing retrieval on non-existent symbols.

---

## Tested Symbols

**Ground truth source**: Phase 8A.10 audit (verified against actual repository)

### Verified-Existing Symbols (Only These)

1. **resetModal**
   - Type: function
   - Status: EXISTS ✓
   - Evidence: Found in source via grep (`const resetModal`)
   - Location: `/home/dheeraj/Deep-Guard/Deep-Guard-Frontend/src/components/ForgetPasswordModal.tsx`

2. **ForgotPasswordModal**
   - Type: class
   - Status: EXISTS ✓
   - Evidence: Found in source via grep (`const ForgotPasswordModal`)
   - Location: `/home/dheeraj/Deep-Guard/Deep-Guard-Frontend/src/components/ForgetPasswordModal.tsx`
   - Extraction status: Already extracted by parser (Phase 8A.9) ✓

---

## Testing Protocol

### Step 1: Ground-Truth Verification (MANDATORY)

Before calling `search_repository`, verify both symbols exist in source:

```bash
grep -r "const resetModal" /home/dheeraj/Deep-Guard/Deep-Guard-Frontend --include=*.ts --include=*.tsx
grep -r "const ForgotPasswordModal" /home/dheeraj/Deep-Guard/Deep-Guard-Frontend --include=*.ts --include=*.tsx
```

**Expected output**: Both commands should return file:line matches.

**If either fails**: STOP. Do not proceed with retrieval testing. Document the failure.

### Step 2: Retrieval Testing

For each verified symbol:

```
search_repository({
  query: "resetModal",
  entity_type: "function"
})

search_repository({
  query: "ForgotPasswordModal",
  entity_type: "class"
})
```

**Record for each**:
- Query executed: YES/NO
- Results found: COUNT (0 or >0)
- Found/Not Found: YES/NO
- Result type: CORRECT (matches entity_type) or INCORRECT

### Step 3: Classification

For each verified symbol, classify as:

- **TRUE POSITIVE**: Verified exists + Search found → retrieval works ✓
- **FALSE NEGATIVE**: Verified exists + Search empty → retrieval failure ✗
- **ERROR**: Query execution failed → cannot determine

---

## Metrics to Calculate

### Overall Retrieval Health

```
Verified symbols tested: 2
Found by search: ? (0, 1, or 2)
Missed by search: ? (0, 1, or 2)
Retrieval recall: ? % (found / total)
False-negative rate: ? % (missed / total)
```

### Interpretation

**If 2/2 found** (100% recall):
- Retrieval works for these symbols
- Phase 8A.6's 50% false-negative rate is invalid (based on fabricated symbols)
- No retrieval gap for these specific symbols
- Parser is not the bottleneck for ForgotPasswordModal

**If 1/2 found** (50% recall):
- Retrieval gap exists
- Trace which symbol failed and why
- Example: If `resetModal` is missing but `ForgotPasswordModal` is found, they differ in:
  - Type: function vs. class
  - Location: same file but different declarations
  - Export syntax: different?
- Investigate downstream (RIM → index → search) for the failing symbol

**If 0/2 found** (0% recall):
- Retrieval completely broken for these symbols
- Trace downstream: where do they disappear?

---

## If Retrieval Gaps Exist

**Only then** trace downstream:

```
Source code
    ↓
Loader (reads file)
    ↓ (PRESENT or ABSENT?)
Language Detection (.tsx detected?)
    ↓ (PRESENT or ABSENT?)
Parser (TypeScript provider)
    ↓ (EXTRACTED or ABSENT?)
Symbol Extraction (SymbolAnalyzer)
    ↓ (EXTRACTED or ABSENT?)
RIM Entity Creation
    ↓ (ENTITY CREATED or ABSENT?)
FactStore/Index Population
    ↓ (INDEXED or ABSENT?)
Search Query Execution
    ↓ (FOUND or ABSENT?)
Retrieval Result
```

**First confirmed disappearance point**: Where you find PRESENT → ABSENT transition.

### Example Investigation

If `resetModal` is verified in source but not found by search:

1. Check if parser extracted it: `run_phase8a9_direct_parser.py` on ForgetPasswordModal.tsx
   - Expected: resetModal extracted ✓
   - If absent: Parser is the bottleneck
   - If present: Continue downstream

2. Check if RIM has entity: Query RIM directly for `resetModal`
   - Expected: Entity exists
   - If absent: RIM creation is the bottleneck
   - If present: Continue downstream

3. Check if index has it: Query index/FactStore for `resetModal`
   - Expected: Indexed
   - If absent: Index population is the bottleneck
   - If present: Search/retrieval layer is the bottleneck

4. Diagnose and fix at the identified bottleneck only

---

## Safety Constraints

- **No code changes** during investigation
- **RIM Verdict**: Keep `CURRENTLY_UNSAFE`
- **Phase 8 Benchmark**: Keep `LOCKED`
- **Investigation only**: Document findings, do not implement fixes
- **Evidence-based only**: Use direct observation, not inference

---

## Preventing the Phase 8A.6 Mistake

**What went wrong in 8A.6**:
1. Assumed 8 entities existed without verification
2. Tested retrieval on those assumptions
3. Got "50% false-negative" result
4. Built entire Phase 8A.7-8A.8 chain on that invalid metric

**What Phase 8A.11 does differently**:
1. **Verify ground truth first** (Phase 8A.10 audit)
2. **Only test symbols confirmed to exist**
3. **If retrieval works**: Phase 8A.6 conclusion is invalid
4. **If retrieval fails**: Trace the specific failure point with direct evidence
5. **Then fix** based on verified diagnosis

---

## Success Criteria

### Phase 8A.11 is COMPLETE when:

- ✓ Both symbols verified in source
- ✓ Retrieval test executed for both
- ✓ Results classified (TP/FN/ERROR for each)
- ✓ Recall calculated
- ✓ If gaps exist, first disappearance point identified
- ✓ If no gaps exist, Phase 8A.6 conclusion invalidated

### Phase 8A.11 is BLOCKED if:

- ✗ Either symbol cannot be verified in source (rediscover why)
- ✗ Search API cannot be called (infrastructure issue)
- ✗ Results are ambiguous (e.g., search returns partial matches)

---

## Next Phases (Conditional)

**If 8A.11 shows 100% recall** (both symbols found):
- Phase 8A.6 false-negative rate is invalid
- RIM is not the bottleneck
- Parser works (already proven in 8A.9)
- Conclusion: System is functioning for these verified symbols
- Decision: Do not proceed further OR test more symbols if needed

**If 8A.11 shows <100% recall** (at least one symbol missed):
- Phase 8A.12: Trace downstream (RIM → index → search)
- Phase 8A.13: Diagnose root cause
- Phase 8A.14: Fix at identified bottleneck only

---

## Expected Outcome

This phase repairs the evidence chain broken by Phase 8A.6's bad test data.

It establishes which retrieval failures are **real** (based on verified symbols) vs. **phantom** (based on fabricated symbols).

Result determines whether the problem is:
1. **Parser/extraction** (disproven by 8A.9; ForgotPasswordModal extracted)
2. **RIM entity creation** (to be tested in 8A.12)
3. **Index/FactStore** (to be tested in 8A.12)
4. **Search/retrieval** (to be tested in 8A.12)
5. **Nothing** (system works; Phase 8A.6 was just bad test data)
