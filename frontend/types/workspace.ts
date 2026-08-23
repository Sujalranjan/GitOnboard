export type DefectCategory =
  | 'PACKAGE_HALLUCINATION'
  | 'SYMBOL_NOT_FOUND'
  | 'CONTRACT_OMISSION'
  | 'TEST_FAILURE'
  | 'ARCH_VIOLATION'
  | 'STATIC_SYMBOL_MISSING'
  | 'STATIC_IMPORT_MISSING'
  | 'DYNAMIC_TEST_FAILURE'
  | 'DYNAMIC_BUILD_FAILURE'
  | 'DYNAMIC_LINT_FAILURE'
  | 'CONTRACT_INVARIANT_VIOLATION'
  | 'ARCHITECTURE_ERROR';

export type DefectSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export type ExecutionState = 'PASS' | 'FAIL' | 'ERROR' | 'UNVERIFIED' | 'MOCKED';

export interface DefectItem {
  id: string;
  category: DefectCategory | string;
  file_path: string;
  line_number?: number;
  description: string;
  severity?: DefectSeverity | string;
  symbol?: string;
  evidence_id?: string;
}

export interface VerificationVectorResult {
  vector_name: string;
  status: ExecutionState | string;
  passed: boolean;
  execution_state?: ExecutionState | string;
  defects: DefectItem[];
  evidence_manifest?: Record<string, any>[];
  details?: Record<string, any>;
  execution_time_ms?: number;
}

export interface VerificationReport {
  run_id: string;
  overall_status: 'PENDING' | ExecutionState | string;
  status?: ExecutionState | string;
  passed?: boolean;
  execution_state?: ExecutionState | string;
  static_passed: boolean;
  dynamic_passed: boolean;
  semantic_passed: boolean;
  static_result?: VerificationVectorResult;
  dynamic_result?: VerificationVectorResult;
  contract_result?: VerificationVectorResult;
  defects: DefectItem[];
  evidence_manifest?: Record<string, any>[];
  summary?: string;
  created_at: string;
}

export interface AffectedComponentItem {
  file: string;
  symbol?: string;
  component_type?: 'EXISTING' | 'NEW' | string;
  evidence_ids?: string[];
}

export interface ImplementationContract {
  id: string;
  requirement: string;
  required_endpoints: string[];
  expected_components: string[];
  invariants: string[];
  required_tests: string[];
  affected_components?: AffectedComponentItem[];
  acceptance_criteria?: any[];
  evidence_manifest?: any[];
  security_considerations?: string[];
}

export interface RunState {
  runId: string | null;
  repoId: string;
  branch: string;
  taskPrompt: string;
  contract: ImplementationContract | null;
  rawDiff: string;
  report: VerificationReport | null;
  iteration: number;
  isLoading: boolean;
  statusMessage?: string;
  currentState?: AgentState | string;
  startedAt?: string;
  currentActivity?: string;
}

export type AgentState =
  | 'IDLE'
  | 'UNDERSTANDING'
  | 'PLANNING'
  | 'AWAITING_APPROVAL'
  | 'EXECUTING'
  | 'VERIFYING'
  | 'DIAGNOSING'
  | 'REPAIRING'
  | 'BLOCKED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface AgentStateTransitionRecord {
  from_state: AgentState | string;
  to_state: AgentState | string;
  reason?: string;
  timestamp: string;
}

export interface AgentRunRecord {
  id: string;
  task_id: string;
  repository_id?: string;
  user_requirement?: string;
  current_state: AgentState | string;
  status: string;
  started_at: string;
  completed_at?: string;
  cancellation_reason?: string;
  error_message?: string;
  transitions?: AgentStateTransitionRecord[];
}

export interface PlanTaskItem {
  task_id: string;
  step_number: number;
  title: string;
  description: string;
  affected_files: string[];
  acceptance_criteria: string[];
  dependencies: string[];
  verification_strategy: string;
  status: string;
  assigned_to?: string;
  error_message?: string;
}

export interface ImplementationPlanData {
  plan_id: string;
  version: number;
  status: string;
  requirement?: string;
  acceptance_criteria?: string[];
  architecture_context?: Record<string, any>;
  repository_understanding?: Record<string, any>;
  risks?: string[];
  tasks: PlanTaskItem[];
  validation?: {
    valid: boolean;
    errors: string[];
    warnings: string[];
  };
}

export interface ApprovalRequestItem {
  id: string;
  agent_run_id: string;
  task_id?: string;
  action_type: string;
  action_description: string;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  command?: string;
  reason?: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'CANCELLED' | string;
  requested_at: string;
  resolved_at?: string;
  resolved_by?: string;
  rejection_reason?: string;
}

export interface EventStreamItem {
  event_id: string;
  sequence: number;
  agent_run_id: string;
  task_id?: string;
  event_type: string;
  message: string;
  payload: Record<string, any>;
  created_at: string;
  timestamp?: string;
}

export interface WorkspaceChangesData {
  agent_run_id: string;
  worktree_path?: string;
  modified_files: string[];
  added_files: string[];
  deleted_files: string[];
  diff: string;
}

export interface WorkspaceSnapshot {
  run: AgentRunRecord & {
    transitions?: AgentStateTransitionRecord[];
    events?: EventStreamItem[];
    metadata?: Record<string, any>;
  };
  plan?: ImplementationPlanData | null;
  tasks: PlanTaskItem[];
  active_task?: PlanTaskItem | null;
  changes: WorkspaceChangesData;
  verification?: Record<string, any> | null;
  pending_approvals: ApprovalRequestItem[];
  latest_events: EventStreamItem[];
}

export type AgentWorkspaceView = 'chat' | 'plan' | 'tasks' | 'changes' | 'verify';

export type ConnectionStatus = 'CONNECTED' | 'RECONNECTING' | 'DISCONNECTED';


