# Contract: Self-Repair Loop

**Status**: `PLANNED (Future Pipeline Stage)`

> [!NOTE]
> This document specifies the target contract for the planned **Phase 7: Self-Repair Loop**. It is NOT yet implemented in runtime code.

## 1. Purpose
Defines the self-repair loop that activates when the Verification Engine detects test failures, syntax errors, or lint violations in generated code.

## 2. Planned Repair Loop Flow

```text
Verification Failure ──► Diagnostic Analyzer ──► Patch Adjustment ──► Re-Verification (Max 3 Attempts)
```

1. **Diagnostic Analysis**:
   - Ingests the `VerificationReport` containing error logs, stack traces, and failed assertions.
2. **Targeted Patch Generation**:
   - Identifies the specific failure cause (e.g., missing import, type mismatch, broken assertion) and generates a corrective patch.
3. **Iteration Guard**:
   - Limits repair attempts to a maximum of 3 cycles to prevent infinite loops.
4. **Escalation**:
   - If repair fails after maximum iterations, marks the job as `Failed` with diagnostic logs.
