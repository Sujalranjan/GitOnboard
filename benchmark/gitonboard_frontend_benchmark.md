# GitOnboard Frontend Benchmark

15 rigorous questions targeting GitOnboard Frontend architecture (Next.js 16 App Router, React 19, useAgentWorkspace SSE reconciliation, Monaco CodeEditorPanel, ApprovalBanner, and VerificationPanel).

> **Evaluation Rule:** Every question specifies concrete `required_evidence`, `expected_symbols`, `expected_answer_points`, and `difficulty` levels (L1–L5). A rigorous agent evaluation must grade answers against these ground-truth expectations.

---

## GF01 — Architecture (L3)
**Question:** How does useAgentWorkspace synchronize agent execution state, implementation plan updates, and terminal events via Server-Sent Events (SSE)? Detail snapshot hydration, reconnect reconciliation, and sequence de-duplication.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 3, Hops: 2, Concepts: 5)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `frontend/hooks/useAgentWorkspace.ts`
- `frontend/components/workspace/AIAgentPanel.tsx`
- `frontend/types/workspace.ts`

**Supporting Evidence:**
- `frontend/components/workspace/WorkspaceLayout.tsx`
- `frontend/components/workspace/ChatPanel.tsx`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/hooks/useTaskStatus.js`

**Expected Symbols:** `useAgentWorkspace, fetchSnapshot, processedEventIds, lastSequence, EventStreamItem, WorkspaceSnapshot`

**Expected Concepts:** `SSE EventSource streaming, snapshot reconciliation on reconnect, processed event set de-duplication, sequence ordering, optimistic UI updates vs authoritative snapshot`

**Expected Tool Capabilities:** `file_read, symbol_lookup, graph_traversal`

**Expected Answer Points:**
1. useAgentWorkspace initializes with an initialRunId and maintains state for snapshot, planHistory, connectionStatus, and activeView.
1. fetchSnapshot executes a GET request to /api/v1/agent/runs/{runId}/workspace to hydrate the authoritative WorkspaceSnapshot including current run state, active plan, and latest events.
1. SSE connection is opened to /api/v1/agent/runs/{runId}/events using EventSource, registering handlers for task_progress, plan_updated, approval_required, and verification_completed.
1. Event de-duplication is enforced using processedEventIds ref (a Set of string event IDs) and lastSequence ref to discard duplicate or out-of-order events.
1. Upon SSE error or reconnect, the hook triggers fetchSnapshot to reconcile any dropped intermediate events against the authoritative backend state.

**Expected Answer Structure:**
- hook initialization and state properties
- authoritative snapshot hydration flow
- SSE streaming and message handler dispatch
- reconnect recovery and event de-duplication mechanism

**Known Traps & Failure Modes:**
- Confusing legacy useTaskStatus.js with the active useAgentWorkspace.ts hook.
- Assuming state is purely streaming without noticing the REST snapshot reconciliation.

---

## GF02 — State Management (L3)
**Question:** How are implementation plans rendered and versioned in the workspace UI? Trace how PlanPanel deduplicates active and historical plans and communicates plan selection to CodeEditorPanel.

- **Category:** `state_management`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 3, Hops: 2, Concepts: 4)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `frontend/components/workspace/PlanPanel.tsx`
- `frontend/components/workspace/CodeEditorPanel.tsx`
- `frontend/types/workspace.ts`

**Supporting Evidence:**
- `frontend/components/workspace/PlanDocumentViewer.tsx`
- `frontend/hooks/useAgentWorkspace.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/workspace/TaskPanel.tsx`

**Expected Symbols:** `PlanPanel, plansMap, ImplementationPlanData, PLAN_TAB_KEY, onOpenPlanInEditor`

**Expected Concepts:** `plan version deduplication, virtual document tab (virtual://plan), version descending sort, read-only structured plan viewer vs Monaco editor, affected file count and risk level computation`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. PlanPanel receives snapshot?.plan (the authoritative active plan) and planHistory from useAgentWorkspace.
1. It deduplicates plans using a Map keyed by plan_id || `v${version}`, ensuring the active plan is always present alongside historical versions.
1. Plans are sorted in descending order by version (allPlans.sort((a, b) => (b.version || 0) - (a.version || 0))).
1. When a user selects a plan version, onOpenPlanInEditor is invoked, which opens a virtual tab in CodeEditorPanel under PLAN_TAB_KEY ('virtual://plan').
1. CodeEditorPanel switches to PlanDocumentViewer when a virtual://plan tab is active, rendering tasks, affected files, risks, and verification gates.

**Expected Answer Structure:**
- plan data ingestion and deduplication in Map
- sorting logic and metadata extraction (risk, tasks, affected files)
- virtual tab routing to CodeEditorPanel
- PlanDocumentViewer rendering

**Known Traps & Failure Modes:**
- Assuming plans are opened as physical files on disk rather than virtual tabs (virtual://plan).

---

## GF03 — Security (L4)
**Question:** How does ApprovalBanner intercept high-risk operations and send approval or rejection decisions back to the backend? Where is this wired in the workspace and what payload is sent?

- **Category:** `security`
- **Answer Type:** `contract_analysis`
- **Difficulty:** `L4` (Files: 3, Hops: 3, Concepts: 5)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `frontend/components/workspace/ApprovalBanner.tsx`
- `frontend/hooks/useAgentWorkspace.ts`
- `frontend/components/workspace/WorkspaceLayout.tsx`

**Supporting Evidence:**
- `frontend/types/workspace.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/workspace/TerminalPanel.tsx`

**Expected Symbols:** `ApprovalBanner, ApprovalRequestItem, approvePlan, rejectPlan, respondToApproval`

**Expected Concepts:** `human-in-the-loop safety gating, risk level highlighting (CRITICAL / HIGH vs LOW), rejection justification capture, fixed floating modal overlay, REST action POST payload`

**Expected Tool Capabilities:** `file_read, symbol_lookup, search_code`

**Expected Answer Points:**
1. ApprovalBanner renders as a fixed floating overlay (z-50) whenever snapshot.approvals contains pending ApprovalRequestItem entries.
1. It displays risk levels, action descriptions, associated CLI commands, and justification reasons.
1. For rejections, an input box captures user reasoning before dispatching to prevent arbitrary rejections without context.
1. The component triggers onApprove(approvalId) or onReject(approvalId, reason) which route through useAgentWorkspace.respondToApproval.
1. The hook issues a POST request to /api/v1/agent/runs/{runId}/approvals/{approvalId} with { approved: boolean, reason: string } to release or abort the agent execution lock.

**Expected Answer Structure:**
- UI trigger condition and floating layout
- rejection reasoning workflow
- hook handler delegation
- backend HTTP API contract and payload schema

**Known Traps & Failure Modes:**
- Assuming approvals only handle plan approval rather than arbitrary runtime commands/actions.
- Missing the optional rejection reason input field toggle.

---

## GF04 — Architecture (L4)
**Question:** How does VerificationPanel present multi-vector verification results (Static AST, Dynamic Tests, Contract Verification, and Judge) and defect evidence to the user? Trace how defects link to code files.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 3, Hops: 2, Concepts: 5)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `frontend/components/workspace/VerificationPanel.tsx`
- `frontend/types/workspace.ts`
- `frontend/components/workspace/WorkspaceLayout.tsx`

**Supporting Evidence:**
- `frontend/services/verificationApi.ts`
- `frontend/hooks/useAgentWorkspace.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/workspace/ChangesPanel.tsx`

**Expected Symbols:** `VerificationPanel, VerificationReport, VerificationVectorResult, DefectItem, onSelectFile`

**Expected Concepts:** `multi-vector verification display, judge pass/fail verdict badge, defect classification (syntax, import, contract, test), file selection callback linking defects to Monaco editor, repair event filtering from latest_events`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. VerificationPanel consumes snapshot.verification containing overall status, judge pass/fail verdict, checks array, and defects list.
1. Checks display individual vector health (Static AST, Dynamic Tests, Contract Invariants, Judge) with duration and execution state.
1. Each DefectItem details severity (CRITICAL, HIGH, MEDIUM, LOW), category, description, and target file_path with line numbers.
1. Clicking a defect triggers onSelectFile(defect.file_path), notifying WorkspaceLayout to open the offending file directly in CodeEditorPanel.
1. The panel also filters latest_events for REPAIR_ and DIAGNOSIS_ prefixes to show the autonomous repair loop's progress in real time.

**Expected Answer Structure:**
- executive summary card and judge verdict
- vector checks grid and execution states
- defect listing and severity categorization
- file click integration with Monaco editor
- repair event timeline integration

**Known Traps & Failure Modes:**
- Assuming verification only checks unit test outcomes without AST and contract invariant vectors.

---

## GF05 — Code Navigation (L3)
**Question:** How does CodeEditorPanel switch between Monaco source view, Monaco diff view, and PlanDocumentViewer? Trace how activeFile, editorMode, and virtual tabs are handled.

- **Category:** `code_navigation`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 2, Hops: 2, Concepts: 4)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `frontend/components/workspace/CodeEditorPanel.tsx`
- `frontend/components/workspace/PlanDocumentViewer.tsx`

