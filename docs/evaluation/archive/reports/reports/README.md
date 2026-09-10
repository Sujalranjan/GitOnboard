# Repository Intelligence Platform — Audit Reports Index

This directory contains the complete, evidence-based architectural audit of the Repository Intelligence Platform.

> **Audit Date:** 2026-07-16  
> **Audited Commit State:** July 15, 2026  
> **Analyst:** Automated static analysis + LLM synthesis  

---

## ⚠️ Start Here

Read the reports in the following order for maximum clarity:

| # | Report | Purpose |
|---|--------|---------|
| 0 | [00-coverage-report.md](./00-coverage-report.md) | What was analyzed and what was skipped |
| 1 | [00-executive-summary.md](./00-executive-summary.md) | High-level findings, critical risks |
| 2 | [01-project-architecture.md](./01-project-architecture.md) | Complete low-level architecture |
| 3 | [02-runtime-flow.md](./02-runtime-flow.md) | Application startup and request lifecycle |
| 4 | [03-module-dependency-graph.md](./03-module-dependency-graph.md) | Module and package dependencies |
| 5 | [04-function-call-graph.md](./04-function-call-graph.md) | Critical function call chains |
| 6 | [05-function-analysis.md](./05-function-analysis.md) | Per-function analysis |
| 7 | [06-dead-code-report.md](./06-dead-code-report.md) | Unused files, classes, functions |
| 8 | [07-wiring-validation.md](./07-wiring-validation.md) | DI, routing, middleware wiring |
| 9 | [08-frontend-backend-integration.md](./08-frontend-backend-integration.md) | Integration health |
| 10 | [09-api-mapping.md](./09-api-mapping.md) | Every API endpoint mapped to frontend |
| 11 | [10-feature-traceability.md](./10-feature-traceability.md) | End-to-end feature flows |
| 12 | [11-configuration-audit.md](./11-configuration-audit.md) | Env vars, config files |
| 13 | [12-architectural-smells.md](./12-architectural-smells.md) | Anti-patterns and smells |
| 14 | [13-risk-assessment.md](./13-risk-assessment.md) | Ranked risk register |
| 15 | [14-refactoring-roadmap.md](./14-refactoring-roadmap.md) | Prioritized refactoring plan |

---

## Diagrams

Mermaid diagrams are in [`diagrams/`](./diagrams/):

- [architecture.mmd](./diagrams/architecture.mmd) — High-level system architecture
- [dependency-graph.mmd](./diagrams/dependency-graph.mmd) — Module dependency graph
- [call-graph.mmd](./diagrams/call-graph.mmd) — Critical call graph paths
- [runtime-flow.mmd](./diagrams/runtime-flow.mmd) — Application startup sequence
- [frontend-backend-flow.mmd](./diagrams/frontend-backend-flow.mmd) — Frontend↔Backend data flow

---

## Audit Log

See [audit.log](./audit.log) for a record of analysis phases and coverage statistics.
