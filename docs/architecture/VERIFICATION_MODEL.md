# GitOnBoard — Multi-Agent Verification & Evidence Model

## 1. Multi-Evidence Categories

Verification aggregates 3 independent evidence categories:

### A. Static Evidence
- AST syntax validity via Tree-sitter.
- Symbol import & caller graph resolution via RIM.
- Architectural rule checks (e.g. `Controller → Service → Repository`).
- Expected Impact delta analysis.

### B. Dynamic Evidence
- Compilation (`tsc` / `next build`).
- Type checking (`mypy` / `tsc`).
- Unit and integration test suite execution (`pytest`).
- Execution log and stack trace extraction.

### C. Semantic Evidence
- LLM-based contract item mapping.
- Requirement completeness audit.
- Business logic & edge case analysis.

---

## 2. Verifier Agent Roles & Verdict Matrix

| Role | Verification Focus | Evidence Category |
| :--- | :--- | :--- |
| **Requirement Verifier** | Implementation Contract checklist satisfaction | Semantic + Static |
| **Code/Test Verifier** | Compilation, type checks, linting, tests | Dynamic |
| **Architecture Verifier** | System boundary & layer rule adherence | Static (RIM Graph) |
| **Impact Verifier** | Actual changes vs Expected Impact Analysis | Static |
| **Semantic Verifier** | Edge-case logic & behavioral correctness | Semantic |
| **Judge / Aggregator** | Weighted verdict synthesis (`PASS` / `FAIL`) | All |

---

## 3. Verification Result Schema

```json
{
  "status": "FAIL",
  "contract_status": {
    "reset_endpoint": true,
    "token_generation": true,
    "token_expiry_check": false
  },
  "static_evidence": "PASS",
  "dynamic_evidence": "PASS",
  "architecture_evidence": "PASS",
  "semantic_evidence": "FAIL",
  "findings": [
    {
      "severity": "HIGH",
      "category": "Requirement Hallucination",
      "description": "Token expiration timestamp is not checked during password reset validation.",
      "recommended_repair": "Add expiration check in token validation logic."
    }
  ]
}
```
