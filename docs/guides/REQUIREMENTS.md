# GitOnBoard — Core Requirements & Specifications

## 1. Functional Requirements

### FR-1: Repository Intelligence
- Multi-language AST parsing (Python, JavaScript, TypeScript) via Tree-sitter.
- Relational Layer 4 Fact Store persistence in PostgreSQL.
- Repository Intelligence Model (RIM) directed dependency and call graph construction.

### FR-2: Requirement Intelligence
- Requirement decomposition into explicit **Implementation Contract** checklists.
- **Expected Impact Analysis** predicting modified files, components, and symbol relations.

### FR-3: Coding Agent Sandbox Execution
- Execution of coding agents in isolated Git worktrees (`data/worktrees/`).
- Diff extraction (`git diff`), modified file listing, and output log capture.

### FR-4: Adversarial Multi-Agent Verification
- **Requirement Verifier**: Validates Implementation Contract completeness.
- **Code/Test Verifier**: Executes build (`tsc`), linter (`eslint`/`ruff`), and tests (`pytest`).
- **Architecture Verifier**: Detects layer boundary violations.
- **Repository/Impact Verifier**: Compares actual file changes against Expected Impact Analysis.
- **Semantic Verifier**: Evaluates behavioral correctness and edge cases with LLM.
- **Judge / Aggregator**: Emits definitive `VerificationReport`.

### FR-5: Automated Repair Loop
- Structured diagnostic report generation for failing verifications.
- Contextual repair prompts sent to Repair Agent.
- Maximum 3 automated repair iterations.

### FR-6: Evaluation & Benchmarking
- 30 curated evaluation tasks across 6 categories (Auth, CRUD, API, DB, Logic, Architecture).
- Metrics tracking: Requirement Completion Rate, Implementation Error Rate, Repair Success Rate, Latency.
