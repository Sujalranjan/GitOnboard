# Phase 2C: Symbol Extraction Root Cause Analysis

## STATUS: INVESTIGATION IN PROGRESS

This report documents the investigation into why `AnalysisEngine.run()` produces a `RepositoryModel` with 0 symbols despite 1369 files being successfully extracted.

---

## Phase 1: AnalysisEngine Execution Trace

### Target: `backend/intelligence/engine/orchestration/pipeline.py`

**Objective:** Trace the complete execution path from `AnalysisEngine.run()` to `RepositoryModel` creation.

**Investigation Required:**

1. How does AnalysisEngine.run() initialize?
2. What scanner is used to discover files?
3. How are languages detected for each file?
4. How are parsers selected based on language?
5. How are analyzers retrieved from the registry?
6. Which analyzers are executed on parsed entities?
7. How is the output collected into RepositoryModel.entities?
8. Where are relationships extracted?
9. How are errors handled?

**Status:** NOT YET TRACED - Requires code inspection

---

## Phase 2: Registry Inspection

### Target: `get_default_registry()`

**Objective:** Determine exactly what analyzers are registered and enabled.

**To Investigate:**

```python
def get_default_registry():
    # What analyzers are created?
    # Which ones are for symbol extraction?
    # Are they enabled by default?
```

**Expected Analyzer Types:**
- [ ] PythonFunctionAnalyzer
- [ ] PythonClassAnalyzer
- [ ] JavaScriptFunctionAnalyzer
- [ ] TypeScriptFunctionAnalyzer
- [ ] RelationshipAnalyzer
- [ ] Other symbol extractors

**Status:** NOT YET INSPECTED

---

## Phase 3: Search for Existing Symbol Extractors

### Objective: Determine if symbol extraction code already exists

**Search Terms to Investigate:**
- `EntityType.FUNCTION`
- `EntityType.CLASS`
- `SymbolAnalyzer`
- `extract.*symbol`
- `AST` (Abstract Syntax Tree)
- `function.*analyzer`
- `class.*analyzer`

**Possible Findings:**

### Case A: Existing extractors registered and enabled
**Action:** Find why they're not producing entities

### Case B: Existing extractors registered but disabled
**Action:** Fix the configuration

### Case C: Existing extractors not registered
**Action:** Register them

### Case D: Extractors exist but fail silently
**Action:** Add error handling

### Case E: No extractors exist at all
**Action:** Design minimal implementation

**Status:** NOT YET SEARCHED

---

## Phase 4: Minimal Test Case

### Objective: Isolate the defect with a simple fixture

**Test File Contents:**
```python
def authenticate_token():
    """Authenticate a user token."""
    pass

class AuthService:
    """Authentication service."""
    
    def login(self, username, password):
        """Login user."""
        pass
    
    def logout(self):
        """Logout user."""
        pass
```

**Test Procedure:**

1. Create minimal repository with above file
2. Run: `engine = AnalysisEngine(repo_path, registry)`
3. Run: `model = engine.run(...)`
4. Inspect: `model.entities`

**Expected Result:** Should contain:
- FILE entity for the Python file
- FUNCTION entity for `authenticate_token`
- CLASS entity for `AuthService`
- FUNCTION entity for `login` (method)
- FUNCTION entity for `logout` (method)

**Actual Result:** NOT YET TESTED

---

## Phase 5: Real Repository Analysis

### Current Analysis Results

```
Repository: GitOnboard (repo_id = 4)
Analysis ID: 14

Entity Counts:
  Files: 1369 ✓
  Symbols: 0 ✗
  Relationships: 0 ✗
```

**Key Files Containing Symbols (Should be Extracted):**

From earlier investigation:
- `backend/routers/auth.py` - Contains auth routes
- `backend/services/github_oauth.py` - Contains OAuth implementation
- `frontend/context/AuthContext.tsx` - Contains React context
- `controllers/authcontroller.js` - Contains auth controller