**Supporting Evidence:**
- `frontend/services/repositoryApi.ts`
- `frontend/types/workspace.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/CodeDetailsViewer.jsx`

**Expected Symbols:** `CodeEditorPanel, PLAN_TAB_KEY, isPlanDoc, getLanguage, getFileContent`

**Expected Concepts:** `virtual vs physical tab discrimination, Monaco editor language inference by file extension, source vs diff editor toggle, file fetching via repositoryApi, tab closing and active tab switching`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. CodeEditorPanel maintains openTabs and activeFile; if activeFile matches virtual://plan or plan://, isPlanDoc returns true.
1. When isPlanDoc is true, it renders PlanDocumentViewer instead of Monaco Editor, exposing the structured plan breakdown.
1. For physical files, it detects the Monaco language using getLanguage (mapping tsx/ts, py, json, yaml, etc.) and fetches file content via getFileContent.
1. When editorMode is 'diff', it renders Monaco DiffEditor comparing original repository content with proposed changes from runState.rawDiff.
1. When editorMode is 'source', standard Monaco Editor is rendered with saveFileContent capabilities.

**Expected Answer Structure:**
- tab identification and isPlanDoc check
- Monaco language resolution logic
- Monaco Editor vs DiffEditor vs PlanDocumentViewer branching
- remote content fetching and saving

