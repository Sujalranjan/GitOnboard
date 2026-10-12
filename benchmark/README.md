# Repository Intelligence Benchmark Suite

This directory contains benchmark suites designed to evaluate whether GitOnboard can answer complex repository questions by finding true structural evidence and tracing data flows across files, rather than guessing from filename similarity or generic LLM priors.

## Benchmark Suites

### 1. GitOnboard Benchmarks (Meta-Evaluation of GitOnboard Platform)
Evaluates reasoning about GitOnboard's own architecture, PostgreSQL Fact Store, Azure Blob storage, and AI agent execution:
- [`gitonboard_backend_benchmark.md`](file:///f:/GitOnboard/benchmark/gitonboard_backend_benchmark.md) — 15 backend questions
- [`gitonboard_frontend_benchmark.md`](file:///f:/GitOnboard/benchmark/gitonboard_frontend_benchmark.md) — 15 frontend questions

### 2. DeepGuard Benchmarks (Imported Target Project in PROD)
Evaluates reasoning about the imported **DeepGuard** project (Next.js 15 Frontend + Express Gateway + FastAPI ML Engine with TFLite deepfake detection) stored in Supabase and Azure Blob Storage:
- [`deepguard_backend_benchmark.md`](file:///f:/GitOnboard/benchmark/deepguard_backend_benchmark.md) — 15 backend & ML engine questions
- [`deepguard_frontend_benchmark.md`](file:///f:/GitOnboard/benchmark/deepguard_frontend_benchmark.md) — 15 frontend & dashboard questions

## Evaluation Rules

For every question, the listed files represent the **minimum expected evidence set**. A strong GitOnboard answer should:
1. Discover and cite concrete files, symbols, and routes.
2. Trace the data/control flow through layers.
3. Distinguish confirmed facts from inferences.

### Scoring per question (0–4)
- **4 — Correct and Grounded:** Correct conclusion, correct flow, cited relevant files and symbols, zero hallucinations.
- **3 — Mostly Correct:** Correct conclusion with a minor omission in tracing.
- **2 — Partial:** Identifies some relevant components but misses key relationships.
- **1 — Weak:** Speculative or superficial answer; little concrete evidence.
- **0 — Failed:** Incorrect conclusion, fabricated behavior, or wrong files.
