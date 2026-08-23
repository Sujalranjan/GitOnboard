"use client";

import React from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Clock,
  FileCode,
  Layers,
  Play,
  RotateCw,
  ShieldAlert,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { PlanTaskItem, WorkspaceSnapshot } from "@/types/workspace";

interface TaskPanelProps {
  snapshot: WorkspaceSnapshot | null;
  onSelectFile?: (file: string) => void;
}

export function TaskPanel({ snapshot, onSelectFile }: TaskPanelProps) {
  const tasks = snapshot?.tasks || [];
  const activeTask = snapshot?.active_task;

  if (tasks.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-zinc-500 font-mono text-center">
        <Zap className="w-10 h-10 mb-3 text-zinc-600 animate-pulse" />
        <p className="text-xs font-semibold text-zinc-400">No Tasks in Queue</p>
        <p className="text-[11px] text-zinc-500 max-w-sm mt-1">
          Tasks will appear here once the implementation plan is synthesized and approved.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#0D1117] text-zinc-200 overflow-y-auto p-4 space-y-4 font-mono">
      {/* Active Task Highlight Card */}
      {activeTask && (
        <div className="bg-gradient-to-br from-purple-950/40 to-[#161B22] border border-purple-500/40 p-4 rounded-lg space-y-3 shadow-lg shadow-purple-950/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-purple-400">
              <Activity className="w-4 h-4 animate-spin" />
              <span className="text-xs font-bold uppercase tracking-wider">
                Active Task #{activeTask.step_number}
              </span>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded font-mono font-medium bg-purple-500/20 text-purple-300 border border-purple-500/30">
              {activeTask.status || "RUNNING"}
            </span>
          </div>

          <div>
            <h4 className="text-sm font-semibold text-white">{activeTask.title}</h4>
            {activeTask.description && (
              <p className="text-xs text-zinc-300 mt-1">{activeTask.description}</p>
            )}
          </div>

          {/* Affected Files */}
          {activeTask.affected_files?.length > 0 && (
            <div>
              <span className="text-[10px] text-zinc-400 uppercase tracking-wider">Affected Files</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {activeTask.affected_files.map((file) => (
                  <button
                    key={file}
                    onClick={() => onSelectFile && onSelectFile(file)}
                    className="px-2 py-0.5 rounded bg-[#161B22] hover:bg-purple-900/30 border border-[#30363D] hover:border-purple-500/40 text-[11px] text-zinc-300 flex items-center gap-1 transition-colors"
                  >
                    <FileCode className="w-3 h-3 text-purple-400" />
                    <span>{file}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Acceptance Criteria */}
          {activeTask.acceptance_criteria?.length > 0 && (
            <div>
              <span className="text-[10px] text-zinc-400 uppercase tracking-wider">Acceptance Criteria</span>
              <div className="space-y-1 mt-1">
                {activeTask.acceptance_criteria.map((crit, idx) => (
                  <div key={idx} className="flex items-start gap-1.5 text-xs text-zinc-300">
                    <CheckCircle2 className="w-3.5 h-3.5 text-zinc-500 mt-0.5 shrink-0" />
                    <span className="text-[11px]">{crit}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Complete Task Pipeline List */}
      <div className="space-y-2">
        <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
          Task Execution Sequence
        </span>

        {tasks.map((t: PlanTaskItem, idx: number) => {
          const status = t.status || "PENDING";
          const isPassed = status === "PASSED";
          const isRunning = status === "RUNNING" || status === "VERIFYING" || status === "REPAIRING";
          const isBlocked = status === "BLOCKED";

          return (
            <div
              key={t.task_id}
              className={`p-3 rounded-lg border flex items-center justify-between transition-all ${
                isRunning
                  ? "bg-purple-950/20 border-purple-500/40"
                  : isPassed
                  ? "bg-emerald-950/10 border-emerald-500/20"
                  : isBlocked
                  ? "bg-rose-950/20 border-rose-500/40"
                  : "bg-[#161B22] border-[#30363D]"
              }`}
            >
              <div className="flex items-center gap-3">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                    isPassed
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                      : isRunning
                      ? "bg-purple-500/20 text-purple-400 border border-purple-500/40"
                      : isBlocked
                      ? "bg-rose-500/20 text-rose-400 border border-rose-500/40"
                      : "bg-zinc-800 text-zinc-500 border border-zinc-700"
                  }`}
                >
                  {isPassed ? <CheckCircle2 className="w-3.5 h-3.5" /> : t.step_number}
                </div>

                <div>
                  <h5 className="text-xs font-medium text-zinc-200">{t.title}</h5>
                  {t.dependencies?.length > 0 && (
                    <span className="text-[10px] text-zinc-500">
                      Depends on: {t.dependencies.join(", ")}
                    </span>
                  )}
                </div>
              </div>

              <span
                className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${
                  isPassed
                    ? "bg-emerald-500/10 text-emerald-400"
                    : isRunning
                    ? "bg-purple-500/10 text-purple-400 animate-pulse"
                    : isBlocked
                    ? "bg-rose-500/10 text-rose-400"
                    : "bg-zinc-800 text-zinc-500"
                }`}
              >
                {status}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
