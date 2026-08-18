const API_BASE = '/api/v1/sandbox';

export interface SandboxSessionResponse {
  session_id: string;
  run_id: string;
  worktree_path: string;
  created_at: number;
  cwd: string;
}

export interface SandboxExecResponse {
  run_id: string;
  command: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  timed_out: boolean;
  output_truncated: boolean;
  duration_ms: number;
  session_id?: string;
  cwd?: string;
}

/**
 * Creates or retrieves a persistent interactive shell session for the given run_id.
 */
export async function createSandboxSession(
  runId: string,
  sessionId?: string
): Promise<SandboxSessionResponse> {
  const safeRunId = encodeURIComponent(runId || 'default');
  const res = await fetch(`${API_BASE}/${safeRunId}/session`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      session_id: sessionId,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Session creation failed with HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Closes an active sandbox session, freeing process and temp resources.
 */
export async function closeSandboxSession(
  runId: string,
  sessionId: string
): Promise<{ status: string; session_id: string; run_id: string }> {
  const safeRunId = encodeURIComponent(runId || 'default');
  const safeSessionId = encodeURIComponent(sessionId);
  const res = await fetch(`${API_BASE}/${safeRunId}/session/${safeSessionId}`, {
    method: 'DELETE',
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Session cleanup failed with HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Executes a CLI command inside the persistent shell session for the given run_id.
 * Preserves directory changes (cd), environment exports (export), and shell state across commands.
 */
export async function execSandboxCommand(
  runId: string,
  command: string,
  timeoutSec: number = 30,
  sessionId?: string
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
      session_id: sessionId,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Sandbox execution failed with HTTP ${res.status}`);
  }

  return res.json();
}

