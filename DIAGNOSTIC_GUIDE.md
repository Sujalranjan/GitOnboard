# RIM Diagnostic System - Complete Guide

## Overview

The diagnostic system provides **complete visibility** into the RIM analysis pipeline:

✅ Real-time action logging  
✅ Error capture with stack traces  
✅ Relationship tracking (created vs skipped)  
✅ JSON reports for post-mortem analysis  
✅ Action replay for reproducibility  

## What Gets Logged

Every action in the pipeline is logged:

| Action Type | What's Tracked | Use Case |
|---|---|---|
| ANALYZER_START | Analyzer initialization | When did analyzer begin? |
| ANALYZER_PROCESS_FILE | File processing | Which files were skipped? Why? |
| AST_PARSE | AST type/structure | Is AST valid? |
| ANALYZER_EXTRACT_ENTITY | Entity creation | What symbols were found? |
| ANALYZER_EXTRACT_RELATIONSHIP | Relationship creation | What CALLS/USES/RENDERS were found? |
| RELATIONSHIP_SKIP | Skipped relationships | Why weren't relationships saved? |
| SYMBOL_RESOLUTION | Symbol lookup | How were symbols resolved? |
| VALIDATION_CHECK | Validation results | What passed/failed? |
| ANALYZER_ERROR | Exceptions | Where did it break? |
| ANALYZER_COMPLETE | Analyzer finish | Summary of work done |

---

## Using the Diagnostic System

### Step 1: Enable Diagnostics

The system needs an `analysis_id` to be enabled. This should be passed when calling `AnalysisEngine.run()`:

**In your code:**
```python
from backend.intelligence.engine.orchestration.pipeline import AnalysisEngine
from backend.intelligence.engine.analyzers import get_default_registry

# Your analysis_id (from database or anywhere)
analysis_id = 2

engine = AnalysisEngine(target_dir, get_default_registry())
model = engine.run(
    repo_name="my-repo",
    commit_info={...},
    analysis_id=analysis_id  # <-- ENABLES DIAGNOSTICS
)
```

**In Docker/API context:**
Find where `AnalysisEngine.run()` is called and add `analysis_id` parameter.

### Step 2: Run Analysis

Run your analysis normally. The system will:
- Create `/tmp/rim_diagnostics/` directory
- Log every action to memory
- Save reports at the end

### Step 3: Check Logs

**Real-time:**
```bash
docker compose logs backend | grep -E "\[CallGraphAnalyzer\]|\[RELATIONSHIP_SKIP\]|\[ANALYZER_ERROR\]"
```

**Stored reports:**
```bash
ls -la /tmp/rim_diagnostics/analysis_*_report.json
```

### Step 4: Analyze Reports

**Quick analysis:**
```bash
uv run python -m backend.intelligence.diagnostics.analyzer /tmp/rim_diagnostics/analysis_2_report.json
```

**Sample output:**
```
================================================================================
ANALYSIS REPORT: 2
Repository: Deep-Guard-Frontend
Time Range: 2026-09-01T... to 2026-09-01T...

KEY METRICS:
  Files Processed: 125
  Entities Created: 375
  Total Relationships: 375

RELATIONSHIP BREAKDOWN:
  DECLARES: 178
  IMPORTS: 197

ANALYZERS RUN:
  ✓ CallGraphAnalyzer
  ✓ SymbolAnalyzer
  ✓ ImportAnalyzer
  ✓ UsesAnalyzer

ERRORS (0):
  None

STATUS:
  ⚠️  PROBLEM: New relationship types (CALLS, USES, RENDERS) not found!
  
  This indicates:
  1. New analyzers not running
  2. OR parsers returning invalid AST
  3. OR AST traversal finding no nodes
  
  Recommendations:
  - Verify TypeScriptProvider returns valid tree-sitter Tree
  - Check for exceptions in analyzer logs
  - Review file processing to see what was skipped
```

---

## Interpreting Diagnostic Reports

### Problem: No CALLS/USES/RENDERS

**Symptom:**
```
RELATIONSHIP BREAKDOWN:
  DECLARES: 178
  IMPORTS: 197
  (NO CALLS, USES, RENDERS)
```

**Root causes to check:**