**Symbol Queries That Should Work:**

```
SELECT s.name FROM symbols WHERE analysis_id = 14;
→ Expected: [authenticateToken, setAuthCookies, ...]
→ Actual: []
```

---

## Execution Diagram Template

Fill in as investigation proceeds:

```
AnalysisEngine.run(repo_path, registry)
    ↓
RepositoryScanner
    └─ Discovers 1369 files ✓
    ↓
LanguageDetector
    └─ Detects Python, JavaScript, TypeScript [VERIFY]
    ↓
ParserSelection
    └─ Selects appropriate parsers [VERIFY]
    ↓
ParserExecution
    └─ Parses files into AST [VERIFY]
    ↓
AnalyzerRegistry.get_default_registry()
    └─ Returns analyzers [INSPECT]
    ↓
AnalyzerExecution
    ├─ Python symbol analyzer: [VERIFY IF EXISTS/RUNS]
    ├─ JavaScript symbol analyzer: [VERIFY IF EXISTS/RUNS]
    ├─ TypeScript symbol analyzer: [VERIFY IF EXISTS/RUNS]
    └─ Relationship analyzer: [VERIFY IF EXISTS/RUNS]
    ↓
EntityCollection
    ├─ FILE entities: 1369 ✓
    ├─ FUNCTION entities: 0 ✗ [ROOT CAUSE HERE]
    └─ CLASS entities: 0 ✗ [ROOT CAUSE HERE]
    ↓
RepositoryModel.entities
    └─ Contains only FILE entities
    ↓
save_rim_to_fact_store()
    └─ Correctly saves 1369 FactFile, 0 FactSymbol
```

---

## Investigation Checklist

### AnalysisEngine Inspection
- [ ] Locate `AnalysisEngine` class definition
- [ ] Locate `run()` method
- [ ] Identify scanner instantiation
- [ ] Identify language detection call
- [ ] Identify parser selection logic
- [ ] Identify analyzer registry call
- [ ] Identify entity collection logic
- [ ] Identify relationship extraction logic
- [ ] Identify error handling

### Registry Inspection
- [ ] Find `get_default_registry()` implementation
- [ ] List all registered analyzers
- [ ] Identify which are symbol-related
- [ ] Check enable/disable flags
- [ ] Check language applicability

### Symbol Extractor Search
- [ ] Search for `FUNCTION` analyzer
- [ ] Search for `CLASS` analyzer
- [ ] Search for symbol-related imports
- [ ] Search for AST-related code
- [ ] Check test files for symbol extraction tests

### Minimal Test Setup
- [ ] Create test repository
- [ ] Run AnalysisEngine
- [ ] Inspect RepositoryModel.entities
- [ ] Record entity counts

---

## Findings Summary

**To be completed as investigation proceeds**

### Root Cause Statement
[NOT YET DETERMINED]

### Evidence
- ✓ Phase 2B: Confirmed FactStore has 0 symbols
- ✓ Phase 2A: Confirmed retrieval returns 0 BM25 results
- ✗ Not yet: Why AnalysisEngine produces 0 symbols

### Affected Component
[INVESTIGATING]

### Fix Approach
[PENDING]

---

## Next Steps

1. **Immediate:** Inspect `backend/intelligence/engine/orchestration/pipeline.py`
2. **Secondary:** Find and inspect `get_default_registry()`
3. **Tertiary:** Search for existing symbol extractors
4. **Validation:** Run minimal test case
5. **Verification:** Re-analyze GitOnboard with findings

---

## Report Status

**Verdict:** INVESTIGATION_IN_PROGRESS

- Phase 1: NOT YET STARTED
- Phase 2: NOT YET STARTED
- Phase 3: NOT YET STARTED
- Phase 4: NOT YET STARTED
- Phase 5: NOT YET STARTED

**Do not proceed to Phase 3 RIM validation until this investigation is complete.**
