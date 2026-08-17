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
  status: 'PASS' | 'FAIL' | string;
  passed: boolean;
  defects: DefectItem[];
  details?: Record<string, any>;
  execution_time_ms?: number;
}

export interface VerificationReport {
  run_id: string;
  overall_status: 'PENDING' | 'PASS' | 'FAIL' | string;
  status?: 'PASS' | 'FAIL' | string;
  passed?: boolean;
  static_passed: boolean;
  dynamic_passed: boolean;
  semantic_passed: boolean;
  static_result?: VerificationVectorResult;
  dynamic_result?: VerificationVectorResult;
  contract_result?: VerificationVectorResult;
  defects: DefectItem[];
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
}