**Known Traps & Failure Modes:**
- Confusing the repository explorer CodeDetailsViewer.jsx with the workspace CodeEditorPanel.tsx.

---

## GF06 — Architecture (L3)
**Question:** How does the frontend handle repository selection, repository routing, and analysis ID context across workspace views? Trace how repository IDs are passed into workspace components.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 3, Hops: 2, Concepts: 4)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `frontend/app/workspace/page.tsx`
- `frontend/components/workspace/WorkspaceLayout.tsx`
- `frontend/hooks/useAgentWorkspace.ts`

**Supporting Evidence:**
- `frontend/components/workspace/HeaderGlobal.tsx`
- `frontend/services/repositoryApi.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/app/repository/[id]/page.tsx`

**Expected Symbols:** `WorkspaceLayout, useAgentWorkspace, HeaderGlobal, repoId, initialRunId`

**Expected Concepts:** `URL search params parsing (repo, run_id), fallback repository defaults, isolation of workspace state per repository ID, global header repository switcher`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. frontend/app/workspace/page.tsx extracts repo and run_id query parameters from useSearchParams().
1. The resolved repoId (or default) is passed to WorkspaceLayout and forwarded to useAgentWorkspace({ repositoryId, initialRunId }).
1. WorkspaceLayout passes repoId to HeaderGlobal, AIAgentPanel, FileExplorerPanel, and CodeEditorPanel.
1. File fetching and API calls in repositoryApi and agent endpoints prefix queries with repoId to prevent cross-repository collision.
1. Switching repositories triggers state reset or redirection, unmounting active SSE streams.

**Expected Answer Structure:**
- searchParams ingestion in page component
- propagation through WorkspaceLayout props
- hook parameterization in useAgentWorkspace
- API request scoping by repository ID

**Known Traps & Failure Modes:**
- Looking at frontend/app/repository/[id]/page.tsx (the static explorer) instead of the agent workspace route.

---

## GF07 — State Management (L2)
**Question:** How does the user start a new chat session in AIAgentPanel, and how does this affect active runs, event subscriptions, and chat message history?

- **Category:** `state_management`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `frontend/components/workspace/AIAgentPanel.tsx`
- `frontend/components/workspace/ChatPanel.tsx`
- `frontend/hooks/useAgentWorkspace.ts`

**Supporting Evidence:**
- `frontend/types/workspace.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/LLMConversationFlow.tsx`

**Expected Symbols:** `AIAgentPanel, newChatKey, setNewChatKey, ChatPanel, newChatTrigger`

