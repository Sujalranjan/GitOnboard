# Phase 8A Investigation — File Index

## Start Here
- **README.md** — Complete overview and methodology
- **reports/PHASE_8A_INVESTIGATION_FINAL_SUMMARY.txt** — Quick 1-page summary

## For Detailed Analysis
- **reports/PHASE_8A_FINAL_REPORT.md** — Comprehensive findings (primary artifact)
- **reports/PHASE_8A_INVESTIGATION_EVIDENCE.md** — Evidence from all three agents

## For Test Results
- **results/PHASE8A10_GROUND_TRUTH_AUDIT.json** — Shows 37.5% fabricated entities
- **results/PHASE8A11_FINAL_RESULTS.json** — Shows 100% retrieval recall
- **results/** — All JSON results from test execution

## For Re-running Tests
- **test_harnesses/run_phase8a9_direct_parser.py** — Parser execution
- **test_harnesses/run_phase8a10_ground_truth_audit.py** — Ground truth audit
- **test_harnesses/run_phase8a11_verified_retrieval_validation.py** — Retrieval test

## For Protocol/Prevention
- **documentation/PHASE_8A11_PROTOCOL.md** — How to avoid bad test data mistakes

## Full Directory Tree
```
investigations/phase_8a/
├── README.md
├── INDEX.md (this file)
│
├── reports/
│   ├── PHASE_8A_FINAL_REPORT.md (comprehensive)
│   ├── PHASE_8A_INVESTIGATION_EVIDENCE.md (detailed)
│   └── PHASE_8A_INVESTIGATION_FINAL_SUMMARY.txt (quick summary)
│
├── results/
│   ├── PHASE8A9_PARSER_INSPECTION_RESULTS.json
│   ├── PHASE8A10_GROUND_TRUTH_AUDIT.json (critical)
│   ├── PHASE8A11_VERIFIED_RETRIEVAL_RESULTS.json
│   ├── PHASE8A11_RETRIEVAL_TEST_RESULTS.json
│   └── PHASE8A11_FINAL_RESULTS.json (critical)
│
├── test_harnesses/
│   ├── run_phase8a9_direct_parser.py
│   ├── run_phase8a10_ground_truth_audit.py
│   └── run_phase8a11_verified_retrieval_validation.py
│
└── documentation/
    └── PHASE_8A11_PROTOCOL.md
```

## Key Files by Purpose

**To understand what went wrong**: `reports/PHASE_8A_INVESTIGATION_FINAL_SUMMARY.txt`

**To see the proof**: `results/PHASE8A10_GROUND_TRUTH_AUDIT.json` + `results/PHASE8A11_FINAL_RESULTS.json`

**To prevent it again**: `documentation/PHASE_8A11_PROTOCOL.md`

**To re-run tests**: `test_harnesses/` directory (Python 3.8+)

**For comprehensive details**: `reports/PHASE_8A_FINAL_REPORT.md`
