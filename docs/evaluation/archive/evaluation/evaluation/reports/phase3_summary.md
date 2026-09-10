# Phase 3 — Hallucination Baseline Report
## 1. Executive Summary
- **Writer Model**: `ollama / qwen2.5-coder:7b`
- **Benchmark Corpus**: 15 Repositories (50 Curated Ground-Truth Facts)
- **Total Extracted Claims**: **143**
- **Evaluable Claims**: **99** (69.2% of total)
- **Writer Hallucination Rate (Overall)**: **3.5%**
- **Conditional Hallucination Rate (Evaluable Only)**: **5.05%**
- **Validator Leakage Rate**: **0.0%** (Hard Safety Barrier: **0% Leaked**)
- **Refined False Rejection Rate**: **29.63%** (Supported + Correctly Evidenced Claims Rejected)

## 2. Writer Claim Distribution
| Metric | Count | Percentage of Total | Percentage of Evaluable |
| :--- | :--- | :--- | :--- |
| **Total Claims** | 143 | 100.0% | — |
| **Evaluable Claims** | 99 | 69.2% | 100.0% |
| **Supported Claims** | 94 | 65.7% | 94.9% |
| **Unsupported Claims** | 5 | 3.5% | 5.1% |
| **Contradicted Claims** | 0 | 0.0% | 0.0% |
| **Unresolved Claims** | 44 | 30.8% | — |

## 3. Content Hallucination Taxonomy
| Hallucination Category | Occurrences | Definition |
| :--- | :--- | :--- |
| `FABRICATED_PATH` | 2 | Invented directories / mount paths absent from snapshot |
| `FABRICATED_FILE` | 0 | Invented file names absent from filesystem snapshot |
| `FABRICATED_SYMBOL` | 0 | Invented functions, classes, or variables absent from AST |
| `FALSE_CONTRADICTION` | 2 | Invented doc vs code discrepancies without evidence |
| `INCORRECT_TECHNOLOGY` | 1 | Asserted frameworks/databases not in manifests/imports |

## 4. Citation Quality Metrics (Reported Separately)
| Citation Metric | Count | Percentage |
| :--- | :--- | :--- |
| **Total Citations Generated** | 142 | 100.0% |
| **Valid & Entailed Citations** | 58 | 40.85% |
| **Invalid Citation IDs** | 1 | 0.7% |
| **Unentailed Citations (Existing ID, wrong snippet)** | 83 | 58.5% |
| **Citation Entailment Rate** | — | **41.13%** |

## 5. Deterministic Validator Performance (Safety Barrier & Refined False Rejection)
| Safety Metric | Value | Description |
| :--- | :--- | :--- |
| **Invalid Claims Before Validation** | 5 | Unsupported + Contradicted assertions by Writer |
| **Invalid Claims Rejected by Validator** | 4 | Blocked by deterministic rules |
| **Invalid Claims Leaked to Final Summary** | **0** | Reached published summary (Target: 0) |
| **Validator Leakage Rate** | **0.0%** | Hard safety barrier maintained |
| **Supported + Correctly Evidenced Claims** | 54 | True facts with valid & entailed citations |
| **Supported + Correctly Evidenced Rejected** | 16 | Correct claims improperly blocked by validator |
| **Refined False Rejection Rate** | **29.63%** | True false rejection rate under provenance rules |

## 6. Per-Repository Results
| Repository | Total | Evaluable | Supported | Unsupported | Contradicted | Cond. Hallucination % | Invalid | Leaked | Leakage % | False Rej % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `01_minimal_python_cli` | 6 | 5 | 5 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 0.0% |
| `02_fastapi_backend` | 14 | 8 | 7 | 1 | 0 | 12.5% | 1 | 0 | 0.0% | 0.0% |
| `03_flask_monolith` | 11 | 8 | 8 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 100.0% |
| `04_express_api` | 10 | 7 | 6 | 1 | 0 | 14.29% | 1 | 0 | 0.0% | 0.0% |
| `05_django_rest` | 10 | 7 | 6 | 1 | 0 | 14.29% | 1 | 0 | 0.0% | 66.67% |
| `06_go_microservice` | 11 | 5 | 4 | 1 | 0 | 20.0% | 1 | 0 | 0.0% | 0.0% |
| `07_nextjs_frontend` | 8 | 6 | 6 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 66.67% |
| `08_rust_cli_utility` | 7 | 5 | 5 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 0.0% |
| `09_java_spring_boot` | 9 | 6 | 6 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 100.0% |
| `10_python_data_pipeline` | 9 | 6 | 6 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 25.0% |
| `11_ruby_rails_app` | 8 | 6 | 6 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 0.0% |
| `12_multiservice_monorepo` | 13 | 12 | 12 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 25.0% |
| `13_legacy_php_portal` | 8 | 4 | 4 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 0.0% |
| `14_serverless_functions` | 7 | 5 | 5 | 0 | 0 | 0.0% | 0 | 0 | 0.0% | 75.0% |
| `15_fullstack_ai_agent` | 12 | 9 | 8 | 1 | 0 | 11.11% | 1 | 0 | 0.0% | 0.0% |

## 7. Representative Real Examples from Benchmark
### Example 1: Fabricated Path
- **Repository**: `02_fastapi_backend`
- **Claim**: `Deployable unit 'admin_panel' exists at root path '/services/admin_dashboard'.`
- **Evidence**: Path `/services/admin_dashboard` absent from filesystem snapshot.
- **Classification**: `UNSUPPORTED` (`FABRICATED_PATH`)
- **Validator Decision**: `REJECT` (Reason: `Path '/services/admin_dashboard' does not exist in repository snapshot.`)
- **Final Summary Status**: `Absent` (0% Leakage)

### Example 2: False Contradiction
- **Repository**: `04_express_api`
- **Claim**: `Documentation claims 'GraphQL API', but actual code exhibits 'REST endpoints only'.`
- **Evidence**: No ground-truth discrepancy computed by `ClaimVerifier`.
- **Classification**: `UNSUPPORTED` (`FALSE_CONTRADICTION`)
- **Validator Decision**: `REJECT` (Reason: `No authoritative CONTRADICTED claim found in repository evidence.`)
- **Final Summary Status**: `Absent` (0% Leakage)

### Example 3: Invalid Citation (Reported Under Citation Quality)
- **Repository**: `03_flask_monolith`
- **Claim**: `The project uses Flask (Framework).` with citation `['ev_9999_invalid']`
- **Citation Evaluation**: `INVALID_ID` (`ev_9999_invalid` not in index).
- **Content Support Status**: `SUPPORTED` (Core fact is established in requirements.txt).
- **Validator Decision**: Sanitized invalid evidence ID while preserving verified core fact.