**Expected Concepts:** `component remounting via React key property, local chat message history reset, run ID clearing, clean state for new user prompt`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. AIAgentPanel provides a '+' button in its header that increments the newChatKey state variable.
1. newChatKey is passed to ChatPanel as newChatTrigger, forcing local message state reset and clearing input drafts.
1. When a new prompt is submitted, startRun is invoked with the new requirement prompt.
1. startRun creates a fresh agent run via POST /api/v1/agent/runs, updates runId, and points SSE to the new run ID.
1. Previous session events in processedEventIds are reset when a new runId is assigned.

**Expected Answer Structure:**
- UI trigger in AIAgentPanel header
- newChatKey increment and effect on ChatPanel
- startRun invocation and new run lifecycle
- event subscriber reset

**Known Traps & Failure Modes:**
- Confusing LLMConversationFlow.tsx (graph canvas) with ChatPanel.tsx in the workspace.

---

## GF08 — Contract (L4)
**Question:** What is the exact HTTP REST and SSE contract between the frontend useAgentWorkspace hook and the backend agent router? Enumerate all endpoints, methods, and expected payload structures.

- **Category:** `contract`
- **Answer Type:** `contract_analysis`
- **Difficulty:** `L4` (Files: 2, Hops: 3, Concepts: 5)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `frontend/hooks/useAgentWorkspace.ts`
- `backend/routers/agent.py`

**Supporting Evidence:**
- `frontend/types/workspace.ts`
- `backend/schemas/agent.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `backend/routers/repository.py`

**Expected Symbols:** `fetchSnapshot, startRun, approvePlan, rejectPlan, respondToApproval, router`

**Expected Concepts:** `REST CRUD endpoints for agent runs, SSE endpoint (/events), workspace snapshot aggregation (/workspace), plan approval endpoints (/plan/approve, /plan/reject), two-way safety approval endpoint (/approvals/{id})`

**Expected Tool Capabilities:** `file_read, symbol_lookup, search_code`

**Expected Answer Points:**
1. POST /api/v1/agent/runs: starts an agent run with { repository_id, user_prompt, mode }, returns { run_id, task_id, status }.
1. GET /api/v1/agent/runs/{run_id}/workspace: returns complete WorkspaceSnapshot { run, plan, latest_events, approvals, verification, changes }.
1. GET /api/v1/agent/runs/{run_id}/events: Server-Sent Events stream delivering EventStreamItem events formatted as JSON lines.
1. POST /api/v1/agent/runs/{run_id}/plan/approve and /plan/reject: approves or rejects implementation plan with optional feedback.
1. POST /api/v1/agent/runs/{run_id}/approvals/{approval_id}: responds to Phase 9 safety gates with { approved: bool, reason: str }.

**Expected Answer Structure:**
- run initialization endpoint and payload
- workspace snapshot fetch endpoint and schema
- SSE stream connection and event format
- plan lifecycle endpoints (approve/reject)
- safety approval gate response endpoint

**Known Traps & Failure Modes:**
- Assuming the frontend communicates directly with the LLM or worker queue instead of the FastAPI agent router.

---

## GF09 — Architecture (L3)
**Question:** How are agent thought processes, tool calls, and execution steps rendered in ChatPanel? Trace how streaming events are transformed into message bubbles, tool call accordions, and markdown blocks.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 2, Hops: 2, Concepts: 4)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `frontend/components/workspace/ChatPanel.tsx`
- `frontend/types/workspace.ts`

**Supporting Evidence:**
- `frontend/components/workspace/AIAgentPanel.tsx`
- `frontend/hooks/useAgentWorkspace.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/workspace/ChangesPanel.tsx`

**Expected Symbols:** `ChatPanel, ChatMessage, EventStreamItem, renderMessageBubble, formatToolCall`

**Expected Concepts:** `thought/reasoning block folding, tool call argument and output collapsible cards, markdown rendering for assistant messages, streaming progress indicator and auto-scrolling, role differentiation (user vs assistant vs system vs tool)`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. ChatPanel aggregates events from snapshot.latest_events and real-time SSE stream into a unified messages list.
1. Agent thoughts/reasoning are detected from event payloads and rendered in collapsible or dimmed 'Thinking' blocks.
1. Tool invocations (e.g. read_file, search_repo, verify_contract) render as dedicated cards showing tool name, arguments, and execution status.
1. Assistant responses are rendered with Markdown formatting supporting code syntax highlighting.
1. The component automatically scrolls to the newest message on stream updates unless the user has manually scrolled up.

**Expected Answer Structure:**
- event-to-message mapping pipeline
- reasoning / thought presentation
- tool-call card UI structure
- markdown and code block rendering
- auto-scroll behavior

**Known Traps & Failure Modes:**
- Assuming messages are plain strings rather than composite structures with embedded tool call payloads.

---

## GF10 — Architecture (L3)
**Question:** How does the workspace expose live terminal output and interactive terminal commands? Trace InteractiveTerminal and TerminalPanel integration with backend execution processes.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 3, Hops: 2, Concepts: 4)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `frontend/components/workspace/InteractiveTerminal.tsx`
- `frontend/components/workspace/TerminalPanel.tsx`
- `frontend/components/workspace/WorkspaceLayout.tsx`

**Supporting Evidence:**
- `frontend/services/sandboxApi.ts`
- `frontend/hooks/useAgentWorkspace.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/workspace/SidebarNav.tsx`

**Expected Symbols:** `InteractiveTerminal, TerminalPanel, executeCommand, TerminalOutputItem`

**Expected Concepts:** `ANSI escape code handling / monospaced terminal styling, command execution sandbox routing, agent command logging vs user interactive command input, terminal clear and scroll-to-bottom mechanics`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. TerminalPanel provides the outer tabbed container for terminal logs, test runner output, and interactive terminal.
1. InteractiveTerminal provides a command prompt allowing users to run bash/PowerShell commands in the sandbox environment via sandboxApi.executeCommand.
1. Agent execution commands (e.g. running pytest or tree-sitter verification) stream into TerminalPanel via SSE stdout/stderr chunks.
1. Output history maintains timestamps, command exit codes, and standard error highlighting.
1. Terminal input supports command history navigation (Up/Down arrow keys) and clear buffer shortcuts.

**Expected Answer Structure:**
- TerminalPanel tab structure
- InteractiveTerminal execution pathway via sandboxApi
- SSE terminal streaming for agent commands
- terminal UX features (command history, error coloring)

**Known Traps & Failure Modes:**
- Assuming terminal runs locally on client browser rather than invoking backend sandbox execution endpoints.

---

## GF11 — Code Navigation (L2)
**Question:** How does FileExplorerPanel render the file tree of local or cloned repositories, handle file creation/deletion, and link selection to Monaco editor tabs?

- **Category:** `code_navigation`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `frontend/components/workspace/FileExplorerPanel.tsx`
- `frontend/services/repositoryApi.ts`
- `frontend/components/workspace/WorkspaceLayout.tsx`

**Supporting Evidence:**
- `frontend/components/workspace/CodeEditorPanel.tsx`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/FileExplorer.jsx`

