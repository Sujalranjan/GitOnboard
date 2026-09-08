# Data Validation Gates

Three-stage validation framework to independently verify repository intelligence data integrity before Phase 2M research work.

## Overview

**DO NOT** proceed to Phase 2M benchmarking until all three gates pass.

Each gate is independent and can be run in sequence:

```
GATE 1: Storage/Persistence ✓
GATE 2: Symbol Extraction ✓
GATE 3: Tools Harness ✓
→ Phase 2M Approved
```

---

## GATE 1 — Storage/Persistence Verification

**Purpose**: Cross-verify PostgreSQL ↔ Azure blob storage ↔ Repository

**What it checks**:
- ✓ Analysis record exists and is in "Completed" state
- ✓ File counts match across PostgreSQL and blob storage
- ✓ File paths are canonical (no backslashes, no duplicates)
- ✓ PostgreSQL referential integrity (no NULL IDs)
- ✓ Symbols link to valid file records
- ✓ Relationships reference valid symbols (ZERO orphaned)
- ✓ No orphaned analysis data
- ✓ No duplicate data across analyses

**Usage**:

```bash
cd /home/dheeraj/repository_intelligence_platform

# Run verification for Analysis 7 (or your analysis ID)
python -m backend.validation.gate1_storage_consistency 7
```

**Expected Output**:
```
GATE 1: Storage Consistency Verification
Analysis ID: 7
============================================================

CHECK 1: Analysis exists in database...
  ✓ Analysis 7 exists, status: Completed

CHECK 2: File counts consistency...
  ✓ PostgreSQL: 150 files, 150 unique paths

CHECK 3: File path canonicalization...
  ✓ All 150 file paths are canonical

CHECK 4: PostgreSQL referential integrity...
  ✓ PostgreSQL integrity OK (11072 symbols)

CHECK 5: Blob storage consistency...
  ✓ Blob storage consistency OK (sampled 10 files)

CHECK 6: Symbol ↔ File links...
  ✓ All 11072 symbols link to valid files

CHECK 7: Relationship ↔ Symbol references...
  ✓ All 22133 relationships reference valid symbols (ZERO orphaned)

CHECK 8: No orphaned data...
  ✓ No orphaned data found

CHECK 9: No cross-analysis duplicates...
  ✓ No duplicates found

============================================================
GATE 1 REPORT

Status: ✅ PASS | 9 passed, 0 failed | 0 warnings
```

**Passing Criteria**:
- All 9 checks pass (✓)
- Zero orphaned relationships
- Zero errors in report

---

## GATE 2 — Symbol Extraction Verification

**Purpose**: Manually verify that extracted symbols correctly map to actual source code

**What it checks**:
- ✓ Sampled symbols exist in PostgreSQL
- ✓ Line boundaries (start_line, end_line) are valid
- ✓ Symbol names appear in source code at specified lines
- ✓ Functions, classes, methods, components are correctly identified
- ✓ Qualified names match source structure

**Usage**:

```bash
cd /home/dheeraj/repository_intelligence_platform

# Sample and verify 5 files with symbols
python -m backend.validation.gate2_symbol_extraction 7 5

# Or specify repository directory if not in default location
python -m backend.validation.gate2_symbol_extraction 7 5 /tmp/repo-analysis/job_9_GitOnboard
```

**Expected Output**:
```
============================================================
GATE 2: Symbol Extraction Verification
Analysis ID: 7
Sample Size: 5
============================================================

Repository: https://github.com/salianDheeraj/GitOnboard
Analysis Status: Completed

Sampled 5 files with symbols:

────────────────────────────────────────────────────────────
FILE: backend/intelligence/engine/orchestration/pipeline.py
Extension: .py
File ID: 7:urn:file:backend/intelligence/engine/orchestration/pipeline.py
Size: 8234 bytes

✓ Source file found at: /tmp/repo-analysis/job_9_GitOnboard/backend/intelligence/engine/orchestration/pipeline.py

  Symbol: AnalysisEngine
  Type: class
  Qualified Name: backend.intelligence.engine.orchestration.pipeline.AnalysisEngine
  Lines: 42-156
  ID: 7:urn:class:AnalysisEngine

  Source snippet (lines 42-156):
    class AnalysisEngine:
        """Orchestrate repository analysis pipeline."""
        
        def __init__(self, db: Session):
    ✅ Symbol name 'AnalysisEngine' found in source

  Symbol: run_analysis
  Type: method
  Qualified Name: backend.intelligence.engine.orchestration.pipeline.AnalysisEngine.run_analysis
  Lines: 48-75
  ID: 7:urn:method:run_analysis

  Source snippet (lines 48-75):
        def run_analysis(self, repo_path: str) -> RepositoryModel:
            """Run complete analysis pipeline."""
            # ... implementation
    ✅ Symbol name 'run_analysis' found in source

============================================================
GATE 2 SUMMARY

Total symbols verified: 15
Source-matched symbols: 15/15
Match rate: 100.0%

✓ All symbols verified against source code
```

