"use client";

import React, { useState } from "react";
import {
  Terminal as TerminalIcon,
  AlertCircle,
  X,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Plus,
  ChevronDown,
  MoreHorizontal,
  Split,
  Maximize2,
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
        Initializing sandbox terminal...
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
  const [activeTab, setActiveTab] = useState<"PROBLEMS" | "OUTPUT" | "DEBUG" | "TERMINAL" | "PORTS">("TERMINAL");
  const [activeSession, setActiveSession] = useState<"docker" | "node">("docker");
  const [isRestarting, setIsRestarting] = useState(false);
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
      className="bg-[#0D1117] border-t border-[#21262D] flex flex-col text-[#E6EDF3] flex-shrink-0 font-mono select-none"
    >
      {/* Top Console Bar (VS Code / Antigravity IDE layout) */}
      <div className="h-8 bg-[#161B22] border-b border-[#21262D] flex items-center justify-between px-3 text-xs flex-shrink-0">
        {/* Left Console Tabs */}
        <div className="flex items-center gap-4 text-[11px]">
          <button
            onClick={() => setActiveTab("PROBLEMS")}
            className={`flex items-center gap-1.5 font-medium transition-colors border-b-2 py-1 ${
              activeTab === "PROBLEMS"
                ? "text-purple-400 border-purple-500 font-semibold"
                : "text-zinc-400 border-transparent hover:text-zinc-200"
            }`}
          >
            <span>Problems</span>
            {defects.length > 0 ? (
              <span className="w-4 h-4 rounded-full bg-rose-500/20 text-rose-300 text-[10px] flex items-center justify-center font-bold">
                {defects.length}
              </span>
            ) : (
              <span className="w-4 h-4 rounded-full bg-zinc-800 text-zinc-400 text-[10px] flex items-center justify-center font-bold">
                0
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab("OUTPUT")}
            className={`flex items-center gap-1.5 font-medium transition-colors border-b-2 py-1 ${
              activeTab === "OUTPUT"
                ? "text-purple-400 border-purple-500 font-semibold"
                : "text-zinc-400 border-transparent hover:text-zinc-200"
            }`}
          >
            <span>Output</span>
          </button>

          <button
            onClick={() => setActiveTab("DEBUG")}
            className={`flex items-center gap-1.5 font-medium transition-colors border-b-2 py-1 ${
              activeTab === "DEBUG"
                ? "text-purple-400 border-purple-500 font-semibold"
                : "text-zinc-400 border-transparent hover:text-zinc-200"
            }`}
          >
            <span>Debug Console</span>
          </button>

          <button
            onClick={() => setActiveTab("TERMINAL")}
            className={`flex items-center gap-1.5 font-medium transition-colors border-b-2 py-1 ${
              activeTab === "TERMINAL"
                ? "text-purple-400 border-purple-500 font-semibold"
                : "text-zinc-400 border-transparent hover:text-zinc-200"
            }`}
          >
            <span>Terminal</span>
          </button>

          <button
            onClick={() => setActiveTab("PORTS")}
            className={`flex items-center gap-1.5 font-medium transition-colors border-b-2 py-1 ${
              activeTab === "PORTS"
                ? "text-purple-400 border-purple-500 font-semibold"
                : "text-zinc-400 border-transparent hover:text-zinc-200"
            }`}
          >
            <span>Ports</span>
          </button>
        </div>

        {/* Right Controls Bar */}
        <div className="flex items-center gap-2 text-zinc-400">
          {/* Terminal Session Selector */}
          <div className="flex items-center gap-1 bg-[#0D1117] border border-[#30363D] rounded px-1.5 py-0.5 text-[10px]">
            <button
              onClick={() => setActiveSession("docker")}
              className={`px-1.5 py-0.5 rounded transition-colors ${
                activeSession === "docker"
                  ? "bg-purple-600 text-white font-medium"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              &gt;_ docker
            </button>
            <button
              onClick={() => setActiveSession("node")}
              className={`px-1.5 py-0.5 rounded transition-colors ${
                activeSession === "node"
                  ? "bg-purple-600 text-white font-medium"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              &gt;_ node
            </button>
          </div>

          <button
            onClick={handleRestartTerminal}
            disabled={isRestarting}
            className="p-1 hover:text-zinc-200 hover:bg-[#21262D] rounded transition-colors"
            title="Restart Terminal Session"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={handleRestartTerminal}
            disabled={isRestarting}
            className="p-1 hover:text-zinc-200 hover:bg-[#21262D] rounded transition-colors"
            title="Reload sandbox PTY"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRestarting ? "animate-spin" : ""}`} />
          </button>

          <button
            onClick={onClose}
            className="p-1 hover:text-zinc-200 hover:bg-[#21262D] rounded transition-colors"
            title="Close Panel"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* TERMINAL View Tab */}
      {activeTab === "TERMINAL" && (
        <InteractiveTerminal key={terminalGeneration} runId={activeRunId} />
      )}

      {/* OUTPUT / VERIFICATION View Tab */}
      {activeTab === "OUTPUT" && (
        <div className="flex-1 overflow-y-auto p-3 font-mono text-xs text-zinc-200 bg-[#080B0E] space-y-2 leading-relaxed">
          <div className="text-purple-300 font-semibold border-b border-[#21262D] pb-1 flex items-center justify-between">
            <span>Dynamic Test Runner Execution Output</span>
            <span className="text-[10px] text-zinc-500 font-mono">
              Status: {report?.dynamic_result?.status || "PASS"}
            </span>
          </div>

          {dynamicDetails.pytest_stdout ? (
            <div>
              <div className="text-emerald-400 font-bold text-[11px] mb-1">Pytest Output:</div>
              <pre className="bg-[#161B22] border border-[#21262D] p-2 rounded text-[11px] text-zinc-300 overflow-x-auto">
                <code>{dynamicDetails.pytest_stdout}</code>
              </pre>
            </div>
          ) : null}

          {dynamicDetails.node_build_stdout ? (
            <div>
              <div className="text-blue-400 font-bold text-[11px] mb-1">TypeScript Compiler Output:</div>
              <pre className="bg-[#161B22] border border-[#21262D] p-2 rounded text-[11px] text-zinc-300 overflow-x-auto">
                <code>{dynamicDetails.node_build_stdout}</code>
              </pre>
            </div>
          ) : null}

          {!dynamicDetails.pytest_stdout && !dynamicDetails.node_build_stdout && (
            <div className="text-zinc-500 italic text-xs">
              No active test runner output. Click &quot;Run Verification&quot; to execute dynamic verification tests.
            </div>
          )}
        </div>
      )}

      {/* PROBLEMS View Tab */}
      {activeTab === "PROBLEMS" && (
        <div className="flex-1 overflow-y-auto p-3 font-mono text-xs text-zinc-200 bg-[#080B0E] space-y-2 leading-relaxed">
          <div className="text-purple-300 font-semibold border-b border-[#21262D] pb-1">
            <span>Static AST & Contract Verification Defects</span>
          </div>
          {defects.length > 0 ? (
            <div className="space-y-1.5">
              {defects.map((d: any, idx: number) => (
                <div
                  key={idx}
                  className="p-2 rounded bg-rose-950/20 border border-rose-500/30 flex items-start gap-2 text-xs"
                >
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <div className="flex-1 space-y-0.5">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-rose-300">
                        {d.defect_type || d.type || "AST Defect"}
                      </span>
                      <span className="text-[10px] text-zinc-500 font-mono">
                        {d.file_path || "workspace"}
                      </span>
                    </div>
                    <p className="text-[11px] text-zinc-300">{d.message || d.description}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-zinc-500 italic text-xs">No defects detected in current workspace.</div>
          )}
        </div>
      )}

      {/* DEBUG CONSOLE & PORTS View Tabs */}
      {(activeTab === "DEBUG" || activeTab === "PORTS") && (
        <div className="flex-1 flex items-center justify-center p-4 text-zinc-500 text-xs italic bg-[#080B0E]">
          {activeTab === "DEBUG" ? "Debugger disconnected." : "Port 3000 (Next.js) | Port 8000 (FastAPI)"}
        </div>
      )}
    </div>
  );
}