**Expected Symbols:** `FileExplorerPanel, FileTreeNode, fetchRepositoryTree, onSelectFile`

**Expected Concepts:** `recursive directory tree rendering, folder expand/collapse state, file extension icons, Monaco editor tab opening on click, virtual plan tab inclusion`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. FileExplorerPanel fetches repository file tree structure using repositoryApi.fetchRepositoryTree(repoId).
1. It renders directories and files recursively with folder expand/collapse state stored in local state sets.
1. File items show language-appropriate icons (TypeScript, Python, JSON, Markdown).
1. Clicking a file invokes onSelectFile(path), causing WorkspaceLayout to add the file to openTabs and set it as activeFile in CodeEditorPanel.
1. It distinguishes between physical files and virtual files (such as virtual://plan).

**Expected Answer Structure:**
- tree data fetching from repositoryApi
- recursive folder rendering and toggle state
- file click event routing to WorkspaceLayout
- Monaco editor tab activation

**Known Traps & Failure Modes:**
- Confusing the repository analysis viewer FileExplorer.jsx with the active workspace FileExplorerPanel.tsx.

---

## GF12 — Architecture (L3)
**Question:** How are repository code changes and proposed git diffs visualized in ChangesPanel? Trace how raw diffs, modified files list, and file reviews are coordinated.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 3, Hops: 2, Concepts: 4)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `frontend/components/workspace/ChangesPanel.tsx`
- `frontend/types/workspace.ts`
- `frontend/components/workspace/WorkspaceLayout.tsx`

