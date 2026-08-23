"use client";

import React, { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileCode,
  Layers,
  PauseCircle,
  Play,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import { ImplementationPlanData, PlanTaskItem, WorkspaceSnapshot } from "@/types/workspace";

interface PlanPanelProps {
  snapshot: WorkspaceSnapshot | null;
  onApprovePlan: () => void;
  onRejectPlan: (reason?: string) => void;
  onSelectFile?: (file: string) => void;
  isLoading?: boolean;
}

export function PlanPanel({
  snapshot,
  onApprovePlan,
  onRejectPlan,
  onSelectFile,
  isLoading = false,
}: PlanPanelProps) {
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);

  const plan = snapshot?.plan;
  const tasks = snapshot?.tasks || [];
  const runState = snapshot?.run?.current_state;
  const isAwaitingApproval =
    runState === "AWAITING_APPROVAL" ||
    plan?.status === "READY_FOR_APPROVAL";

  const handleReject = () => {
    if (!rejectReason.trim()) {
      setShowRejectInput(true);
      return;
    }
    onRejectPlan(rejectReason.trim());
    setRejectReason("");
    setShowRejectInput(false);
  };

  if (!plan && tasks.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-zinc-500 font-mono text-center">
        <Layers className="w-10 h-10 mb-3 text-zinc-600 animate-pulse" />
        <p className="text-xs font-semibold text-zinc-400">No Implementation Plan Yet</p>
        <p className="text-[11px] text-zinc-500 max-w-sm mt-1">
          The agent will synthesize and validate an explicit multi-task DAG plan during the planning stage.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#0D1117] text-zinc-200 overflow-y-auto p-4 space-y-4 font-mono">
      {/* Plan Header Card with Open in Editor button */}
      <div className="bg-[#161B22] p-4 rounded-lg border border-[#30363D] space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-purple-400" />
            <span className="text-xs font-semibold text-white">
              Implementation Plan v{plan?.version || 1}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {onSelectFile && (
              <button
                type="button"
                onClick={() => onSelectFile("implementation_plan.md")}
                className="text-[10px] px-2 py-0.5 rounded bg-[#21262D] hover:bg-[#30363D] text-purple-400 hover:text-purple-300 border border-[#30363D] flex items-center gap-1 transition-colors"
                title="Open Markdown spec in Monaco Editor"
              >
                <FileCode className="w-3 h-3" />
                <span>Open in Editor</span>
              </button>
            )}
            <span
              className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium border ${
                plan?.status === "APPROVED"
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                  : plan?.status === "READY_FOR_APPROVAL"
                  ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  : "bg-zinc-800 text-zinc-400 border-zinc-700"
              }`}
            >
              {plan?.status || "DRAFT"}
            </span>
          </div>
        </div>
        <p className="text-xs text-zinc-300">
          {snapshot?.run?.user_requirement || "Plan for target requirements"}
        </p>
      </div>

      {/* Phase 9 Plan Approval Banner */}
      {isAwaitingApproval && (
        <div className="bg-amber-950/30 border border-amber-500/40 p-4 rounded-lg space-y-3 shadow-lg shadow-amber-950/20">
          <div className="flex items-center gap-2 text-amber-400">
            <PauseCircle className="w-5 h-5 animate-pulse" />
            <span className="text-xs font-bold uppercase tracking-wider">
              Explicit Plan Approval Required (Phase 9)
            </span>
          </div>
          <p className="text-xs text-zinc-300">
            Review the {tasks.length} tasks and acceptance criteria below. Invariant: Zero execution occurs until explicitly approved.
          </p>

          {showRejectInput && (
            <div className="space-y-1.5 pt-1">
              <label className="text-[11px] text-zinc-400">Revision feedback for agent:</label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="e.g. Please add unit test task for payment edge cases..."
                className="w-full h-16 bg-[#0D1117] border border-amber-500/40 rounded p-2 text-xs font-mono text-zinc-200 focus:outline-none focus:border-amber-400"
              />
            </div>
          )}

          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={() => (showRejectInput ? handleReject() : setShowRejectInput(true))}
              disabled={isLoading}
              className="px-3 py-1.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-xs font-medium transition-all"
            >
              {showRejectInput ? "Submit Rejection" : "Reject Plan"}
            </button>
            <button
              onClick={onApprovePlan}
              disabled={isLoading}
              className="flex-1 px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium shadow-md transition-all flex items-center justify-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Approve Plan & Start Execution</span>
            </button>
          </div>
        </div>
      )}

      {/* Task List */}
      <div className="space-y-2">
        <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
          Plan Tasks DAG ({tasks.length})
        </span>

        {tasks.map((task: PlanTaskItem) => {
          const isExpanded = expandedTask === task.task_id;
          const status = task.status || "PENDING";

          return (
            <div
              key={task.task_id}
              className="bg-[#161B22] border border-[#30363D] rounded-lg overflow-hidden transition-all"
            >
              <div
                onClick={() => setExpandedTask(isExpanded ? null : task.task_id)}
                className="p-3 flex items-center justify-between cursor-pointer hover:bg-[#1C2128]"
              >
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-purple-500/20 text-purple-400 flex items-center justify-center text-[11px] font-bold">
                    {task.step_number}
                  </div>
                  <span className="text-xs font-medium text-zinc-200">{task.title}</span>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${
                      status === "PASSED"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : status === "RUNNING"
                        ? "bg-blue-500/10 text-blue-400 animate-pulse"
                        : status === "BLOCKED"
                        ? "bg-rose-500/10 text-rose-400"
                        : "bg-zinc-800 text-zinc-400"
                    }`}
                  >
                    {status}
                  </span>
                  {isExpanded ? (
                    <ChevronDown className="w-4 h-4 text-zinc-500" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-zinc-500" />
                  )}
                </div>
              </div>

              {isExpanded && (
                <div className="p-3 border-t border-[#21262D] bg-[#0D1117] space-y-2.5 text-xs">
                  {task.description && (
                    <div>
                      <span className="text-[10px] text-zinc-500 uppercase">Description</span>
                      <p className="text-zinc-300 mt-0.5">{task.description}</p>
                    </div>
                  )}

                  {task.dependencies?.length > 0 && (
                    <div>
                      <span className="text-[10px] text-zinc-500 uppercase">Dependencies</span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {task.dependencies.map((dep) => (
                          <span
                            key={dep}
                            className="px-2 py-0.5 rounded bg-[#161B22] border border-[#30363D] text-[11px] text-zinc-300"
                          >
                            {dep}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {task.affected_files?.length > 0 && (
                    <div>
                      <span className="text-[10px] text-zinc-500 uppercase">Affected Files</span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {task.affected_files.map((file) => (
                          <span
                            key={file}
                            className="px-2 py-0.5 rounded bg-blue-950/30 border border-blue-500/30 text-[11px] text-blue-300 flex items-center gap-1"
                          >
                            <FileCode className="w-3 h-3" />
                            <span>{file}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {task.acceptance_criteria?.length > 0 && (
                    <div>
                      <span className="text-[10px] text-zinc-500 uppercase">Acceptance Criteria</span>
                      <ul className="list-disc list-inside space-y-1 mt-1 text-zinc-300">
                        {task.acceptance_criteria.map((c, cIdx) => (
                          <li key={cIdx} className="text-[11px]">
                            {c}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {task.verification_strategy && (
                    <div>
                      <span className="text-[10px] text-zinc-500 uppercase">Verification Strategy</span>
                      <p className="text-cyan-400 font-mono text-[11px] mt-0.5">
                        {task.verification_strategy}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