1. **CallGraphAnalyzer not running**
   - Check: Is it in `get_default_registry()`?
   - Check: Are TypeScript files being processed?

2. **AST is not tree-sitter Tree object**
   - Check: What does TypeScriptProvider return?
   - Check action log: `ANALYZER_PROCESS_FILE` shows `ast_type=?`
   - If `ast_type=NoneType`, the parser failed

3. **AST traversal not finding nodes**
   - Check: Do you see `[TS Visitor] Starting traversal from program`?
   - If not, visitor.visit() isn't being called
   - If yes, check if it's finding function_declaration, call_expression nodes

4. **Exceptions in analyzers**
   - Check: Are there `ANALYZER_ERROR` entries?
   - Read stack trace from actions log

---

## Reading the Action Log

The system saves **detailed action replay logs** (JSONL format):

```bash
cat /tmp/rim_diagnostics/analysis_2_actions.jsonl | head -20
```

**Sample output:**
```json
{"timestamp": "2026-09-01T16:00:36.095...", "action_type": "ANALYZER_START", "analyzer_name": "CallGraphAnalyzer", "file_path": "", "message": "Starting analyzer for 125 files", "details": {"file_count": 125}}
{"timestamp": "2026-09-01T16:00:36.200...", "action_type": "ANALYZER_PROCESS_FILE", "analyzer_name": "CallGraphAnalyzer", "file_path": "src/components/Login.tsx", "message": "Processing src/components/Login.tsx: ast_type=Tree", "details": {"ast_type": "Tree"}}
{"timestamp": "2026-09-01T16:00:36.210...", "action_type": "ANALYZER_EXTRACT_RELATIONSHIP", "analyzer_name": "CallGraphAnalyzer", "file_path": "src/components/Login.tsx", "message": "Created CALLS relationship", "details": {"rel_type": "CALLS", "source": "...", "target": "..."}}
```

**Parse with jq:**
```bash
# Show only errors
jq 'select(.action_type == "ANALYZER_ERROR")' /tmp/rim_diagnostics/analysis_2_actions.jsonl

# Show only skipped relationships
jq 'select(.action_type == "RELATIONSHIP_SKIP")' /tmp/rim_diagnostics/analysis_2_actions.jsonl

# Count relationships by type
jq -s 'map(select(.action_type == "ANALYZER_EXTRACT_RELATIONSHIP") | .details.rel_type) | group_by(.) | map({type: .[0], count: length})' /tmp/rim_diagnostics/analysis_2_actions.jsonl
```

---

## Debugging Specific Issues

### Issue: "AST has no root_node"

**Log:**
```
[ANALYZER_ERROR] CallGraphAnalyzer @ src/components/Login.tsx: AST missing root_node attribute
```

**Diagnosis:**
- TypeScriptProvider is returning wrong AST type
- Expected: `tree_sitter.Tree` object (has `.root_node`)
- Got: Something else (dict? None? string?)

**Fix location:**
- `backend/intelligence/engine/parser/providers/typescript.py:150`
- Check: `return ParsedFile(..., ast=tree, ...)`

---

### Issue: "Skipping: unsupported language"

**Log:**
```
[ANALYZER_PROCESS_FILE] CallGraphAnalyzer @ src/app/page.tsx: Skipped: unsupported language TypeScript
```

**Diagnosis:**
- File extension says TypeScript but language detection says something else
- OR language is correct but CallGraphAnalyzer doesn't support it

**Fix location:**
- `backend/intelligence/engine/analyzers/callgraph.py:279`
- Check: `self.supported_languages = ["Python", "TypeScript", "JavaScript"]`

---

### Issue: "Skipping: no AST available"

**Log:**
```
[ANALYZER_PROCESS_FILE] CallGraphAnalyzer @ middleware.ts: Skipped: no AST available (ast_type=NoneType)
```

**Diagnosis:**
- Parser returned `ast=None`
- Could be parse error or language not supported

**Fix location:**
- `backend/intelligence/engine/parser/providers/typescript.py:170`
- Check exception handling block

---

## Accessing Diagnostic Logs in Docker

### Option 1: Copy from running container

```bash
# While docker compose is running
docker cp <backend_container_id>:/tmp/rim_diagnostics/analysis_2_report.json ./

# Analyze
python -m backend.intelligence.diagnostics.analyzer analysis_2_report.json
```

