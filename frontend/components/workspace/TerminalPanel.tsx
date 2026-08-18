"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Terminal as TerminalIcon,
  AlertCircle,
  Play,
  Square,
  Columns,
  Trash2,
  Plus,
  ChevronDown,
  X,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { RunState } from "@/types/workspace";
import {
  execSandboxCommand,
  createSandboxSession,
  closeSandboxSession,
  SandboxExecResponse,
} from "@/services/sandboxApi";

interface TerminalPanelProps {
  isOpen: boolean;
  onClose: () => void;
  runState?: RunState;
  height?: number;
}

interface TerminalEntry {
  command: string;
  stdout: string;
  stderr: string;
  exitCode: number;
  timedOut?: boolean;
  outputTruncated?: boolean;
  durationMs?: number;
  cwd?: string;
  error?: string;
}

export function TerminalPanel({ isOpen, onClose, runState, height = 224 }: TerminalPanelProps) {
  const [activeTab, setActiveTab] = useState<"TERMINAL" | "VERIFICATION" | "PROBLEMS">("TERMINAL");
  const [selectedShell, setSelectedShell] = useState("bash (persistent sandbox)");
  const [commandInput, setCommandInput] = useState("");
  const [isExecuting, setIsExecuting] = useState(false);
  const [terminalEntries, setTerminalEntries] = useState<TerminalEntry[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentCwd, setCurrentCwd] = useState<string>("");

  const terminalEndRef = useRef<HTMLDivElement>(null);

  const report = runState?.report;
  const dynamicDetails = report?.dynamic_result?.details || {};
  const defects = report?.defects || [];

  const activeRunId = runState?.runId || runState?.repoId || "default";

  // Initialize or connect to persistent session
  useEffect(() => {
    let isMounted = true;
    async function initSession() {
      try {
        const session = await createSandboxSession(activeRunId);
        if (isMounted) {
          setSessionId(session.session_id);
          setCurrentCwd(session.cwd || "");
        }
      } catch (e) {
        console.warn("Failed to initialize sandbox session:", e);
      }
    }
    if (isOpen) {
      initSession();
    }
    return () => {
      isMounted = false;
    };
  }, [isOpen, activeRunId]);

  // Scroll to bottom when new terminal entries arrive
  useEffect(() => {
    if (activeTab === "TERMINAL" && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [terminalEntries, activeTab]);

  if (!isOpen) return null;

  const handleRestartSession = async () => {
    setIsExecuting(true);
    try {
      if (sessionId) {
        await closeSandboxSession(activeRunId, sessionId).catch(() => {});
      }
      const newSession = await createSandboxSession(activeRunId);
      setSessionId(newSession.session_id);
      setCurrentCwd(newSession.cwd || "");
      setTerminalEntries((prev) => [
        ...prev,
        {
          command: "# Session restarted",
          stdout: `[Shell session reset in worktree: ${newSession.worktree_path}]`,
          stderr: "",
          exitCode: 0,
        },
      ]);
    } catch (err: any) {
      console.error("Failed to restart session:", err);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleCommandSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!commandInput.trim() || isExecuting) return;

    const cmd = commandInput.trim();
    setCommandInput("");
    setIsExecuting(true);

    try {
      const res = await execSandboxCommand(activeRunId, cmd, 30, sessionId || undefined);
      if (res.session_id) {
        setSessionId(res.session_id);
      }
      if (res.cwd) {
        setCurrentCwd(res.cwd);
      }
      setTerminalEntries((prev) => [
        ...prev,
        {
          command: cmd,
          stdout: res.stdout,
          stderr: res.stderr,
          exitCode: res.exit_code,
          timedOut: res.timed_out,
          outputTruncated: res.output_truncated,
          durationMs: res.duration_ms,
          cwd: res.cwd,
        },
      ]);
    } catch (err: any) {
      setTerminalEntries((prev) => [
        ...prev,
        {
          command: cmd,
          stdout: "",
          stderr: err?.message || "Execution error occurred",
          exitCode: 1,
          error: err?.message || "Failed to communicate with sandbox service",
        },
      ]);
    } finally {
      setIsExecuting(false);
    }
  };

  // Helper to format short display path
  const formatShortCwd = (fullPath: string) => {
    if (!fullPath) return "";
    const normalized = fullPath.replace(/\\/g, "/");
    const segments = normalized.split("/").filter(Boolean);
    if (segments.length <= 2) return `/${segments.join("/")}`;
    return `.../${segments.slice(-2).join("/")}`;
  };

  return (
    <div
      style={{ height: `${height}px` }}
      className="bg-[#0A0D10] border-t border-[#2F343A] flex flex-col select-none text-[#E6EDF3] flex-shrink-0"
    >
      {/* Top Console Bar */}
      <div className="h-8 bg-[#14181E] border-b border-[#2F343A] flex items-center justify-between px-3 text-xs flex-shrink-0">
        {/* Left Console Sub-Tabs */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => setActiveTab("TERMINAL")}
            className={`flex items-center gap-1.5 font-semibold text-xs transition-colors border-b-2 py-1 ${
              activeTab === "TERMINAL"
                ? "text-purple-400 border-purple-500"
                : "text-[#8B949E] border-transparent hover:text-[#E6EDF3]"
            }`}
          >
            <TerminalIcon className="w-3.5 h-3.5" />
            <span>TERMINAL</span>
          </button>

          <button
            onClick={() => setActiveTab("VERIFICATION")}
            className={`flex items-center gap-1.5 font-semibold text-xs transition-colors border-b-2 py-1 ${
              activeTab === "VERIFICATION"
                ? "text-purple-400 border-purple-500"
                : "text-[#8B949E] border-transparent hover:text-[#E6EDF3]"
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>TEST RUNNER STDOUT</span>
          </button>

          <button
            onClick={() => setActiveTab("PROBLEMS")}
            className={`flex items-center gap-1.5 font-semibold text-xs transition-colors border-b-2 py-1 ${
              activeTab === "PROBLEMS"
                ? "text-purple-400 border-purple-500"
                : "text-[#8B949E] border-transparent hover:text-[#E6EDF3]"
            }`}
          >
            <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
            <span>PROBLEMS</span>
            {defects.length > 0 && (
              <span className="bg-rose-950 text-rose-300 text-[10px] px-1.5 rounded-full font-mono">
                {defects.length}
              </span>
            )}
          </button>
        </div>

        {/* Right Shell Controls */}
        <div className="flex items-center gap-2">
          {currentCwd && (
            <span className="text-[10px] font-mono text-purple-300/80 bg-purple-950/30 px-1.5 py-0.5 rounded border border-purple-500/20 max-w-[180px] truncate" title={currentCwd}>
              {formatShortCwd(currentCwd)}
            </span>
          )}
          <span className="text-[10px] font-mono text-[#8B949E]">{selectedShell}</span>
          <button
            onClick={handleRestartSession}
            disabled={isExecuting}
            className="p-1 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors"
            title="Restart Sandbox Shell Session"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isExecuting ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setTerminalEntries([])}
            className="p-1 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors"
            title="Clear Console"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          <button onClick={onClose} className="p-1 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Close Console">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Terminal Output Content */}
      <div className="flex-1 overflow-y-auto p-3 font-mono text-xs text-[#E6EDF3] bg-[#0A0D10] leading-relaxed scrollbar-thin">
        {activeTab === "TERMINAL" && (
          <div className="space-y-2">
            <div className="text-purple-400 font-semibold flex items-center justify-between">
              <span>GitOnBoard Persistent Sandbox Terminal [{runState?.repoId || "default"}]</span>
              {sessionId && (
                <span className="text-[10px] text-slate-500 font-normal">Session: {sessionId}</span>
              )}
            </div>
            <div className="text-slate-500 text-[11px]">
              Persistent interactive shell session. Working directory (`cd`) and environment exports (`export`) are maintained across commands.
            </div>


            {/* Render Verification Progress Summary if present */}
            {runState?.statusMessage && (
              <div className="text-amber-300 pt-1 border-t border-[#2F343A]/50">
                [Status Update]: {runState.statusMessage}
              </div>
            )}

            {/* Real Interactive Terminal Log Entries */}
            {terminalEntries.map((entry, idx) => (
              <div key={idx} className="space-y-1 border-t border-[#2F343A]/40 pt-1.5">
                {/* Command Line */}
                <div className="flex items-center gap-2 text-purple-300 font-bold">
                  <span>$</span>
                  <span>{entry.command}</span>
                </div>

                {/* Real Stdout */}
                {entry.stdout && (
                  <pre className="whitespace-pre-wrap text-[#E6EDF3] font-mono text-[11px] leading-relaxed bg-[#14181E]/60 p-1.5 rounded border border-[#2F343A]/30">
                    <code>{entry.stdout}</code>
                  </pre>
                )}

                {/* Real Stderr */}
                {entry.stderr && (
                  <pre className="whitespace-pre-wrap text-rose-300 font-mono text-[11px] leading-relaxed bg-rose-950/20 p-1.5 rounded border border-rose-500/30">
                    <code>{entry.stderr}</code>
                  </pre>
                )}

                {/* Truncation & Timeout Badges */}
                {entry.outputTruncated && (
                  <div className="text-amber-400 text-[10px] flex items-center gap-1 font-semibold">
                    <AlertTriangle className="w-3 h-3" />
                    <span>[Output stream capped at 1MB limit — process terminated]</span>
                  </div>
                )}
                {entry.timedOut && (
                  <div className="text-rose-400 text-[10px] flex items-center gap-1 font-semibold">
                    <AlertTriangle className="w-3 h-3" />
                    <span>[Execution timed out — process group killed]</span>
                  </div>
                )}

                {/* Exit Code & Timing Footer */}
                <div className="flex items-center gap-2 text-[10px]">
                  <span
                    className={`px-1.5 py-0.5 rounded font-mono font-semibold ${
                      entry.exitCode === 0
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-500/30"
                        : "bg-rose-950 text-rose-300 border border-rose-500/30"
                    }`}
                  >
                    Exit code: {entry.exitCode}
                  </span>
                  {entry.durationMs !== undefined && (
                    <span className="text-slate-500">({entry.durationMs}ms)</span>
                  )}
                </div>
              </div>
            ))}

            {isExecuting && (
              <div className="flex items-center gap-2 text-purple-400 text-[11px] italic pt-1">
                <RefreshCw className="w-3 h-3 animate-spin" />
                <span>Executing in worktree sandbox...</span>
              </div>
            )}

            <div ref={terminalEndRef} />
          </div>
        )}

        {activeTab === "VERIFICATION" && (
          <div className="space-y-2">
            <div className="text-purple-300 font-semibold border-b border-[#2F343A] pb-1 flex items-center justify-between">
              <span>Dynamic Test Runner Execution Output (pytest / jest / tsc)</span>
              <span className="text-[10px] text-slate-400 font-mono">
                Status: {report?.dynamic_result?.status || "PASS"}
              </span>
            </div>

            {dynamicDetails.pytest_stdout ? (
              <div>
                <div className="text-emerald-400 font-bold text-[11px] mb-1">Pytest Output:</div>
                <pre className="bg-[#14181E] border border-[#2F343A] p-2 rounded text-[11px] text-slate-300 overflow-x-auto">
                  <code>{dynamicDetails.pytest_stdout}</code>
                </pre>
              </div>
            ) : null}

            {dynamicDetails.node_build_stdout ? (
              <div>
                <div className="text-blue-400 font-bold text-[11px] mb-1">Node/TypeScript Compiler Output:</div>
                <pre className="bg-[#14181E] border border-[#2F343A] p-2 rounded text-[11px] text-slate-300 overflow-x-auto">
                  <code>{dynamicDetails.node_build_stdout}</code>
                </pre>
              </div>
            ) : null}

            {!dynamicDetails.pytest_stdout && !dynamicDetails.node_build_stdout && (
              <div className="text-slate-400 italic text-xs">
                No active test stdout recorded yet. Click "Run Verification" to execute dynamic tests inside the worktree sandbox.
              </div>
            )}
          </div>
        )}

        {activeTab === "PROBLEMS" && (
          <div className="space-y-2">
            <div className="text-rose-400 font-semibold border-b border-[#2F343A] pb-1">
              Verification Defects & Problems ({defects.length})
            </div>

            {defects.length > 0 ? (
              <div className="space-y-1.5">
                {defects.map((d, idx) => (
                  <div
                    key={idx}
                    className="p-2 rounded bg-[#14181E] border border-rose-500/30 flex items-start gap-2 text-[11px]"
                  >
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-bold text-rose-300">
                        [{d.category}] {d.file_path} {d.line_number ? `:${d.line_number}` : ""}
                      </div>
                      <div className="text-slate-300 mt-0.5">{d.description}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-emerald-400 text-xs italic">
                Zero problems detected. All static, dynamic, and contract verification checks passed cleanly!
              </div>
            )}
          </div>
        )}
      </div>

      {/* Terminal Input Bar at Bottom */}
      {activeTab === "TERMINAL" && (
        <form onSubmit={handleCommandSubmit} className="h-8 bg-[#14181E] border-t border-[#2F343A] flex items-center px-3 gap-2 flex-shrink-0">
          {currentCwd ? (
            <span className="text-purple-400 font-bold text-xs flex-shrink-0">
              [{formatShortCwd(currentCwd)}] $
            </span>
          ) : (
            <span className="text-purple-400 font-bold text-xs flex-shrink-0">$</span>
          )}
          <input
            type="text"
            value={commandInput}
            onChange={(e) => setCommandInput(e.target.value)}
            disabled={isExecuting}
            placeholder={isExecuting ? "Command executing..." : "Type command and press Enter (e.g. pwd, cd src, export FOO=bar)..."}
            className="flex-1 bg-transparent text-xs font-mono text-[#E6EDF3] placeholder-[#8B949E] focus:outline-none disabled:opacity-50"
          />
        </form>
      )}

    </div>
  );
}