**Passing Criteria**:
- Match rate ≥ 80% (ideally 100%)
- Symbol names found in source code
- Line boundaries are valid and contain the symbol

---

## GATE 3 — Tools Test Harness

**Purpose**: Test repository inspection tools against real GitOnboard data

**Available Tests**:

```bash
cd /home/dheeraj/repository_intelligence_platform

# List files matching pattern
python -m backend.validation.gate3_tools_harness 7 find_files 'backend'

# List symbols matching pattern
python -m backend.validation.gate3_tools_harness 7 find_symbols 'process'

# Find relationships from a symbol
python -m backend.validation.gate3_tools_harness 7 find_relationships '7:urn:class:AnalysisEngine'

# Navigate graph neighbors
python -m backend.validation.gate3_tools_harness 7 graph_neighbors '7:urn:class:AnalysisEngine'

# Retrieval search
python -m backend.validation.gate3_tools_harness 7 retrieval_search 'entity extraction'

# Assemble context around symbol
python -m backend.validation.gate3_tools_harness 7 context_assembly '7:urn:class:AnalysisEngine'
```

**Expected Output** (find_files):
```
TEST: find_files('backend')
────────────────────────────────────────────────────────────
Found 87 files matching 'backend':
  - backend/intelligence/engine/orchestration/pipeline.py (8234 bytes)
  - backend/intelligence/engine/orchestration/stage6_graph_navigation.py (9281 bytes)
  - backend/intelligence/rim/entity.py (4521 bytes)
  - backend/intelligence/rim/relationship.py (3214 bytes)
  ... and 83 more

✓ Test passed
```

**Test Cases**:
- `find_files <pattern>` — Search for files by name
- `find_symbols <pattern>` — Search for symbols by name
- `find_relationships <symbol_id>` — Find all outgoing relationships
- `graph_neighbors <symbol_id>` — Visualize graph neighbors (in/out)
- `retrieval_search <query>` — Full-text lexical search
- `context_assembly <symbol_id>` — Build context around a symbol

**Passing Criteria**:
- Tests return results
- No errors or exceptions
- Results are meaningful and accurate

---

## Validation Workflow

### Step 1: Run GATE 1

```bash
python -m backend.validation.gate1_storage_consistency 7
```

Check for:
- ✅ 9/9 checks passed
- ✅ ZERO orphaned relationships
- ✅ All data consistent

If GATE 1 fails, **stop here**. Investigate the errors before proceeding.

### Step 2: Run GATE 2

```bash
python -m backend.validation.gate2_symbol_extraction 7 5
```

Check for:
- ✅ Match rate ≥ 80%
- ✅ Symbol names found in source
- ✅ Line boundaries accurate

If GATE 2 shows low match rate, investigate symbol extraction bugs.

### Step 3: Run GATE 3

```bash
# Test several query operations
python -m backend.validation.gate3_tools_harness 7 find_files 'backend'
python -m backend.validation.gate3_tools_harness 7 find_symbols 'process'
python -m backend.validation.gate3_tools_harness 7 retrieval_search 'repository'
```

Check for:
- ✅ All tests return results
- ✅ Results are accurate
- ✅ No errors

---

## When All Gates Pass

Once all three gates pass:

```
✅ GATE 1: Storage/Persistence verified
✅ GATE 2: Symbol Extraction verified
✅ GATE 3: Tools tested and working

→ Phase 2M research/benchmarking APPROVED
```

Document the validation state:
- Analysis ID: 7
- Timestamp: 2026-09-07
- Gate 1: PASS (9/9, zero orphaned)
- Gate 2: PASS (100% symbol match)
- Gate 3: PASS (all tools working)

---

## Troubleshooting

### GATE 1 Failures

**Orphaned relationships found**:
- Check Phase 2L.9 fix is deployed
- Rebuild backend with latest code
- Run fresh analysis

**Blob storage consistency issues**:
- Verify blob names in PostgreSQL match Azurite
- Check BLOB_UPLOAD logs in backend
- Verify code-file-only filtering is active

### GATE 2 Failures

**Low symbol match rate**:
- Verify source files exist in repository directory
- Check symbol line boundaries are correct
- Review parser output for specific file types (Python vs JS)

**Symbol name not found in source**:
- Symbol line boundaries might be off by one
- Symbol extraction might have a bug
- Review extracted vs actual source

### GATE 3 Failures

**No results from search**:
- Verify analysis is in Completed state
- Check database has symbols and files
- Verify symbol IDs are correct format

**Tool errors**:
- Check Python imports and dependencies
- Verify database connection
- Review error message for specific issue

---

## Next Steps After Validation

Once all gates pass:

1. Document validation results
2. Tag the verified analysis as "canonical"
3. Proceed to Phase 2M benchmarking (do NOT run before gates pass)
4. Run Phase 2M validation tools against canonical analysis
5. Do NOT modify or re-run the verified analysis

---

## Files

- `gate1_storage_consistency.py` — Storage verification
- `gate2_symbol_extraction.py` — Symbol extraction verification  
- `gate3_tools_harness.py` — Tools testing framework
- `README.md` — This file
- `__init__.py` — Module init
