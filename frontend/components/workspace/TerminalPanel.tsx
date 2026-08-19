"use client";

import React, { useState } from "react";
import {
  Terminal as TerminalIcon,
  AlertCircle,
  X,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import dynamic from "next/dynamic";
import { RunState } from "@/types/workspace";
import { resetSandboxTerminal } from "@/services/sandboxApi";

const InteractiveTerminal = dynamic(
  () => import("./InteractiveTerminal").then((mod) => mod.InteractiveTerminal),
  {
    ssr: false,
    loading: () => (
      <div className="flex-1 flex items-center justify-center text-xs text-slate-500 font-mono">
        Initializing terminal...
      </div>
    ),
  }
);

interface TerminalPanelProps {
  isOpen: boolean;
  onClose: () => void;
  runState?: RunState;
  height?: number;
}

export function TerminalPanel({ isOpen, onClose, runState, height = 224 }: TerminalPanelProps) {
  const [activeTab, setActiveTab] = useState<"TERMINAL" | "VERIFICATION" | "PROBLEMS">("TERMINAL");
  const [isRestarting, setIsRestarting] = useState(false);
  // Bumping this remounts <InteractiveTerminal>, which opens a fresh websocket
  // (and a fresh xterm.js buffer) against the freshly-reset backend PTY session.
  const [terminalGeneration, setTerminalGeneration] = useState(0);

  const report = runState?.report;
  const dynamicDetails = report?.dynamic_result?.details || {};
  const defects = report?.defects || [];

  const activeRunId = runState?.runId || runState?.repoId || "default";

  if (!isOpen) return null;

  const handleRestartTerminal = async () => {
    setIsRestarting(true);
    try {
      await resetSandboxTerminal(activeRunId);
    } catch (err) {
      console.error("Failed to reset terminal session:", err);
    } finally {
      setTerminalGeneration((g) => g + 1);
      setIsRestarting(false);
    }
  };

  return (
    <div
      style={{ height: `${height}px` }}
      className="bg-[#0A0D10] border-t border-[#2F343A] flex flex-col text-[#E6EDF3] flex-shrink-0"
    >
      {/* Top Console Bar */}
      <div className="h-8 bg-[#14181E] border-b border-[#2F343A] flex items-center justify-between px-3 text-xs flex-shrink-0 select-none">
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
          <span className="text-[10px] font-mono text-[#8B949E]">bash (persistent PTY sandbox)</span>
          {activeTab === "TERMINAL" && (
            <button
              onClick={handleRestartTerminal}
              disabled={isRestarting}
              className="p-1 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors"
              title="Restart Sandbox Shell Session"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRestarting ? "animate-spin" : ""}`} />
            </button>
          )}
          <button onClick={onClose} className="p-1 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Close Console">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* TERMINAL tab: a real interactive terminal (xterm.js) streaming raw
          bytes over a websocket to an actual PTY-backed shell. No command
          history, no cwd tracking, and no synthesized "Directory changed" /
          "Command completed" messages here — the shell itself owns its
          prompt, readline history, and output, exactly like a real terminal. */}
      {activeTab === "TERMINAL" && (
        <InteractiveTerminal key={terminalGeneration} runId={activeRunId} />
      )}

      {/* VERIFICATION and PROBLEMS tabs are unrelated to the interactive shell —
          they render structured results from the dynamic verification pipeline. */}
      {(activeTab === "VERIFICATION" || activeTab === "PROBLEMS") && (
        <div className="flex-1 overflow-y-auto p-3 font-mono text-xs text-[#E6EDF3] bg-[#0A0D10] leading-relaxed scrollbar-thin">
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
                  No active test stdout recorded yet. Click &quot;Run Verification&quot; to execute dynamic tests inside the worktree sandbox.
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
      )}
    </div>
  );
}