**Supporting Evidence:**
- `frontend/components/workspace/CodeEditorPanel.tsx`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/workspace/TaskPanel.tsx`

**Expected Symbols:** `ChangesPanel, WorkspaceChangesData, ModifiedFileItem, onSelectDiffFile`

**Expected Concepts:** `git unified diff parsing, file additions, modifications, and deletions badge indicators, line additions/deletions statistics (+/- count), Monaco diff viewer cross-navigation`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. ChangesPanel receives snapshot.changes or runState.rawDiff containing changed files, additions, and deletions count.
1. It displays a summary header with total files changed, lines added (+), and lines deleted (-).
1. Each file row displays change status (CREATED, MODIFIED, DELETED) and diff line counts.
1. Clicking a changed file invokes onSelectDiffFile(filePath), prompting CodeEditorPanel to switch to Monaco DiffEditor comparing base vs modified content.
1. Allows approving or committing individual file changes or the full change set.

**Expected Answer Structure:**
- diff data ingestion from snapshot
- summary statistics calculation
- file list presentation with modification badges
- Monaco DiffEditor trigger on selection

**Known Traps & Failure Modes:**
- Assuming ChangesPanel computes git diffs client-side rather than consuming backend diff snapshots.

---

## GF13 — Architecture (L3)
**Question:** Trace the component hierarchy and layout arrangement of WorkspaceLayout.tsx. How do collapsible sidebars, resizable panels, and modal overlays interact?

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 3, Hops: 2, Concepts: 5)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `frontend/components/workspace/WorkspaceLayout.tsx`
- `frontend/components/workspace/SidebarNav.tsx`
- `frontend/components/workspace/HeaderGlobal.tsx`

**Supporting Evidence:**
- `frontend/components/workspace/AIAgentPanel.tsx`
- `frontend/components/workspace/CodeEditorPanel.tsx`
- `frontend/components/workspace/ApprovalBanner.tsx`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/layout/Navbar.jsx`

**Expected Symbols:** `WorkspaceLayout, SidebarNav, HeaderGlobal, activeSidebarTab, agentPanelWidth`

**Expected Concepts:** `three-pane IDE layout (left sidebar, center editor/terminal, right agent drawer), SidebarNav tab switching (files, changes, plans, verification), keyboard shortcuts modal toggle, floating safety approval banner overlay`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. WorkspaceLayout coordinates the full IDE workspace with HeaderGlobal at top, SidebarNav on the far left, collapsible left panel (FileExplorer, Changes, Plans, Verification), center work area, and AIAgentPanel on the right.
1. SidebarNav switches activeSidebarTab ('files' | 'changes' | 'plans' | 'verification' | 'terminal'), dynamically mounting the corresponding panel in the left drawer.
1. Center work area splits between CodeEditorPanel (top/center) and TerminalPanel (bottom) with resizable height.
1. Right AIAgentPanel can be resized or collapsed to maximize code editing area.
1. ApprovalBanner renders as an unconstrained floating overlay at the bottom right whenever approvals are pending, independent of panel collapse states.

**Expected Answer Structure:**
- overall grid/flex layout architecture
- left sidebar navigation and panel switching
- center editor and bottom terminal split
- right agent panel toggling and resizing
- floating modal and approval banner layering

**Known Traps & Failure Modes:**
- Confusing legacy Navbar.jsx with HeaderGlobal.tsx in the workspace layout.

---

## GF14 — Debugging (L4)
**Question:** How does the frontend detect and recover from network disconnects, invalid run IDs, or backend 500 errors during an active agent run? Trace error propagation across useAgentWorkspace, AIAgentPanel, and ChatPanel.

- **Category:** `debugging`
- **Answer Type:** `error_diagnosis`
- **Difficulty:** `L4` (Files: 3, Hops: 3, Concepts: 5)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `frontend/hooks/useAgentWorkspace.ts`
- `frontend/components/workspace/AIAgentPanel.tsx`
- `frontend/components/workspace/ChatPanel.tsx`

