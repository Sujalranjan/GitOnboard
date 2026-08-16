---
name: contract-generation
description: Operational guide for decomposing user requirements into explicit Implementation Contracts.
---

# Skill: Implementation Contract Generation

Use this skill when converting a high-level user requirement into a verification contract.

## Contract Generation Procedure

1. **Requirement Analysis**:
   - Deconstruct the user prompt into discrete functional requirements, security constraints, database schema updates, API route specs, and test expectations.

2. **Repository Context Grounding**:
   - Query Layer 4 Fact Store for existing models, routes, services, and types related to the requirement.

3. **Contract Checklist Formatting**:
   - Create a granular checklist of explicit verification items.
   - Example for "Password Reset with Expiring Token":
     - `[ ] POST /api/auth/reset-request endpoint`
     - `[ ] Cryptographically secure token generation`
     - `[ ] Reset token expiration timestamp check`
     - `[ ] Token invalidation after usage`
     - `[ ] Password hash update in DB`
     - `[ ] Unit regression tests for token expiry`
