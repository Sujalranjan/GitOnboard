const API_BASE = '/api/v1/sandbox';

export interface SandboxExecResponse {
  run_id: string;
  command: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  timed_out: boolean;
  output_truncated: boolean;
  duration_ms: number;
}

/**
 * Executes a CLI command inside the isolated worktree sandbox for the given run_id.
 * No client-supplied path is accepted; execution root is resolved server-side.
 */
export async function execSandboxCommand(
  runId: string,
  command: string,
  timeoutSec: number = 30
): Promise<SandboxExecResponse> {
  const safeRunId = encodeURIComponent(runId || 'default');
  const res = await fetch(`${API_BASE}/${safeRunId}/exec`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      command,
      timeout_sec: Math.max(1, Math.min(120, timeoutSec)),
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Sandbox execution failed with HTTP ${res.status}`);
  }

  return res.json();
}
