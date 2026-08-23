"use client";

import React from "react";
import {
  Activity,
  AlertCircle,
  AlertOctagon,
  CheckCircle2,
  Clock,
  GitBranch,
  Layers,
  PauseCircle,
  PlayCircle,
  RotateCw,
  ShieldCheck,
  StopCircle,
  Terminal,
  Zap,
} from "lucide-react";
import { AgentState, ConnectionStatus, WorkspaceSnapshot } from "@/types/workspace";

interface AgentHeaderProps {
  snapshot: WorkspaceSnapshot | null;
  connectionStatus: ConnectionStatus;
  onCancelRun: (reason?: string) => void;
  isLoading?: boolean;
}

export function AgentHeader({
  snapshot,
  connectionStatus,
  onCancelRun,
  isLoading = false,
}: AgentHeaderProps) {
  const run = snapshot?.run;
  const state: AgentState = (run?.current_state as AgentState) || "IDLE";
  const activeTask = snapshot?.active_task;

  // Determine state pill colors and icons
  const getStateBadge = (st: AgentState) => {
    switch (st) {
      case "UNDERSTANDING":
      case "PLANNING":
        return {
          bg: "bg-blue-500/10 border-blue-500/30 text-blue-400",
          icon: <Activity className="w-3.5 h-3.5 animate-pulse text-blue-400" />,
          label: st,
        };
      case "AWAITING_APPROVAL":
        return {
          bg: "bg-amber-500/10 border-amber-500/30 text-amber-400",
          icon: <PauseCircle className="w-3.5 h-3.5 text-amber-400" />,
          label: "AWAITING APPROVAL",
        };
      case "EXECUTING":
        return {
          bg: "bg-purple-500/10 border-purple-500/30 text-purple-400",
          icon: <PlayCircle className="w-3.5 h-3.5 animate-spin text-purple-400" />,
          label: "EXECUTING TASK",
        };
      case "VERIFYING":
        return {
          bg: "bg-cyan-500/10 border-cyan-500/30 text-cyan-400",
          icon: <ShieldCheck className="w-3.5 h-3.5 animate-pulse text-cyan-400" />,
          label: "VERIFYING",
        };
      case "BLOCKED":
        return {
          bg: "bg-rose-500/10 border-rose-500/30 text-rose-400",
          icon: <AlertOctagon className="w-3.5 h-3.5 text-rose-400" />,
          label: "BLOCKED (NEEDS HELP)",
        };
      case "COMPLETED":
        return {
          bg: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
          icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />,
          label: "COMPLETED",
        };
      case "CANCELLED":
        return {
          bg: "bg-gray-500/10 border-gray-500/30 text-gray-400",
          icon: <StopCircle className="w-3.5 h-3.5 text-gray-400" />,
          label: "CANCELLED",
        };
      default:
        return {
          bg: "bg-zinc-800/40 border-zinc-700 text-zinc-400",
          icon: <Clock className="w-3.5 h-3.5 text-zinc-400" />,
          label: st,
        };
    }
  };

  const badge = getStateBadge(state);
  const isCancellable =
    state === "EXECUTING" ||
    state === "PLANNING" ||
    state === "UNDERSTANDING" ||
    state === "VERIFYING" ||
    state === "AWAITING_APPROVAL";

  return (
    <header className="h-14 border-b border-[#21262D] bg-[#0D1117] px-4 flex items-center justify-between select-none shrink-0">
      {/* Left: Brand + Run Identity */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center shadow-md shadow-purple-900/20">
            <Zap className="w-4 h-4 text-white" />
          </div>
          <div className="flex flex-col">
            <span className="text-xs font-semibold tracking-wider text-white uppercase font-mono">
              Engineering Agent
            </span>
            <span className="text-[10px] text-zinc-400 font-mono">
              {run?.repository_id ? `${run.repository_id}` : "Workspace Session"}
            </span>
          </div>
        </div>

        {run?.id && (
          <div className="hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded border border-[#30363D] bg-[#161B22] text-[11px] font-mono text-zinc-300">
            <span className="text-zinc-500">Run:</span>
            <span className="text-purple-300 font-medium">#{run.id.slice(0, 12)}</span>
          </div>
        )}
      </div>

      {/* Center: State Pill + Active Task */}
      <div className="flex items-center gap-3">
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium font-mono ${badge.bg}`}
        >
          {badge.icon}
          <span>{badge.label}</span>
        </div>

        {activeTask && (
          <div className="hidden md:flex items-center gap-1.5 text-xs text-zinc-300 font-mono bg-[#161B22] px-3 py-1 rounded border border-[#30363D] max-w-sm truncate">
            <span className="text-purple-400 font-semibold">Task {activeTask.step_number}:</span>
            <span className="truncate text-zinc-200">{activeTask.title}</span>
          </div>
        )}
      </div>

      {/* Right: Connection Status & Stop Control */}
      <div className="flex items-center gap-3">
        {/* Connection Indicator */}
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-zinc-400">
          <div
            className={`w-2 h-2 rounded-full ${
              connectionStatus === "CONNECTED"
                ? "bg-emerald-400 shadow-sm shadow-emerald-400/50"
                : connectionStatus === "RECONNECTING"
                ? "bg-amber-400 animate-pulse"
                : "bg-rose-500"
            }`}
          />
          <span className="hidden lg:inline capitalize text-[10px] text-zinc-400">
            {connectionStatus.toLowerCase()}
          </span>
        </div>

        {/* Global Stop Button */}
        {isCancellable && (
          <button
            onClick={() => onCancelRun("Cancelled by operator")}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 hover:border-rose-500/50 text-xs font-mono font-medium transition-all shadow-sm active:scale-95"
            title="Stop and cancel active agent execution"
          >
            <StopCircle className="w-3.5 h-3.5" />
            <span>Stop Agent</span>
          </button>
        )}
      </div>
    </header>
  );
}
