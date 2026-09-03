# GitOnBoard — Evaluation Plan & Benchmark Specifications

## 1. Evaluation Methodology

The evaluation measures whether GitOnBoard's multi-agent verification and automated repair layer improves the software implementation quality of an unassisted baseline coding agent.

```text
Baseline Evaluation:
Requirement ──► Baseline Agent ──► Generated Code ──► Evaluation Metrics

GitOnBoard Evaluation:
Requirement ──► Baseline Agent ──► Verification ──► Repair Loop ──► Verified Code ──► Evaluation Metrics
```

---

## 2. Benchmark Task Suite (30 Tasks)

The benchmark consists of 30 curated coding tasks distributed across 6 domain categories:

1. **Authentication (5 Tasks)**: OAuth linking, password reset expiration, JWT refresh, session invalidation, MFA hook.
2. **CRUD Operations (5 Tasks)**: Pagination, input payload validation, soft delete, cascade updates, filtering.
3. **API Changes (5 Tasks)**: REST versioning, response wrapping, rate limiting headers, endpoint deprecation, file upload.
4. **Database Changes (5 Tasks)**: Schema migration, composite indexes, foreign key constraints, transactional isolation, soft deletion models.
5. **Business Logic (5 Tasks)**: Pricing calculation, state machine transition, event dispatch, discount rules, task queueing.
6. **Architecture-Sensitive (5 Tasks)**: Service layer decoupling, dependency inversion, event listener isolation, repository pattern enforcement, middleware pipeline.

---

## 3. Core Evaluation Metrics

1. **Requirement Completion Rate (%)**: Percentage of contract items satisfied.
2. **Implementation Error Rate (%)**: Percentage of tasks exhibiting taxonomy errors.
3. **Defect Detection Precision & Recall**: Accuracy of verifier defect reports.
4. **Repair Success Rate (%)**: Percentage of failing initial attempts successfully repaired.
5. **First-Pass vs Post-Repair Success Rate**: Delta between raw agent output and repaired output.
6. **Verification Latency**: Time spent in analysis, verification, and repair loops.

---

## 4. Flagship Demonstrations

- **Flagship Demo 1**: *Password Reset Token Expiration Omission*. Unassisted agent generates reset logic omitting token expiration check. GitOnBoard detects omission via Semantic Verifier and automatically repairs it.
- **Flagship Demo 2**: *Architecture Violation*. Agent modifies `Controller → Database` directly. GitOnBoard Architecture Verifier catches violation and repair loop reroutes through `Service` layer.
