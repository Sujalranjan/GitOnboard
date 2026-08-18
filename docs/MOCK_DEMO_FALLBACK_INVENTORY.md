# Mock, Demo, and Fallback Inventory

This inventory documents all known mocks, stubs, simulated interfaces, hard-coded responses, and fallback mechanisms identified across the GitOnBoard repository.

---

## 1. Inventory Table

| ID | Location | Type | Purpose | Affects Production? | Covered by Tests? | Target Action / Phase |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **MOCK-01** | `frontend/components/workspace/TerminalPanel.tsx:L38-50` | **UI Simulation / Mock Shell** | Simulates terminal command execution by appending `Exit code: 0` to React state without running a subprocess or backend PTY. | **YES** (Users cannot run real shell commands) | **NO** | Replace with real sandbox execution route (`POST /api/v1/sandbox/{run_id}/exec`) in Phase 2. |
| **MOCK-02** | `frontend/components/workspace/CodeEditorPanel.tsx` | **State Loading Lock** | `loadingFile` initialized to `true` stalled indefinitely if `activeFile` was empty `""`. | **NO** (RESOLVED in Phase 1) | **YES** (`tests/test_phase1_file_loading.py`) | **RESOLVED (Phase 1)**: Initialized `loadingFile=false`, added empty workspace state, and auto-selected first valid file. |
| **MOCK-03** | `frontend/components/workspace/AIAgentPanel.tsx:L49-58` | **Disconnected UI Controls** | Model selector dropdown (GPT-4o, Claude 3.5, Gemini 1.5, Ollama) sets local React state but is omitted from pipeline API request bodies. | **YES** (Backend ignores selected model) | **NO** | Pass `model` parameter in `SubmitTaskRequest` / `ExecuteTaskRequest` in Phase 2. |
| **MOCK-04** | `backend/verification/orchestrator.py:L491-496` | **Dummy Test Generator** | Plants `def test_verification_pass(): assert True` into `tests/test_implementation.py` during repair if test is missing. | **YES** (Produces false-positive dynamic test pass) | **YES** (Codified in baseline) | Remove dummy test generator; require real assertion matching in Phase 2. |
| **MOCK-05** | `frontend/services/repositoryApi.ts` | **Silent Error Fallback** | Returned `// Content for ${filePath}\n` on HTTP 401/404/500 instead of surfacing error to user. | **NO** (RESOLVED in Phase 1) | **YES** (`tests/test_phase1_file_loading.py`) | **RESOLVED (Phase 1)**: Removed placeholder string; throws explicit typed errors (401, 404, 403, 500). |
| **MOCK-06** | `backend/verification/orchestrator.py:_fallback_contract` | **Fallback Contract Generator** | Generates keyword-based contract when LLM provider is unreachable. | **YES** (Allows offline development & testing) | **YES** | Retain as legitimate fallback, but tag report with `MOCKED` or `UNVERIFIED` if LLM is offline. |
| **MOCK-07** | `frontend/components/workspace/HeaderGlobal.tsx:L276-278` | **Hardcoded Profile Avatar** | Renders static initial "V" and fake green online status dot. | **NO** (Cosmetic only) | **NO** | Connect to `current_user.username` in Phase 2. |
| **MOCK-08** | `frontend/components/workspace/HeaderGlobal.tsx:L259-272` | **Cosmetic Action Buttons** | "Invite", "Settings", and "Notifications" buttons have no event handlers or API endpoints. | **NO** (Cosmetic only) | **NO** | Implement modals/handlers or disable in Phase 2. |
| **MOCK-09** | `frontend/hooks/useVerificationWorkspace.ts:L24` | **Hardcoded Initial Prompt** | Default task prompt string: `"Add a new API route for managing user todos with GET and POST handlers."` | **NO** (Default placeholder text) | **NO** | Keep as demo helper or clear to empty string. |
| **MOCK-10** | `backend/routers/repo/structure.py:L181-185` | **GitHub Fallback on Storage Miss** | Falls back to GitHub API `fetch_file_content` if blob is absent in Azurite. | **YES** (Provides graceful fallback) | **YES** | Retain as valid secondary fallback. |

---

## 2. Risk Assessment & Policy

1. **Evidence-Based Rule**: Items **MOCK-01** (Fake terminal exit code) and **MOCK-04** (Dummy `assert True` test) represent risk of false confidence. Phase 0 explicitly guards against **MOCK-04** by rejecting `PASS` status if no verified evidence items are attached.
2. **Freeze Constraint**: None of these items are deleted in Phase 0; all are codified and monitored.
