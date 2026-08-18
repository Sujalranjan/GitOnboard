# Baseline Failure Reproduction Guide

This document provides deterministic reproduction instructions for all known baseline failures and unverified behaviors identified during Phase 0.

---

## 1. Known Baseline Failure Cases

### **FAIL-01: Terminal Simulation Disconnection**
- **Category**: Mock / Simulated UI
- **Affected File**: `frontend/components/workspace/TerminalPanel.tsx:L38-50`
- **Expected Behavior**: Entering a command executes a subprocess inside the isolated worktree sandbox and captures real stdout, stderr, and exit codes.
- **Observed Baseline Behavior**: Command input is intercepted by React state (`handleCommandSubmit`), appending a hardcoded string `Exit code: 0` without communicating with any backend API.
- **Deterministic Reproduction Steps**:
  1. Open the GitOnBoard workspace UI (`http://localhost:3000/workspace`).
  2. In the bottom Terminal panel, ensure the `TERMINAL` sub-tab is selected.
  3. In the input line at the bottom, type `false` and press Enter.
  4. Notice the output:
     ```text
     $ false
     Executing 'false' in isolated repository worktree sandbox...
     Exit code: 0
     ```
  5. Enter `cat nonexistent_file.txt`. Observe that it also outputs `Exit code: 0`.

---

### **FAIL-02: Initial Monaco Editor Azurite Stalling**
- **Category**: React Lifecycle State Bug
- **Affected File**: `frontend/components/workspace/CodeEditorPanel.tsx:L49-99`
- **Expected Behavior**: When no file is selected (`activeFile === ""`), the editor shows an empty state or placeholder prompt without displaying an active loading spinner.
- **Observed Baseline Behavior**: `loadingFile` is initialized to `true`. When `activeFile` is empty, `useEffect` exits early, leaving `loadingFile = true` permanently.
- **Deterministic Reproduction Steps**:
  1. Navigate directly to `/workspace` or `/repository/my-project/workspace`.
  2. Do NOT click any file in the File Explorer tree.
  3. Observe the middle Code Editor panel.
  4. It displays an infinite spinner: *"Streaming blob payload from Azurite Storage..."*.

---

### **FAIL-03: Search Result Navigation Disconnection**
- **Category**: Broken Event Handler
- **Affected File**: `frontend/components/workspace/HeaderGlobal.tsx:L223-236`
- **Expected Behavior**: Clicking a search result opens the containing file in Monaco and jumps to the symbol line number.
- **Observed Baseline Behavior**: Clicking a search result only calls `setShowSearchDropdown(false)`, doing nothing to active editor state.
- **Deterministic Reproduction Steps**:
  1. Focus the search bar in the top navigation header.
  2. Type a known symbol name (e.g., `read_root`).
  3. The dropdown displays the symbol and its file path.
  4. Click on the symbol result in the dropdown.
  5. Observe: The dropdown closes, but the file is not opened and the active editor does not navigate.

---

### **FAIL-04: Model Selector Dropdown Disconnection**
- **Category**: Missing Request Payload Wiring
- **Affected File**: `frontend/components/workspace/AIAgentPanel.tsx:L49-58`
- **Expected Behavior**: Selecting an LLM provider (GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro, Ollama) sends the choice to the backend pipeline.
- **Observed Baseline Behavior**: The selection is stored only in local component state (`selectedModel`) and is discarded when invoking `submitPipelineTask` / `executePipelineTask`.
- **Deterministic Reproduction Steps**:
  1. In the right-hand AI Verification Agent panel, click the Model Selector dropdown.
  2. Select "Claude 3.5 Sonnet".
  3. Type a requirement prompt and click "Dispatch".
  4. Open Browser DevTools → Network tab.
  5. Inspect the payload sent to `POST /api/v1/pipeline/task/submit`.
  6. Observe: The request body contains only `{"repo_name": "...", "prompt": "..."}` without `model`.

---

### **FAIL-05: Unauthenticated Repository API Swallowing**
- **Category**: Error Masking Fallback
- **Affected File**: `frontend/services/repositoryApi.ts:L71-73`
- **Expected Behavior**: Failed file fetches (e.g. 401 Unauthorized, 404 Not Found) alert the user or redirect to login.
- **Observed Baseline Behavior**: The exception is caught and replaced with a dummy comment string.
- **Deterministic Reproduction Steps**:
  1. Clear the `access_token` cookie in the browser.
  2. Select a file in the workspace.
  3. Observe that the editor displays:
     ```typescript
     // Content for path/to/file.py
     ```
     instead of displaying an authentication required prompt.
