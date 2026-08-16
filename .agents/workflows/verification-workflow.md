# Verification & Repair Workflow

Standard 8-step workflow executed by AI agents in GitOnBoard:

```text
Understand ──► Locate ──► Trace ──► Plan ──► Modify ──► Validate ──► Review ──► Report
```

1. **Understand**: Deconstruct requirement & generate explicit Implementation Contract.
2. **Locate**: Identify target files using Repository Intelligence Model (RIM) and Fact Store.
3. **Trace**: Calculate Expected Impact Analysis across call graphs and dependencies.
4. **Plan**: Generate step-by-step implementation plan.
5. **Modify**: Apply code generation inside isolated Git worktree.
6. **Validate**: Execute multi-agent verification (Static, Dynamic, Semantic evidence).
7. **Review**: If verification fails, execute repair loop (max 3 iterations).
8. **Report**: Emit structured `VerificationReport` with evidence metrics.
