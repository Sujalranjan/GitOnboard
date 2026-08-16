---
name: verification-audit
description: Operational guide for executing multi-agent static, dynamic, and semantic code verification in GitOnBoard.
---

# Skill: Verification Audit

Use this skill when performing adversarial verification on AI-generated code modifications.

## Verification Pipeline Stages

1. **Static Evidence Verification**:
   - Parse modified files using Tree-sitter CST parser.
   - Check AST symbol declarations against Repository Intelligence Model (RIM) graph.
   - Compare modified file sets against Expected Impact Analysis.
   - Verify zero architectural boundary violations (e.g. `Controller → DB` bypassing `Service`).

2. **Dynamic Evidence Verification**:
   - Execute build (`tsc` / `npm run build`).
   - Run type checking (`mypy` / `tsc`).
   - Run linters (`ruff` / `eslint`).
   - Run unit and integration tests (`pytest` / `jest`) in isolated Git worktree.

3. **Semantic Evidence Verification**:
   - Compare Implementation Contract checklists against generated code.
   - Verify edge cases, error handling, and business logic with LLM verifier.

4. **Evidence Aggregation & Verdict**:
   - Synthesize evidence into `VerificationReport`.
   - Issue `PASS` if all contract requirements are satisfied with passing tests.
   - Issue `FAIL` with structured defect findings if any contract item or test fails.
