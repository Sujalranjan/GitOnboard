# Phase 2K.4: Repository File Eligibility & Filtering

**Status:** SPECIFICATION READY FOR IMPLEMENTATION  
**Priority:** HIGH (improves RIM correctness)  
**Dependencies:** Phase 2K.1, 2K.3 complete

---

## Objective

Implement hybrid file eligibility strategy to exclude dependencies, generated artifacts, caches, and build output while retaining meaningful developer-authored source code and relevant config files.

**This is NOT just performance optimization — file eligibility is part of RIM correctness.**

---

## 15-Task Implementation Plan

### 1. Audit Current Repository Loader
- Inspect directory traversal implementation
- Document file discovery mechanism
- Check existing .gitignore handling
- Locate file-type checking logic
- Map FileInfo/RepositoryManifest construction

### 2. Define File Categories
- **SOURCE:** .py, .js, .ts, .jsx, .tsx, etc.
- **CONFIG/METADATA:** package.json, pyproject.toml, Dockerfile, etc.
- **GENERATED/DEPENDENCY/BUILD:** .next/, node_modules/, __pycache__/, dist/, build/, etc.
- **UNSUPPORTED/IRRELEVANT:** Everything else

### 3. Built-in Directory Exclusions
Centralized policy excluding:
```
.git/
node_modules/
.next/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
venv/
dist/
build/
coverage/
target/
[others from FILE_SCANNER_EXCLUSIONS.md]
```

### 4. Supported Source File Types
Reuse existing language registry + apply eligibility rules.

### 5. .gitignore Support
- Implement .gitignore parsing (library or custom)
- Apply consistently during scanning
- Combine with built-in exclusions
- Preserve built-in defaults even if .gitignore doesn't list them

### 6. Generated File Detection
Conservative detection for:
- *.min.js, *.min.css
- *.map files
- *.bundle.js, *.chunk.js
- Common generated markers

### 7. Config/Metadata Files
Separate category from source AST analysis. Route to specialized analyzers if available.

### 8. File Eligibility API
Create single decision point:
```
classify_file(path) -> FileCategory
  ├─ SOURCE
  ├─ CONFIG
  ├─ GENERATED
  ├─ DEPENDENCY
  ├─ IGNORED
  └─ UNSUPPORTED
```

### 9. Preserve Manifest Visibility
Maintain repository statistics even for excluded files:
- total discovered files
- analyzed source files
- ignored files
- generated files
- config files
- unsupported files

### 10. Test with Real GitOnboard
Verify before/after on actual repository:
- Exclude: .next/, node_modules/, .git/, __pycache__/, dist/, build/
- Include: backend/**/*.py, frontend/**/*.{js,ts,jsx,tsx}
- Record statistics

### 11. Verify RIM Quality
Confirm:
- .next/**/*.js no longer contributes relationships
- Legitimate source relationships intact
- Entity/relationship counts reasonable

### 12. Performance Check
Record before/after:
- files analyzed
- analysis time
- entities
- relationships

### 13. Regression Tests
Add 15+ focused tests covering:
- Directory exclusions (.next, node_modules, .git, __pycache__)
- Source inclusion (.py, .js, .ts, .jsx, .tsx)
- Generated detection (.min.js, .map, .chunk.js)
- .gitignore rules
- Config/metadata classification
- Nested directory exclusion

### 14. Preserve Current RIM
Ensure no breaking changes to:
- RIM semantics
- CallGraphAnalyzer
- UsesAnalyzer
- Retrieval architecture
- ContextAssembler
- LLM integration
- Legitimate source/test files

### 15. Document Policy
Create PHASE2K4_FILE_FILTERING_REPORT.md with:
- Current vs new behavior
- Classification model
- Exclusion rules
- .gitignore behavior
- Generated file detection
- Before/after statistics
- RIM quality impact
- Performance impact
- Tests added
- Limitations

---

## Success Criteria

**FILE_FILTERING_VALIDATED** requires:
- ✓ Focused file-filter tests pass
- ✓ Repository-loader tests pass
- ✓ Real GitOnboard analysis runs
- ✓ .next/node_modules/etc. excluded from source analysis
- ✓ Legitimate source included
- ✓ RIM relationships remain valid
- ✓ Before/after metrics documented

---

## Key Constraints

- Do NOT hardcode massive exclusion lists — use centralized policy
- Do NOT ignore .gitignore — respect repository intentions
- Do NOT break current RIM or analyzers
- Do NOT remove legitimate source/tests
- Do NOT treat generated files as source entities
- DO preserve manifest visibility
- DO maintain RIM correctness
- DO document WHY files are excluded

---

## Expected Impact

### Before (Current State)
- 2,495 files scanned
- Includes .next/ build artifacts
- Unnecessary entities: 5,000-10,000
- Unnecessary relationships: 20,000-50,000
- Analysis time: 100+ seconds

### After (Expected)
- 1,200-1,500 files scanned
- Excludes .next/, node_modules/, caches
- Cleaner entities: 27,000-28,000
- Cleaner relationships: 100,000-110,000
- Analysis time: 60-80 seconds

**Key metric: RIM correctness, not just speed**

---

## Related Documentation

- `FILE_SCANNER_EXCLUSIONS.md` — Comprehensive exclusion list
- `PHASE2K1_VALIDATION_RESULTS.md` — Analysis baseline
- `PHASE2K3_RETRIEVAL_FIX_REPORT.md` — Retrieval architecture

---

## Next Session

1. Audit current repository loader implementation
2. Implement file classification model
3. Add .gitignore support
4. Test with real GitOnboard
5. Document results

---

**Status:** Ready for Phase 2K.4 implementation  
**Estimated Effort:** 2-3 hours  
**Blocking:** None (enhancement, not blocking)  
**Depends On:** Phase 2K.1, 2K.3 complete ✓
