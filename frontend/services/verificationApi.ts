import {
  DefectItem,
  ImplementationContract,
  VerificationReport,
} from '../types/workspace';

const API_BASE = '/api';

/**
 * Normalizes raw backend VerificationReport response into frontend interface.
 */
function normalizeVerificationReport(raw: any, runId: string): VerificationReport {
  const staticResult = raw.static_result || {};
  const dynamicResult = raw.dynamic_result || {};
  const contractResult = raw.contract_result || {};

  const staticPassed = Boolean(staticResult.passed ?? (staticResult.status === 'PASS'));
  const dynamicPassed = Boolean(dynamicResult.passed ?? (dynamicResult.status === 'PASS'));
  const contractPassed = Boolean(contractResult.passed ?? (contractResult.status === 'PASS'));

  const overallStatus = raw.execution_state || raw.status || (raw.passed ? 'PASS' : 'FAIL');

  const defectsList: DefectItem[] = (raw.defects || []).map((d: any, index: number) => ({
    id: d.id || `defect-${index + 1}`,
    category: d.category || 'DEFECT',
    file_path: d.file_path || '',
    line_number: d.line_number,
    description: d.description || '',
    severity: d.severity || 'HIGH',
    symbol: d.symbol,
    evidence_id: d.evidence_id,
  }));

  return {
    run_id: raw.run_id || runId,
    overall_status: overallStatus,
    status: overallStatus,
    execution_state: raw.execution_state || overallStatus,
    passed: raw.passed ?? (overallStatus === 'PASS'),
    static_passed: staticPassed,
    dynamic_passed: dynamicPassed,
    semantic_passed: contractPassed,
    static_result: staticResult,
    dynamic_result: dynamicResult,
    contract_result: contractResult,
    defects: defectsList,
    evidence_manifest: raw.evidence_manifest || [],
    summary: raw.summary || '',
    created_at: raw.created_at || new Date().toISOString(),
  };
}

/**
 * 1. Creates or requests an ImplementationContract from backend.
 */
export async function createContract(
  repoId: string,
  prompt: string
): Promise<ImplementationContract> {
  const res = await fetch(`${API_BASE}/repos/${encodeURIComponent(repoId)}/implementations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ requirement: prompt }),
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => '');
    throw new Error(`Contract creation failed (${res.status}): ${errorText || 'Backend unavailable'}`);
  }

  const data = await res.json();
  const contractObj = data.contract || {};

  const requiredEndpoints = (contractObj.affected_components || [])
    .filter((c: any) => (c.file || '').includes('api') || (c.file || '').includes('router'))
    .map((c: any) => c.file);

  const expectedComponents = (contractObj.affected_components || []).map((c: any) => c.file || c.symbol || '');

  return {
    id: data.id || `contract-${Date.now()}`,
    requirement: prompt,
    required_endpoints: requiredEndpoints.length > 0 ? requiredEndpoints : [],
    expected_components: expectedComponents.length > 0 ? expectedComponents : [],
    invariants: contractObj.security_considerations || contractObj.invariants || [],
    required_tests: contractObj.tests_required || [],
    affected_components: contractObj.affected_components || [],
    acceptance_criteria: contractObj.acceptance_criteria || [],
    security_considerations: contractObj.security_considerations || [],
  };
}

/**
 * 2. Calls POST /api/v1/verify/run to execute Multi-Vector Verification.
 */
export async function runVerification(
  runId: string,
  repoId: string = 'default',
  worktreePath?: string
): Promise<VerificationReport> {
  const res = await fetch(`${API_BASE}/v1/verify/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      run_id: runId,
      repo_id: repoId,
      worktree_path: worktreePath,
    }),
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => '');
    throw new Error(`Verification failed (${res.status}): ${errorText || 'Backend unavailable'}`);
  }

  const rawReport = await res.json();
  return normalizeVerificationReport(rawReport, runId);
}

/**
 * 3. Calls POST /api/v1/repair/iterate to execute automated repair iteration.
 */
export async function triggerRepair(
  runId: string,
  iteration: number,
  defects: DefectItem[] = [],
  repoId: string = 'default'
): Promise<{ run_id: string; diff: string; report: VerificationReport }> {
  const res = await fetch(`${API_BASE}/v1/repair/iterate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      run_id: runId,
      repo_id: repoId,
      defects,
      iteration,
    }),
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => '');
    throw new Error(`Repair iteration failed (${res.status}): ${errorText || 'Backend unavailable'}`);
  }

  const data = await res.json();
  const rawReport = data.verification_report || { status: 'PASS', passed: true, defects: [] };
  return {
    run_id: runId,
    diff: data.repaired_diff || '',
    report: normalizeVerificationReport(rawReport, runId),
  };
}

/**
 * 4. Calls POST /api/v1/pipeline/task/submit to submit pipeline requirement.
 */
export async function submitPipelineTask(
  repoName: string,
  prompt: string
): Promise<{ task_id: string; contract: ImplementationContract }> {
  const res = await fetch(`${API_BASE}/v1/pipeline/task/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_name: repoName, prompt }),
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => '');
    throw new Error(`Pipeline submission failed (${res.status}): ${errorText || 'Backend unavailable'}`);
  }

  const data = await res.json();
  const rawContract = data.contract || {};
  return {
    task_id: data.task_id || `task-${Date.now()}`,
    contract: {
      id: rawContract.id || `contract-${Date.now()}`,
      requirement: prompt,
      required_endpoints: rawContract.required_endpoints || [],
      expected_components: rawContract.expected_components || [],
      invariants: rawContract.invariants || [],
      required_tests: rawContract.required_tests || [],
      affected_components: rawContract.affected_components || [],
      acceptance_criteria: rawContract.acceptance_criteria || [],
      security_considerations: rawContract.security_considerations || [],
    },
  };
}

/**
 * 5. Calls POST /api/v1/pipeline/task/{task_id}/execute to run agent in sandbox and initiate verification.
 */
export async function executePipelineTask(
  taskId: string,
  repoName: string,
  contractId?: string,
  contractData?: any
): Promise<{ run_id: string; diff: string; report: VerificationReport }> {
  const res = await fetch(`${API_BASE}/v1/pipeline/task/${encodeURIComponent(taskId)}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      repo_name: repoName,
      contract_id: contractId,
      contract_data: contractData,
    }),
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => '');
    throw new Error(`Pipeline execution failed (${res.status}): ${errorText || 'Backend unavailable'}`);
  }

  const data = await res.json();
  return {
    run_id: data.run_id || taskId,
    diff: data.diff || '',
    report: normalizeVerificationReport(data.report || {}, taskId),
  };
}

/**
 * 6. Calls POST /api/v1/pipeline/task/{task_id}/repair to trigger repair iteration.
 */
export async function repairPipelineTask(
  taskId: string,
  repoName: string,
  iteration: number,
  defects: DefectItem[] = [],
  contractData?: any
): Promise<{ run_id: string; diff: string; report: VerificationReport; status: string }> {
  const res = await fetch(`${API_BASE}/v1/pipeline/task/${encodeURIComponent(taskId)}/repair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      repo_name: repoName,
      defects,
      iteration,
      contract_data: contractData,
    }),
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => '');
    throw new Error(`Pipeline repair failed (${res.status}): ${errorText || 'Backend unavailable'}`);
  }

  const data = await res.json();
  return {
    run_id: data.run_id || taskId,
    diff: data.diff || '',
    report: normalizeVerificationReport(data.report || {}, taskId),
    status: data.status || 'VERIFIED',
  };
}
