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

export interface TerminalResetResponse {
  status: string;
  run_id: string;
  session_id: string;
  cwd: string;
}

/**
 * Terminates the run's interactive PTY shell and starts a fresh one in the
 * same worktree. Callers should close their existing terminal websocket and
 * open a new one afterward.
 */
export async function resetSandboxTerminal(runId: string): Promise<TerminalResetResponse> {
  const safeRunId = encodeURIComponent(runId || 'default');
  const res = await fetch(`${API_BASE}/${safeRunId}/terminal/reset`, {
    method: 'POST',
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Terminal reset failed with HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Builds the websocket URL for the interactive PTY terminal stream.
 *
 * Next.js's `rewrites()` proxy (next.config.ts) only forwards plain HTTP
 * requests to the backend, not the WebSocket upgrade handshake, so in local
 * dev (frontend on :3000, backend on :8000) this connects straight to the
 * backend's origin using the browser's own hostname. Anywhere else (a single
 * origin behind a reverse proxy in front of both), it stays same-origin and
 * relies on that proxy to forward the upgrade, mirroring the LOCAL_FRONTEND_URL
 * vs PROD_FRONTEND_URL split already used elsewhere in this project.
 */
export function getSandboxTerminalWsUrl(runId: string): string {
  const safeRunId = encodeURIComponent(runId || 'default');
  if (typeof window === 'undefined') return '';

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';

  // Check explicit environment overrides if present
  if (process.env.NEXT_PUBLIC_BACKEND_WS_URL) {
    const base = process.env.NEXT_PUBLIC_BACKEND_WS_URL.replace(/\/+$/, '');
    return `${base}/${safeRunId}/terminal`;
  }
  if (process.env.NEXT_PUBLIC_API_URL) {
    try {
      const parsed = new URL(process.env.NEXT_PUBLIC_API_URL);
      const wsProtocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${wsProtocol}//${parsed.host}${API_BASE}/${safeRunId}/terminal`;
    } catch {
      // ignore
    }
  }

  // In local dev, frontend runs on 3000, 3001, etc. while backend runs on :8000
  const isDevHost =
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname === '0.0.0.0';
  const isSeparateDevPort = window.location.port !== '8000';

  const host = isDevHost && isSeparateDevPort
    ? `${window.location.hostname}:8000`
    : window.location.host;

  return `${protocol}://${host}${API_BASE}/${safeRunId}/terminal`;
}


