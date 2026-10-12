import json
from pathlib import Path

GITONBOARD_COMMIT = "9d4de5e77ef9d4c651acfac9a58a8a81d46d6a6d"

frontend_questions = [
  {
    "id": "GF01",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does useAgentWorkspace synchronize agent execution state, implementation plan updates, and terminal events via Server-Sent Events (SSE)? Detail snapshot hydration, reconnect reconciliation, and sequence de-duplication.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "frontend/hooks/useAgentWorkspace.ts",
      "frontend/components/workspace/AIAgentPanel.tsx",
      "frontend/types/workspace.ts"
    ],
    "supporting_evidence": [
      "frontend/components/workspace/WorkspaceLayout.tsx",
      "frontend/components/workspace/ChatPanel.tsx"
    ],
    "decoy_files": [
      "frontend/hooks/useTaskStatus.js"
    ],
    "expected_symbols": [
      "useAgentWorkspace",
      "fetchSnapshot",
      "processedEventIds",
      "lastSequence",
      "EventStreamItem",
      "WorkspaceSnapshot"
    ],
    "expected_concepts": [
      "SSE EventSource streaming",
      "snapshot reconciliation on reconnect",
      "processed event set de-duplication",
      "sequence ordering",
      "optimistic UI updates vs authoritative snapshot"
    ],
    "expected_answer_points": [
      "useAgentWorkspace initializes with an initialRunId and maintains state for snapshot, planHistory, connectionStatus, and activeView.",
      "fetchSnapshot executes a GET request to /api/v1/agent/runs/{runId}/workspace to hydrate the authoritative WorkspaceSnapshot including current run state, active plan, and latest events.",
      "SSE connection is opened to /api/v1/agent/runs/{runId}/events using EventSource, registering handlers for task_progress, plan_updated, approval_required, and verification_completed.",
      "Event de-duplication is enforced using processedEventIds ref (a Set of string event IDs) and lastSequence ref to discard duplicate or out-of-order events.",
      "Upon SSE error or reconnect, the hook triggers fetchSnapshot to reconcile any dropped intermediate events against the authoritative backend state."
    ],
    "expected_answer_structure": [
      "hook initialization and state properties",
      "authoritative snapshot hydration flow",
      "SSE streaming and message handler dispatch",
      "reconnect recovery and event de-duplication mechanism"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup",
      "graph_traversal"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 3,
      "hops": 2,
      "concepts": 5
    },
    "known_traps": [
      "Confusing legacy useTaskStatus.js with the active useAgentWorkspace.ts hook.",
      "Assuming state is purely streaming without noticing the REST snapshot reconciliation."
    ]
  },
  {
    "id": "GF02",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How are implementation plans rendered and versioned in the workspace UI? Trace how PlanPanel deduplicates active and historical plans and communicates plan selection to CodeEditorPanel.",
    "category": "state_management",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "frontend/components/workspace/PlanPanel.tsx",
      "frontend/components/workspace/CodeEditorPanel.tsx",
      "frontend/types/workspace.ts"
    ],
    "supporting_evidence": [
      "frontend/components/workspace/PlanDocumentViewer.tsx",
      "frontend/hooks/useAgentWorkspace.ts"
    ],
    "decoy_files": [
      "frontend/components/workspace/TaskPanel.tsx"
    ],
    "expected_symbols": [
      "PlanPanel",
      "plansMap",
      "ImplementationPlanData",
      "PLAN_TAB_KEY",
      "onOpenPlanInEditor"
    ],
    "expected_concepts": [
      "plan version deduplication",
      "virtual document tab (virtual://plan)",
      "version descending sort",
      "read-only structured plan viewer vs Monaco editor",
      "affected file count and risk level computation"
    ],
    "expected_answer_points": [
      "PlanPanel receives snapshot?.plan (the authoritative active plan) and planHistory from useAgentWorkspace.",
      "It deduplicates plans using a Map keyed by plan_id || `v${version}`, ensuring the active plan is always present alongside historical versions.",
      "Plans are sorted in descending order by version (allPlans.sort((a, b) => (b.version || 0) - (a.version || 0))).",
      "When a user selects a plan version, onOpenPlanInEditor is invoked, which opens a virtual tab in CodeEditorPanel under PLAN_TAB_KEY ('virtual://plan').",
      "CodeEditorPanel switches to PlanDocumentViewer when a virtual://plan tab is active, rendering tasks, affected files, risks, and verification gates."
    ],
    "expected_answer_structure": [
      "plan data ingestion and deduplication in Map",
      "sorting logic and metadata extraction (risk, tasks, affected files)",
      "virtual tab routing to CodeEditorPanel",
      "PlanDocumentViewer rendering"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 3,
      "hops": 2,
      "concepts": 4
    },
    "known_traps": [
      "Assuming plans are opened as physical files on disk rather than virtual tabs (virtual://plan)."
    ]
  },
  {
    "id": "GF03",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does ApprovalBanner intercept high-risk operations and send approval or rejection decisions back to the backend? Where is this wired in the workspace and what payload is sent?",
    "category": "security",
    "answer_type": "contract_analysis",
    "difficulty": "L4",
    "required_evidence": [
      "frontend/components/workspace/ApprovalBanner.tsx",
      "frontend/hooks/useAgentWorkspace.ts",
      "frontend/components/workspace/WorkspaceLayout.tsx"
    ],
    "supporting_evidence": [
      "frontend/types/workspace.ts"
    ],
    "decoy_files": [
      "frontend/components/workspace/TerminalPanel.tsx"
    ],
    "expected_symbols": [
      "ApprovalBanner",
      "ApprovalRequestItem",
      "approvePlan",
      "rejectPlan",
      "respondToApproval"
    ],
    "expected_concepts": [
      "human-in-the-loop safety gating",
      "risk level highlighting (CRITICAL / HIGH vs LOW)",
      "rejection justification capture",
      "fixed floating modal overlay",
      "REST action POST payload"
    ],
    "expected_answer_points": [
      "ApprovalBanner renders as a fixed floating overlay (z-50) whenever snapshot.approvals contains pending ApprovalRequestItem entries.",
      "It displays risk levels, action descriptions, associated CLI commands, and justification reasons.",
      "For rejections, an input box captures user reasoning before dispatching to prevent arbitrary rejections without context.",
      "The component triggers onApprove(approvalId) or onReject(approvalId, reason) which route through useAgentWorkspace.respondToApproval.",
      "The hook issues a POST request to /api/v1/agent/runs/{runId}/approvals/{approvalId} with { approved: boolean, reason: string } to release or abort the agent execution lock."
    ],
    "expected_answer_structure": [
      "UI trigger condition and floating layout",
      "rejection reasoning workflow",
      "hook handler delegation",
      "backend HTTP API contract and payload schema"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup",
      "search_code"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 3,
      "hops": 3,
      "concepts": 5
    },
    "known_traps": [
      "Assuming approvals only handle plan approval rather than arbitrary runtime commands/actions.",
      "Missing the optional rejection reason input field toggle."
    ]
  },
  {
    "id": "GF04",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does VerificationPanel present multi-vector verification results (Static AST, Dynamic Tests, Contract Verification, and Judge) and defect evidence to the user? Trace how defects link to code files.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L4",
    "required_evidence": [
      "frontend/components/workspace/VerificationPanel.tsx",
      "frontend/types/workspace.ts",
      "frontend/components/workspace/WorkspaceLayout.tsx"
    ],
    "supporting_evidence": [
      "frontend/services/verificationApi.ts",
      "frontend/hooks/useAgentWorkspace.ts"
    ],
    "decoy_files": [
      "frontend/components/workspace/ChangesPanel.tsx"
    ],
    "expected_symbols": [
      "VerificationPanel",
      "VerificationReport",
      "VerificationVectorResult",
      "DefectItem",
      "onSelectFile"
    ],
    "expected_concepts": [
      "multi-vector verification display",
      "judge pass/fail verdict badge",
      "defect classification (syntax, import, contract, test)",
      "file selection callback linking defects to Monaco editor",
      "repair event filtering from latest_events"
    ],
    "expected_answer_points": [
      "VerificationPanel consumes snapshot.verification containing overall status, judge pass/fail verdict, checks array, and defects list.",
      "Checks display individual vector health (Static AST, Dynamic Tests, Contract Invariants, Judge) with duration and execution state.",
      "Each DefectItem details severity (CRITICAL, HIGH, MEDIUM, LOW), category, description, and target file_path with line numbers.",
      "Clicking a defect triggers onSelectFile(defect.file_path), notifying WorkspaceLayout to open the offending file directly in CodeEditorPanel.",
      "The panel also filters latest_events for REPAIR_ and DIAGNOSIS_ prefixes to show the autonomous repair loop's progress in real time."
    ],
    "expected_answer_structure": [
      "executive summary card and judge verdict",
      "vector checks grid and execution states",
      "defect listing and severity categorization",
      "file click integration with Monaco editor",
      "repair event timeline integration"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 3,
      "hops": 2,
      "concepts": 5
    },
    "known_traps": [
      "Assuming verification only checks unit test outcomes without AST and contract invariant vectors."
    ]
  },
  {
    "id": "GF05",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does CodeEditorPanel switch between Monaco source view, Monaco diff view, and PlanDocumentViewer? Trace how activeFile, editorMode, and virtual tabs are handled.",
    "category": "code_navigation",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "frontend/components/workspace/CodeEditorPanel.tsx",
      "frontend/components/workspace/PlanDocumentViewer.tsx"
    ],
    "supporting_evidence": [
      "frontend/services/repositoryApi.ts",
      "frontend/types/workspace.ts"
    ],
    "decoy_files": [
      "frontend/components/CodeDetailsViewer.jsx"
    ],
    "expected_symbols": [
      "CodeEditorPanel",
      "PLAN_TAB_KEY",
      "isPlanDoc",
      "getLanguage",
      "getFileContent"
    ],
    "expected_concepts": [
      "virtual vs physical tab discrimination",
      "Monaco editor language inference by file extension",
      "source vs diff editor toggle",
      "file fetching via repositoryApi",
      "tab closing and active tab switching"
    ],
    "expected_answer_points": [
      "CodeEditorPanel maintains openTabs and activeFile; if activeFile matches virtual://plan or plan://, isPlanDoc returns true.",
      "When isPlanDoc is true, it renders PlanDocumentViewer instead of Monaco Editor, exposing the structured plan breakdown.",
      "For physical files, it detects the Monaco language using getLanguage (mapping tsx/ts, py, json, yaml, etc.) and fetches file content via getFileContent.",
      "When editorMode is 'diff', it renders Monaco DiffEditor comparing original repository content with proposed changes from runState.rawDiff.",
      "When editorMode is 'source', standard Monaco Editor is rendered with saveFileContent capabilities."
    ],
    "expected_answer_structure": [
      "tab identification and isPlanDoc check",
      "Monaco language resolution logic",
      "Monaco Editor vs DiffEditor vs PlanDocumentViewer branching",
      "remote content fetching and saving"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 2,
      "hops": 2,
      "concepts": 4
    },
    "known_traps": [
      "Confusing the repository explorer CodeDetailsViewer.jsx with the workspace CodeEditorPanel.tsx."
    ]
  },
  {
    "id": "GF06",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does the frontend handle repository selection, repository routing, and analysis ID context across workspace views? Trace how repository IDs are passed into workspace components.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "frontend/app/workspace/page.tsx",
      "frontend/components/workspace/WorkspaceLayout.tsx",
      "frontend/hooks/useAgentWorkspace.ts"
    ],
    "supporting_evidence": [
      "frontend/components/workspace/HeaderGlobal.tsx",
      "frontend/services/repositoryApi.ts"
    ],
    "decoy_files": [
      "frontend/app/repository/[id]/page.tsx"
    ],
    "expected_symbols": [
      "WorkspaceLayout",
      "useAgentWorkspace",
      "HeaderGlobal",
      "repoId",
      "initialRunId"
    ],
    "expected_concepts": [
      "URL search params parsing (repo, run_id)",
      "fallback repository defaults",
      "isolation of workspace state per repository ID",
      "global header repository switcher"
    ],
    "expected_answer_points": [
      "frontend/app/workspace/page.tsx extracts repo and run_id query parameters from useSearchParams().",
      "The resolved repoId (or default) is passed to WorkspaceLayout and forwarded to useAgentWorkspace({ repositoryId, initialRunId }).",
      "WorkspaceLayout passes repoId to HeaderGlobal, AIAgentPanel, FileExplorerPanel, and CodeEditorPanel.",
      "File fetching and API calls in repositoryApi and agent endpoints prefix queries with repoId to prevent cross-repository collision.",
      "Switching repositories triggers state reset or redirection, unmounting active SSE streams."
    ],
    "expected_answer_structure": [
      "searchParams ingestion in page component",
      "propagation through WorkspaceLayout props",
      "hook parameterization in useAgentWorkspace",
      "API request scoping by repository ID"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 3,
      "hops": 2,
      "concepts": 4
    },
    "known_traps": [
      "Looking at frontend/app/repository/[id]/page.tsx (the static explorer) instead of the agent workspace route."
    ]
  },
  {
    "id": "GF07",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does the user start a new chat session in AIAgentPanel, and how does this affect active runs, event subscriptions, and chat message history?",
    "category": "state_management",
    "answer_type": "execution_trace",
    "difficulty": "L2",
    "required_evidence": [
      "frontend/components/workspace/AIAgentPanel.tsx",
      "frontend/components/workspace/ChatPanel.tsx",
      "frontend/hooks/useAgentWorkspace.ts"
    ],
    "supporting_evidence": [
      "frontend/types/workspace.ts"
    ],
    "decoy_files": [
      "frontend/components/LLMConversationFlow.tsx"
    ],
    "expected_symbols": [
      "AIAgentPanel",
      "newChatKey",
      "setNewChatKey",
      "ChatPanel",
      "newChatTrigger"
    ],
    "expected_concepts": [
      "component remounting via React key property",
      "local chat message history reset",
      "run ID clearing",
      "clean state for new user prompt"
    ],
    "expected_answer_points": [
      "AIAgentPanel provides a '+' button in its header that increments the newChatKey state variable.",
      "newChatKey is passed to ChatPanel as newChatTrigger, forcing local message state reset and clearing input drafts.",
      "When a new prompt is submitted, startRun is invoked with the new requirement prompt.",
      "startRun creates a fresh agent run via POST /api/v1/agent/runs, updates runId, and points SSE to the new run ID.",
      "Previous session events in processedEventIds are reset when a new runId is assigned."
    ],
    "expected_answer_structure": [
      "UI trigger in AIAgentPanel header",
      "newChatKey increment and effect on ChatPanel",
      "startRun invocation and new run lifecycle",
      "event subscriber reset"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 3,
      "hops": 2,
      "concepts": 3
    },
    "known_traps": [
      "Confusing LLMConversationFlow.tsx (graph canvas) with ChatPanel.tsx in the workspace."
    ]
  },
  {
    "id": "GF08",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "What is the exact HTTP REST and SSE contract between the frontend useAgentWorkspace hook and the backend agent router? Enumerate all endpoints, methods, and expected payload structures.",
    "category": "contract",
    "answer_type": "contract_analysis",
    "difficulty": "L4",
    "required_evidence": [
      "frontend/hooks/useAgentWorkspace.ts",
      "backend/routers/agent.py"
    ],
    "supporting_evidence": [
      "frontend/types/workspace.ts",
      "backend/schemas/agent.py"
    ],
    "decoy_files": [
      "backend/routers/repository.py"
    ],
    "expected_symbols": [
      "fetchSnapshot",
      "startRun",
      "approvePlan",
      "rejectPlan",
      "respondToApproval",
      "router"
    ],
    "expected_concepts": [
      "REST CRUD endpoints for agent runs",
      "SSE endpoint (/events)",
      "workspace snapshot aggregation (/workspace)",
      "plan approval endpoints (/plan/approve, /plan/reject)",
      "two-way safety approval endpoint (/approvals/{id})"
    ],
    "expected_answer_points": [
      "POST /api/v1/agent/runs: starts an agent run with { repository_id, user_prompt, mode }, returns { run_id, task_id, status }.",
      "GET /api/v1/agent/runs/{run_id}/workspace: returns complete WorkspaceSnapshot { run, plan, latest_events, approvals, verification, changes }.",
      "GET /api/v1/agent/runs/{run_id}/events: Server-Sent Events stream delivering EventStreamItem events formatted as JSON lines.",
      "POST /api/v1/agent/runs/{run_id}/plan/approve and /plan/reject: approves or rejects implementation plan with optional feedback.",
      "POST /api/v1/agent/runs/{run_id}/approvals/{approval_id}: responds to Phase 9 safety gates with { approved: bool, reason: str }."
    ],
    "expected_answer_structure": [
      "run initialization endpoint and payload",
      "workspace snapshot fetch endpoint and schema",
      "SSE stream connection and event format",
      "plan lifecycle endpoints (approve/reject)",
      "safety approval gate response endpoint"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup",
      "search_code"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 2,
      "hops": 3,
      "concepts": 5
    },
    "known_traps": [
      "Assuming the frontend communicates directly with the LLM or worker queue instead of the FastAPI agent router."
    ]
  },
  {
    "id": "GF09",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How are agent thought processes, tool calls, and execution steps rendered in ChatPanel? Trace how streaming events are transformed into message bubbles, tool call accordions, and markdown blocks.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "frontend/components/workspace/ChatPanel.tsx",
      "frontend/types/workspace.ts"
    ],
    "supporting_evidence": [
      "frontend/components/workspace/AIAgentPanel.tsx",
      "frontend/hooks/useAgentWorkspace.ts"
    ],
    "decoy_files": [
      "frontend/components/workspace/ChangesPanel.tsx"
    ],
    "expected_symbols": [
      "ChatPanel",
      "ChatMessage",
      "EventStreamItem",
      "renderMessageBubble",
      "formatToolCall"
    ],
    "expected_concepts": [
      "thought/reasoning block folding",
      "tool call argument and output collapsible cards",
      "markdown rendering for assistant messages",
      "streaming progress indicator and auto-scrolling",
      "role differentiation (user vs assistant vs system vs tool)"
    ],
    "expected_answer_points": [
      "ChatPanel aggregates events from snapshot.latest_events and real-time SSE stream into a unified messages list.",
      "Agent thoughts/reasoning are detected from event payloads and rendered in collapsible or dimmed 'Thinking' blocks.",
      "Tool invocations (e.g. read_file, search_repo, verify_contract) render as dedicated cards showing tool name, arguments, and execution status.",
      "Assistant responses are rendered with Markdown formatting supporting code syntax highlighting.",
      "The component automatically scrolls to the newest message on stream updates unless the user has manually scrolled up."
    ],
    "expected_answer_structure": [
      "event-to-message mapping pipeline",
      "reasoning / thought presentation",
      "tool-call card UI structure",
      "markdown and code block rendering",
      "auto-scroll behavior"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 2,
      "hops": 2,
      "concepts": 4
    },
    "known_traps": [
      "Assuming messages are plain strings rather than composite structures with embedded tool call payloads."
    ]
  },
  {
    "id": "GF10",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does the workspace expose live terminal output and interactive terminal commands? Trace InteractiveTerminal and TerminalPanel integration with backend execution processes.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "frontend/components/workspace/InteractiveTerminal.tsx",
      "frontend/components/workspace/TerminalPanel.tsx",
      "frontend/components/workspace/WorkspaceLayout.tsx"
    ],
    "supporting_evidence": [
      "frontend/services/sandboxApi.ts",
      "frontend/hooks/useAgentWorkspace.ts"
    ],
    "decoy_files": [
      "frontend/components/workspace/SidebarNav.tsx"
    ],
    "expected_symbols": [
      "InteractiveTerminal",
      "TerminalPanel",
      "executeCommand",
      "TerminalOutputItem"
    ],
    "expected_concepts": [
      "ANSI escape code handling / monospaced terminal styling",
      "command execution sandbox routing",
      "agent command logging vs user interactive command input",
      "terminal clear and scroll-to-bottom mechanics"
    ],
    "expected_answer_points": [
      "TerminalPanel provides the outer tabbed container for terminal logs, test runner output, and interactive terminal.",
      "InteractiveTerminal provides a command prompt allowing users to run bash/PowerShell commands in the sandbox environment via sandboxApi.executeCommand.",
      "Agent execution commands (e.g. running pytest or tree-sitter verification) stream into TerminalPanel via SSE stdout/stderr chunks.",
      "Output history maintains timestamps, command exit codes, and standard error highlighting.",
      "Terminal input supports command history navigation (Up/Down arrow keys) and clear buffer shortcuts."
    ],
    "expected_answer_structure": [
      "TerminalPanel tab structure",
      "InteractiveTerminal execution pathway via sandboxApi",
      "SSE terminal streaming for agent commands",
      "terminal UX features (command history, error coloring)"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 3,
      "hops": 2,
      "concepts": 4
    },
    "known_traps": [
      "Assuming terminal runs locally on client browser rather than invoking backend sandbox execution endpoints."
    ]
  },
  {
    "id": "GF11",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does FileExplorerPanel render the file tree of local or cloned repositories, handle file creation/deletion, and link selection to Monaco editor tabs?",
    "category": "code_navigation",
    "answer_type": "execution_trace",
    "difficulty": "L2",
    "required_evidence": [
      "frontend/components/workspace/FileExplorerPanel.tsx",
      "frontend/services/repositoryApi.ts",
      "frontend/components/workspace/WorkspaceLayout.tsx"
    ],
    "supporting_evidence": [
      "frontend/components/workspace/CodeEditorPanel.tsx"
    ],
    "decoy_files": [
      "frontend/components/FileExplorer.jsx"
    ],
    "expected_symbols": [
      "FileExplorerPanel",
      "FileTreeNode",
      "fetchRepositoryTree",
      "onSelectFile"
    ],
    "expected_concepts": [
      "recursive directory tree rendering",
      "folder expand/collapse state",
      "file extension icons",
      "Monaco editor tab opening on click",
      "virtual plan tab inclusion"
    ],
    "expected_answer_points": [
      "FileExplorerPanel fetches repository file tree structure using repositoryApi.fetchRepositoryTree(repoId).",
      "It renders directories and files recursively with folder expand/collapse state stored in local state sets.",
      "File items show language-appropriate icons (TypeScript, Python, JSON, Markdown).",
      "Clicking a file invokes onSelectFile(path), causing WorkspaceLayout to add the file to openTabs and set it as activeFile in CodeEditorPanel.",
      "It distinguishes between physical files and virtual files (such as virtual://plan)."
    ],
    "expected_answer_structure": [
      "tree data fetching from repositoryApi",
      "recursive folder rendering and toggle state",
      "file click event routing to WorkspaceLayout",
      "Monaco editor tab activation"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 3,
      "hops": 2,
      "concepts": 3
    },
    "known_traps": [
      "Confusing the repository analysis viewer FileExplorer.jsx with the active workspace FileExplorerPanel.tsx."
    ]
  },
  {
    "id": "GF12",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How are repository code changes and proposed git diffs visualized in ChangesPanel? Trace how raw diffs, modified files list, and file reviews are coordinated.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "frontend/components/workspace/ChangesPanel.tsx",
      "frontend/types/workspace.ts",
      "frontend/components/workspace/WorkspaceLayout.tsx"
    ],
    "supporting_evidence": [
      "frontend/components/workspace/CodeEditorPanel.tsx"
    ],
    "decoy_files": [
      "frontend/components/workspace/TaskPanel.tsx"
    ],
    "expected_symbols": [
      "ChangesPanel",
      "WorkspaceChangesData",
      "ModifiedFileItem",
      "onSelectDiffFile"
    ],
    "expected_concepts": [
      "git unified diff parsing",
      "file additions, modifications, and deletions badge indicators",
      "line additions/deletions statistics (+/- count)",
      "Monaco diff viewer cross-navigation"
    ],
    "expected_answer_points": [
      "ChangesPanel receives snapshot.changes or runState.rawDiff containing changed files, additions, and deletions count.",
      "It displays a summary header with total files changed, lines added (+), and lines deleted (-).",
      "Each file row displays change status (CREATED, MODIFIED, DELETED) and diff line counts.",
      "Clicking a changed file invokes onSelectDiffFile(filePath), prompting CodeEditorPanel to switch to Monaco DiffEditor comparing base vs modified content.",
      "Allows approving or committing individual file changes or the full change set."
    ],
    "expected_answer_structure": [
      "diff data ingestion from snapshot",
      "summary statistics calculation",
      "file list presentation with modification badges",
      "Monaco DiffEditor trigger on selection"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 3,
      "hops": 2,
      "concepts": 4
    },
    "known_traps": [
      "Assuming ChangesPanel computes git diffs client-side rather than consuming backend diff snapshots."
    ]
  },
  {
    "id": "GF13",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "Trace the component hierarchy and layout arrangement of WorkspaceLayout.tsx. How do collapsible sidebars, resizable panels, and modal overlays interact?",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L3",
    "required_evidence": [
      "frontend/components/workspace/WorkspaceLayout.tsx",
      "frontend/components/workspace/SidebarNav.tsx",
      "frontend/components/workspace/HeaderGlobal.tsx"
    ],
    "supporting_evidence": [
      "frontend/components/workspace/AIAgentPanel.tsx",
      "frontend/components/workspace/CodeEditorPanel.tsx",
      "frontend/components/workspace/ApprovalBanner.tsx"
    ],
    "decoy_files": [
      "frontend/components/layout/Navbar.jsx"
    ],
    "expected_symbols": [
      "WorkspaceLayout",
      "SidebarNav",
      "HeaderGlobal",
      "activeSidebarTab",
      "agentPanelWidth"
    ],
    "expected_concepts": [
      "three-pane IDE layout (left sidebar, center editor/terminal, right agent drawer)",
      "SidebarNav tab switching (files, changes, plans, verification)",
      "keyboard shortcuts modal toggle",
      "floating safety approval banner overlay"
    ],
    "expected_answer_points": [
      "WorkspaceLayout coordinates the full IDE workspace with HeaderGlobal at top, SidebarNav on the far left, collapsible left panel (FileExplorer, Changes, Plans, Verification), center work area, and AIAgentPanel on the right.",
      "SidebarNav switches activeSidebarTab ('files' | 'changes' | 'plans' | 'verification' | 'terminal'), dynamically mounting the corresponding panel in the left drawer.",
      "Center work area splits between CodeEditorPanel (top/center) and TerminalPanel (bottom) with resizable height.",
      "Right AIAgentPanel can be resized or collapsed to maximize code editing area.",
      "ApprovalBanner renders as an unconstrained floating overlay at the bottom right whenever approvals are pending, independent of panel collapse states."
    ],
    "expected_answer_structure": [
      "overall grid/flex layout architecture",
      "left sidebar navigation and panel switching",
      "center editor and bottom terminal split",
      "right agent panel toggling and resizing",
      "floating modal and approval banner layering"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": False,
    "difficulty_factors": {
      "files": 3,
      "hops": 2,
      "concepts": 5
    },
    "known_traps": [
      "Confusing legacy Navbar.jsx with HeaderGlobal.tsx in the workspace layout."
    ]
  },
  {
    "id": "GF14",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "How does the frontend detect and recover from network disconnects, invalid run IDs, or backend 500 errors during an active agent run? Trace error propagation across useAgentWorkspace, AIAgentPanel, and ChatPanel.",
    "category": "debugging",
    "answer_type": "error_diagnosis",
    "difficulty": "L4",
    "required_evidence": [
      "frontend/hooks/useAgentWorkspace.ts",
      "frontend/components/workspace/AIAgentPanel.tsx",
      "frontend/components/workspace/ChatPanel.tsx"
    ],
    "supporting_evidence": [
      "frontend/types/workspace.ts"
    ],
    "decoy_files": [
      "frontend/hooks/useTaskStatus.js"
    ],
    "expected_symbols": [
      "useAgentWorkspace",
      "connectionStatus",
      "fetchSnapshot",
      "reconnectTimeoutRef",
      "EventSource"
    ],
    "expected_concepts": [
      "connection status enum ('CONNECTED' | 'RECONNECTING' | 'DISCONNECTED' | 'ERROR')",
      "exponential backoff or reconnect delay",
      "authoritative snapshot re-fetch on reconnect",
      "inline error banner rendering in ChatPanel",
      "graceful fallback when run ID is invalid or 404"
    ],
    "expected_answer_points": [
      "useAgentWorkspace catches fetch failures in fetchSnapshot and sets error state (e.g. 'Failed to load workspace snapshot: Not Found').",
      "EventSource.onerror triggers setConnectionStatus('RECONNECTING') and schedules a reconnection attempt via reconnectTimeoutRef after a delay.",
      "If the SSE connection fails repeatedly or backend returns 404/500, connectionStatus transitions to 'ERROR' and displays an error alert in AIAgentPanel and ChatPanel.",
      "When reconnecting successfully, fetchSnapshot is automatically executed to reconcile state, preventing ghost runs.",
      "Users can manually trigger refreshSnapshot() using the History button in AIAgentPanel to force a state recovery."
    ],
    "expected_answer_structure": [
      "error capture points in fetchSnapshot and EventSource",
      "connection status state machine transitions",
      "reconnect scheduling logic in reconnectTimeoutRef",
      "user-facing error UI in AIAgentPanel and ChatPanel",
      "manual recovery trigger via refreshSnapshot"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": False,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 3,
      "hops": 3,
      "concepts": 5
    },
    "known_traps": [
      "Assuming EventSource reconnects automatically without needing snapshot state reconciliation."
    ]
  },
  {
    "id": "GF15",
    "repository": "gitonboard_frontend",
    "repository_commit": GITONBOARD_COMMIT,
    "question": "Trace the complete end-to-end user journey in GitOnboard from prompt submission in ChatPanel through planning, human approval, code generation, multi-vector verification, and Monaco diff review.",
    "category": "architecture",
    "answer_type": "execution_trace",
    "difficulty": "L5",
    "required_evidence": [
      "frontend/components/workspace/ChatPanel.tsx",
      "frontend/hooks/useAgentWorkspace.ts",
      "frontend/components/workspace/PlanPanel.tsx",
      "frontend/components/workspace/ApprovalBanner.tsx",
      "frontend/components/workspace/VerificationPanel.tsx",
      "frontend/components/workspace/ChangesPanel.tsx",
      "frontend/components/workspace/CodeEditorPanel.tsx"
    ],
    "supporting_evidence": [
      "frontend/components/workspace/WorkspaceLayout.tsx",
      "backend/routers/agent.py"
    ],
    "decoy_files": [
      "frontend/components/ArchitectureExplorer.jsx"
    ],
    "expected_symbols": [
      "useAgentWorkspace",
      "ChatPanel",
      "PlanPanel",
      "ApprovalBanner",
      "VerificationPanel",
      "ChangesPanel",
      "CodeEditorPanel"
    ],
    "expected_concepts": [
      "end-to-end agentic workflow lifecycle",
      "phase transitions: UNDERSTANDING -> PLANNING -> AWAITING_APPROVAL -> EXECUTING -> VERIFYING -> COMPLETED",
      "human-in-the-loop plan and action approval",
      "live SSE event streaming into UI panels",
      "side-by-side Monaco diff inspection and acceptance"
    ],
    "expected_answer_points": [
      "User enters an implementation requirement in ChatPanel; startRun initiates POST /api/v1/agent/runs and opens the SSE event stream.",
      "The backend agent transitions through UNDERSTANDING to PLANNING, streaming tasks and architecture context; PlanPanel receives the generated plan and opens virtual://plan in CodeEditorPanel.",
      "If the plan requires safety clearance or triggers Phase 9 gates, ApprovalBanner pops up; user approves or provides rejection feedback.",
      "The agent executes code edits, updating ChangesPanel with modified files and diff statistics (+/- lines).",
      "Upon completion, multi-vector verification runs automatically; VerificationPanel displays Static AST, dynamic tests, and contract check results, highlighting defects if any.",
      "User opens ChangesPanel or CodeEditorPanel in 'diff' mode to inspect unified Monaco diffs, review evidence, and accept changes."
    ],
    "expected_answer_structure": [
      "Phase 1: Prompt entry and run initiation in ChatPanel",
      "Phase 2: Plan generation, PlanPanel inspection, and virtual tab routing",
      "Phase 3: Human safety gating in ApprovalBanner",
      "Phase 4: Autonomous code modification and ChangesPanel tracking",
      "Phase 5: Multi-vector verification and defect presentation in VerificationPanel",
      "Phase 6: Final Monaco DiffEditor review and acceptance"
    ],
    "expected_tool_capabilities": [
      "file_read",
      "symbol_lookup",
      "graph_traversal",
      "search_code"
    ],
    "requires_multi_hop": True,
    "requires_graph_reasoning": True,
    "requires_verification": True,
    "difficulty_factors": {
      "files": 7,
      "hops": 6,
      "concepts": 6
    },
    "known_traps": [
      "Leaving out the approval gate or verification inspection steps in the lifecycle.",
      "Treating the workflow as a simple single-turn chatbot interaction instead of a multi-panel workspace."
    ]
  }
]

out_path = Path("benchmark/gitonboard_frontend_benchmark.json")
out_path.write_text(json.dumps(frontend_questions, indent=2), encoding="utf-8")
print(f"Successfully generated {out_path} with {len(frontend_questions)} questions")