**Supporting Evidence:**
- `frontend/types/workspace.ts`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/hooks/useTaskStatus.js`

**Expected Symbols:** `useAgentWorkspace, connectionStatus, fetchSnapshot, reconnectTimeoutRef, EventSource`

**Expected Concepts:** `connection status enum ('CONNECTED' | 'RECONNECTING' | 'DISCONNECTED' | 'ERROR'), exponential backoff or reconnect delay, authoritative snapshot re-fetch on reconnect, inline error banner rendering in ChatPanel, graceful fallback when run ID is invalid or 404`

**Expected Tool Capabilities:** `file_read, symbol_lookup`

**Expected Answer Points:**
1. useAgentWorkspace catches fetch failures in fetchSnapshot and sets error state (e.g. 'Failed to load workspace snapshot: Not Found').
1. EventSource.onerror triggers setConnectionStatus('RECONNECTING') and schedules a reconnection attempt via reconnectTimeoutRef after a delay.
1. If the SSE connection fails repeatedly or backend returns 404/500, connectionStatus transitions to 'ERROR' and displays an error alert in AIAgentPanel and ChatPanel.
1. When reconnecting successfully, fetchSnapshot is automatically executed to reconcile state, preventing ghost runs.
1. Users can manually trigger refreshSnapshot() using the History button in AIAgentPanel to force a state recovery.

**Expected Answer Structure:**
- error capture points in fetchSnapshot and EventSource
- connection status state machine transitions
- reconnect scheduling logic in reconnectTimeoutRef
- user-facing error UI in AIAgentPanel and ChatPanel
- manual recovery trigger via refreshSnapshot

**Known Traps & Failure Modes:**
- Assuming EventSource reconnects automatically without needing snapshot state reconciliation.

---

## GF15 — Architecture (L5)
**Question:** Trace the complete end-to-end user journey in GitOnboard from prompt submission in ChatPanel through planning, human approval, code generation, multi-vector verification, and Monaco diff review.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L5` (Files: 7, Hops: 6, Concepts: 6)
- **Repository:** `gitonboard_frontend` (Commit: `9d4de5e77ef9`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `True`

**Required Evidence Files:**
- `frontend/components/workspace/ChatPanel.tsx`
- `frontend/hooks/useAgentWorkspace.ts`
- `frontend/components/workspace/PlanPanel.tsx`
- `frontend/components/workspace/ApprovalBanner.tsx`
- `frontend/components/workspace/VerificationPanel.tsx`
- `frontend/components/workspace/ChangesPanel.tsx`
- `frontend/components/workspace/CodeEditorPanel.tsx`

**Supporting Evidence:**
- `frontend/components/workspace/WorkspaceLayout.tsx`
- `backend/routers/agent.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `frontend/components/ArchitectureExplorer.jsx`

**Expected Symbols:** `useAgentWorkspace, ChatPanel, PlanPanel, ApprovalBanner, VerificationPanel, ChangesPanel, CodeEditorPanel`

**Expected Concepts:** `end-to-end agentic workflow lifecycle, phase transitions: UNDERSTANDING -> PLANNING -> AWAITING_APPROVAL -> EXECUTING -> VERIFYING -> COMPLETED, human-in-the-loop plan and action approval, live SSE event streaming into UI panels, side-by-side Monaco diff inspection and acceptance`

**Expected Tool Capabilities:** `file_read, symbol_lookup, graph_traversal, search_code`

**Expected Answer Points:**
1. User enters an implementation requirement in ChatPanel; startRun initiates POST /api/v1/agent/runs and opens the SSE event stream.
1. The backend agent transitions through UNDERSTANDING to PLANNING, streaming tasks and architecture context; PlanPanel receives the generated plan and opens virtual://plan in CodeEditorPanel.
1. If the plan requires safety clearance or triggers Phase 9 gates, ApprovalBanner pops up; user approves or provides rejection feedback.
1. The agent executes code edits, updating ChangesPanel with modified files and diff statistics (+/- lines).
1. Upon completion, multi-vector verification runs automatically; VerificationPanel displays Static AST, dynamic tests, and contract check results, highlighting defects if any.
1. User opens ChangesPanel or CodeEditorPanel in 'diff' mode to inspect unified Monaco diffs, review evidence, and accept changes.

**Expected Answer Structure:**
- Phase 1: Prompt entry and run initiation in ChatPanel
- Phase 2: Plan generation, PlanPanel inspection, and virtual tab routing
- Phase 3: Human safety gating in ApprovalBanner
- Phase 4: Autonomous code modification and ChangesPanel tracking
- Phase 5: Multi-vector verification and defect presentation in VerificationPanel
- Phase 6: Final Monaco DiffEditor review and acceptance

**Known Traps & Failure Modes:**
- Leaving out the approval gate or verification inspection steps in the lifecycle.
- Treating the workflow as a simple single-turn chatbot interaction instead of a multi-panel workspace.

---