### Option 2: Mount volume

```bash
# In docker-compose.yml
services:
  backend:
    volumes:
      - ./diagnostics:/tmp/rim_diagnostics
```

Then reports appear in `./diagnostics/` on your host machine.

### Option 3: Add logging to backend logs

Edit `backend/intelligence/engine/orchestration/pipeline.py`:

```python
if diag:
    diag.print_summary()  # This prints to stdout/logs
```

---

## Reproducing Failures

### Save the exact action sequence

All actions are saved in JSONL format. To reproduce a failure:

1. **Get the action log:**
   ```bash
   cat /tmp/rim_diagnostics/analysis_2_actions.jsonl > /tmp/failed_analysis.jsonl
   ```

2. **Write a replay test:**
   ```python
   import json
   
   with open("/tmp/failed_analysis.jsonl") as f:
       for line in f:
           action = json.loads(line)
           if action['action_type'] == 'ANALYZER_ERROR':
               print(f"Failure at: {action['message']}")
               print(f"Stack trace: {action['stack_trace']}")
   ```

3. **The failures are reproducible** because:
   - Same files, same language detection, same AST parsing
   - Run with same repository
   - Failure point will be identical

---

## Monitoring Multiple Analyses

```bash
# Watch for new reports
watch -n 2 'ls -lt /tmp/rim_diagnostics/*.json | head -5'

# Compare two analyses
python -m backend.intelligence.diagnostics.analyzer /tmp/rim_diagnostics/analysis_1_report.json
python -m backend.intelligence.diagnostics.analyzer /tmp/rim_diagnostics/analysis_2_report.json

# Find all failures
grep -l "PROBLEM\|ISSUES\|INCOMPLETE" /tmp/rim_diagnostics/*_report.json
```

---

## Integration with Bug Reports

**When reporting RIM issues, include:**

1. The diagnostic report JSON
   ```bash
   cat /tmp/rim_diagnostics/analysis_X_report.json
   ```

2. The actions log (for specific issues)
   ```bash
   # Extract errors only
   jq 'select(.action_type == "ANALYZER_ERROR")' /tmp/rim_diagnostics/analysis_X_actions.jsonl
   ```

3. The backend logs around the time of analysis
   ```bash
   docker compose logs backend --since 1h | grep -E "CallGraphAnalyzer|ANALYZER|RIM"
   ```

This gives maintainers everything needed to reproduce and fix the issue.

---

## Advanced: Custom Analysis

Write your own analyzer script:

```python
from pathlib import Path
from backend.intelligence.diagnostics import DiagnosticReportAnalyzer

report = DiagnosticReportAnalyzer(Path("/tmp/rim_diagnostics/analysis_2_report.json"))

# Find what went wrong
missing = report.find_missing_relationships()
for rel_type, reasons in missing.items():
    print(f"{rel_type}: {reasons}")

# Show timeline
report.show_action_timeline(analyzer_name="CallGraphAnalyzer")

# Compare with expected
report.compare_relationships({
    "CALLS": 50,
    "USES": 20,
    "RENDERS": 10,
})
```

---

## Summary

| Task | Command |
|------|---------|
| Enable diagnostics | Pass `analysis_id` to `AnalysisEngine.run()` |
| View reports | `ls /tmp/rim_diagnostics/analysis_*_report.json` |
| Analyze report | `python -m backend.intelligence.diagnostics.analyzer <report>` |
| View actions | `cat /tmp/rim_diagnostics/analysis_*_actions.jsonl` |
| Find errors | `jq 'select(.action_type == "ANALYZER_ERROR")' analysis_*_actions.jsonl` |
| Reproduce | Use actions log as exact sequence that failed |
| Monitor | `watch 'ls -lt /tmp/rim_diagnostics/*.json'` |

---

## Next Steps

1. **Rebuild and test** with `docker compose up --build`
2. **Run a RIM comparison** to trigger analysis
3. **Check `/tmp/rim_diagnostics/`** for reports
4. **Analyze with** `python -m backend.intelligence.diagnostics.analyzer`
5. **Share findings** from the diagnostic report

The diagnostic system will pinpoint exactly what's breaking and why.
