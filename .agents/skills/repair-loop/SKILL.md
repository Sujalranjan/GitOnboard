---
name: repair-loop
description: Operational guide for executing the automated defect diagnosis and 3-pass repair loop.
---

# Skill: Automated Repair Loop

Use this skill when a VerificationReport returns `FAIL`.

## Repair Loop Procedure

1. **Defect Diagnosis**:
   - Extract failing test names, stack traces, AST syntax errors, or unsatisfied contract items from `VerificationReport`.

2. **Targeted Repair Prompt Construction**:
   - Provide the repair agent with:
     - Original user requirement & Implementation Contract.
     - Specific failure findings & stack traces.
     - Diff patch generated in previous attempt.

3. **Isolated Worktree Patch Application**:
   - Apply patch in temporary Git worktree (`data/worktrees/`).

4. **Iteration Limit Guard**:
   - Increment repair iteration counter.
   - Enforce a maximum of **3 repair attempts**.
   - If iteration > 3 and verifier still fails, mark status as `UNRESOLVED` and output defect diagnostic summary.
