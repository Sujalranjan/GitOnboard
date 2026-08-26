"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Code2,
  ExternalLink,
  FileCode,
  FileSearch,
  FileText,
  HelpCircle,
  Layers,
  PauseCircle,
  Play,
  RotateCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Tag,
  X,
} from "lucide-react";
import { ImplementationPlanData, PlanTaskItem, SourceSnippetEvidence } from "@/types/workspace";

interface PlanDocumentViewerProps {
  plan: ImplementationPlanData | null;
  activePlan?: ImplementationPlanData | null;
  onApprovePlan?: () => void;
  onRejectPlan?: (reason?: string) => void;
  onSelectFile?: (file: string) => void;
  onSelectPlan?: (plan: ImplementationPlanData) => void;
  isLoading?: boolean;
}

export function PlanDocumentViewer({
  plan,
  activePlan,
  onApprovePlan,
  onRejectPlan,
  onSelectFile,
  onSelectPlan,
  isLoading = false,
}: PlanDocumentViewerProps) {
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [expandedTasks, setExpandedTasks] = useState<Record<string, boolean>>({});

  if (!plan) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-center select-none font-mono bg-[#0A0D10] text-zinc-500">
        <Layers className="w-12 h-12 mb-3 text-zinc-700 animate-pulse" />
        <p className="text-sm font-semibold text-zinc-400">No Implementation Plan Selected</p>
        <p className="text-xs text-zinc-600 max-w-md mt-1.5">
          Select a plan from the Plan History tab or click "Preview full plan" in the chat to inspect the full structured implementation plan.
        </p>
      </div>
    );
  }

  const isCurrent = !activePlan || activePlan.plan_id === plan.plan_id || activePlan.version === plan.version;
  const isStale = !isCurrent;
  const isAwaitingApproval = isCurrent && (plan.status === "READY_FOR_APPROVAL" || plan.status === "PENDING_APPROVAL");

  const investigation = plan.investigation;
  const assessment = investigation?.assessment || "NEW";
  const tasks = plan.tasks || [];
  const risks = plan.risks || [];
  const unknowns = (plan as any).unknowns || [];
  const allAffectedFiles = Array.from(
    new Set(tasks.flatMap((t) => t.affected_files || []).concat(investigation?.inspected_files || []))
  );

  const toggleTask = (taskId: string) => {
    setExpandedTasks((prev) => ({
      ...prev,
      [taskId]: !prev[taskId],
    }));
  };

  const handleConfirmReject = () => {
    onRejectPlan?.(rejectReason.trim() || "Plan rejected during review.");
    setRejectReason("");
    setShowRejectModal(false);
  };

  return (
    <div className="h-full overflow-y-auto bg-[#0A0D10] text-zinc-200 p-6 lg:p-8 font-sans selection:bg-purple-900 selection:text-white space-y-6">
      {/* 1. Document Header & Version Strip */}
      <div className="bg-[#14181E] border border-[#2F343A] rounded-xl p-5 space-y-4 shadow-md">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#21262D] pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-600/20 border border-purple-500/40 flex items-center justify-center text-purple-400 shadow-inner">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-white tracking-wide">
                  Implementation Plan
                </h1>
                <span className="text-xs px-2 py-0.5 rounded font-mono font-bold bg-purple-950 text-purple-300 border border-purple-500/40">
                  v{plan.version || 1}
                </span>
                {isCurrent ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                    CURRENT
                  </span>
                ) : (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
                    STALE / SUPERSEDED
                  </span>
                )}
              </div>
              <p className="text-xs text-zinc-400 font-mono mt-0.5">
                Plan ID: <span className="text-zinc-300">{plan.plan_id}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`text-xs px-2.5 py-1 rounded font-mono font-semibold uppercase border ${
                plan.status === "APPROVED"
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                  : plan.status === "REJECTED"
                  ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                  : isAwaitingApproval
                  ? "bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse"
                  : "bg-zinc-800 text-zinc-400 border-zinc-700"
              }`}
            >
              {plan.status || "DRAFT"}
            </span>
          </div>
        </div>

        {/* Plan Metadata Summary Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
          <div className="bg-[#0D1117] p-2.5 rounded-lg border border-[#21262D]">
            <span className="text-[10px] text-zinc-500 uppercase block">Assessment</span>
            <span
              className={`text-sm font-bold ${
                assessment === "EXISTING"
                  ? "text-emerald-400"
                  : assessment === "PARTIAL"
                  ? "text-amber-400"
                  : assessment === "NEW"
                  ? "text-cyan-400"
                  : "text-purple-400"
              }`}
            >
              {assessment}
            </span>
          </div>
          <div className="bg-[#0D1117] p-2.5 rounded-lg border border-[#21262D]">
            <span className="text-[10px] text-zinc-500 uppercase block">Tasks</span>
            <span className="text-sm font-bold text-zinc-200">{tasks.length} Steps</span>
          </div>
          <div className="bg-[#0D1117] p-2.5 rounded-lg border border-[#21262D]">
            <span className="text-[10px] text-zinc-500 uppercase block">Files Inspected</span>
            <span className="text-sm font-bold text-zinc-200">{allAffectedFiles.length} Target Files</span>
          </div>
          <div className="bg-[#0D1117] p-2.5 rounded-lg border border-[#21262D]">
            <span className="text-[10px] text-zinc-500 uppercase block">Investigation</span>
            <span className="text-sm font-bold text-emerald-400">Verified</span>
          </div>
        </div>

        {/* Approval/Rejection Audit Trail */}
        {(plan.resolved_by || plan.resolved_at) && (
          <div className="bg-[#0D1117] p-3 rounded-lg border border-[#21262D] space-y-1.5">
            <div className="flex items-center justify-between text-[10px] text-zinc-500 uppercase font-bold">
              <span>Approval Audit Trail</span>
              {plan.status === "APPROVED" && <span className="text-emerald-400">Approved</span>}
              {plan.status === "REJECTED" && <span className="text-rose-400">Rejected</span>}
            </div>
            <div className="space-y-1 text-xs text-zinc-300 font-mono">
              {plan.resolved_by && (
                <div>
                  <span className="text-zinc-500">Resolved by:</span>{" "}
                  <span className="text-zinc-100">{plan.resolved_by}</span>
                </div>
              )}
              {plan.resolved_at && (
                <div>
                  <span className="text-zinc-500">Resolved at:</span>{" "}
                  <span className="text-zinc-100">
                    {new Date(plan.resolved_at).toLocaleString()}
                  </span>
                </div>
              )}
              {plan.rejection_reason && (
                <div className="pt-1 border-t border-zinc-800">
                  <span className="text-zinc-500">Rejection reason:</span>
                  <p className="text-zinc-200 pt-0.5">{plan.rejection_reason}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 2. Stale Plan Warning Banner */}
      {isStale && activePlan && (
        <div className="bg-amber-950/30 border border-amber-500/50 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-md">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
            <div>
              <div className="text-xs font-bold text-amber-300">
                Outdated Plan Specification (v{plan.version})
              </div>
              <div className="text-[11px] text-zinc-300 mt-0.5 font-mono">
                This plan was superseded by current active plan v{activePlan.version}. It is displayed for historical inspection only and cannot be executed.
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onSelectPlan?.(activePlan)}
            className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-zinc-950 font-bold text-xs font-mono flex items-center gap-1.5 transition-colors shrink-0 cursor-pointer shadow"
          >
            <span>View Current Plan (v{activePlan.version})</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* 3. Primary Action Buttons: [ Reject ] and [ Review ] */}
      {isAwaitingApproval && onApprovePlan && (
        <div className="bg-gradient-to-b from-[#1E1B2E] to-[#141220] border-2 border-purple-500/60 rounded-xl p-5 space-y-4 shadow-xl shadow-purple-950/30">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5 text-purple-300">
              <PauseCircle className="w-5 h-5 animate-pulse text-purple-400 shrink-0" />
              <div>
                <span className="text-xs font-bold uppercase tracking-wider block text-white">
                  Plan Awaiting Review & Authorization
                </span>
                <span className="text-[11px] text-zinc-300">
                  Review the repository investigation and planned tasks below. Zero repository modifications occur until explicitly authorized.
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between gap-3 pt-2 border-t border-[#2F343A]">
            {/* Distinct Reject Action */}
            <button
              type="button"
              onClick={() => setShowRejectModal(true)}
              disabled={isLoading}
              className="px-4 py-2.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-xs font-bold font-mono transition-all flex items-center gap-2 cursor-pointer"
              title="Reject this implementation plan"
            >
              <Ban className="w-3.5 h-3.5" />
              <span>Reject</span>
            </button>

            {/* Distinct Review Action */}
            <button
              type="button"
              onClick={onApprovePlan}
              disabled={isLoading}
              className="px-6 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold font-mono shadow-lg shadow-emerald-950/40 transition-all flex items-center gap-2 cursor-pointer"
              title="Review and authorize this plan for implementation"
            >
              <ShieldCheck className="w-4 h-4" />
              <span>Review</span>
            </button>
          </div>
        </div>
      )}

      {/* Rejection Feedback Dialog */}
      {showRejectModal && (
        <div className="bg-[#14181E] border border-rose-500/40 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-rose-300 font-mono">Reject Plan Feedback</span>
            <button onClick={() => setShowRejectModal(false)} className="text-zinc-400 hover:text-white">
              <X className="w-4 h-4" />
            </button>
          </div>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Provide optional reason or revision instructions (e.g. 'Use existing status endpoint instead of new file')..."
            className="w-full h-20 bg-[#0D1117] border border-rose-500/30 rounded-lg p-2.5 text-xs font-mono text-zinc-200 focus:outline-none focus:border-rose-400"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowRejectModal(false)}
              className="px-3 py-1.5 rounded-lg bg-[#21262D] text-xs font-mono text-zinc-300 hover:bg-[#30363D]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleConfirmReject}
              className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs font-mono text-white font-bold"
            >
              Confirm Rejection
            </button>
          </div>
        </div>
      )}

      {/* 4. REPOSITORY INVESTIGATION & EVIDENCE CARD */}
      <div className="bg-[#14181E] border border-purple-500/40 rounded-xl p-5 space-y-4 shadow-md">
        <div className="flex items-center justify-between border-b border-[#21262D] pb-3">
          <div className="flex items-center gap-2">
            <FileSearch className="w-4 h-4 text-purple-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-purple-300 font-mono">
              Repository Investigation & Evidence
            </h2>
          </div>
          <span
            className={`text-xs px-2.5 py-0.5 rounded font-mono font-bold uppercase border ${
              assessment === "EXISTING"
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                : assessment === "PARTIAL"
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                : assessment === "NEW"
                ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40"
                : "bg-purple-500/20 text-purple-300 border-purple-500/40"
            }`}
          >
            Assessment: {assessment}
          </span>
        </div>

        {/* Decision Rationale */}
        <div className="bg-[#0D1117] p-3.5 rounded-lg border border-[#21262D] space-y-1.5">
          <span className="text-[10px] text-zinc-500 font-mono font-bold uppercase block">
            Decision Rationale
          </span>
          <p className="text-xs text-zinc-200 font-mono leading-relaxed">
            {investigation?.decision_rationale || "Repository investigated for existing capabilities."}
          </p>
          {investigation?.assessment_reason && (
            <p className="text-[11px] text-zinc-400 font-mono pt-1 border-t border-zinc-800/80">
              <span className="text-zinc-500">Grounding:</span> {investigation.assessment_reason}
            </p>
          )}
        </div>

        {/* Inspected Candidates & Symbols */}
        {((investigation?.inspected_files && investigation.inspected_files.length > 0) ||
          (investigation?.relevant_symbols && investigation.relevant_symbols.length > 0) ||
          (investigation?.relevant_routes && investigation.relevant_routes.length > 0)) && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
            {investigation?.relevant_routes && investigation.relevant_routes.length > 0 && (
              <div className="bg-[#0D1117] p-3 rounded-lg border border-[#21262D] space-y-1">
                <span className="text-[10px] text-zinc-500 uppercase font-bold">Routes Inspected</span>
                <div className="flex flex-wrap gap-1">
                  {investigation.relevant_routes.map((r) => (
                    <span key={r} className="px-2 py-0.5 rounded bg-purple-950/40 text-purple-300 border border-purple-500/30 text-[11px]">
                      {r}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {investigation?.relevant_symbols && investigation.relevant_symbols.length > 0 && (
              <div className="bg-[#0D1117] p-3 rounded-lg border border-[#21262D] space-y-1">
                <span className="text-[10px] text-zinc-500 uppercase font-bold">Symbols Inspected</span>
                <div className="flex flex-wrap gap-1">
                  {investigation.relevant_symbols.map((s) => (
                    <span key={s} className="px-2 py-0.5 rounded bg-blue-950/40 text-blue-300 border border-blue-500/30 text-[11px]">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Source Code Evidence Snippets */}
        {investigation?.source_snippets && investigation.source_snippets.length > 0 && (
          <div className="space-y-2.5">
            <span className="text-[10px] text-zinc-400 font-mono font-bold uppercase block">
              Source Code Evidence ({investigation.source_snippets.length})
            </span>
            <div className="space-y-2">
              {investigation.source_snippets.map((snip: SourceSnippetEvidence, sIdx: number) => (
                <div key={sIdx} className="bg-[#0D1117] border border-[#21262D] rounded-lg overflow-hidden text-xs font-mono">
                  <div className="p-2 bg-[#161B22] border-b border-[#21262D] flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => onSelectFile?.(snip.file_path)}
                      className="text-blue-300 hover:text-blue-200 flex items-center gap-1.5 cursor-pointer"
                    >
                      <FileCode className="w-3.5 h-3.5 text-blue-400" />
                      <span>{snip.file_path}:{snip.line_start}-{snip.line_end}</span>
                    </button>
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-400 uppercase">
                      {snip.match_type}
                    </span>
                  </div>
                  <pre className="p-3 text-[11px] text-zinc-300 font-mono overflow-x-auto bg-[#0A0D10] leading-relaxed">
                    <code>{snip.code_snippet}</code>
                  </pre>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 5. Objective Section */}
      <div className="bg-[#14181E] border border-[#2F343A] rounded-xl p-5 space-y-2">
        <h2 className="text-xs font-bold uppercase tracking-wider text-purple-400 font-mono">
          Objective
        </h2>
        <p className="text-sm text-zinc-100 font-sans leading-relaxed">
          {plan.requirement || "Implement requested repository changes."}
        </p>
      </div>

      {/* 6. Proposed Changes & Affected Files */}
      {allAffectedFiles.length > 0 && (
        <div className="bg-[#14181E] border border-[#2F343A] rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-purple-400 font-mono">
              Proposed Changes & Affected Files ({allAffectedFiles.length})
            </h2>
            <span className="text-[10px] text-zinc-500 font-mono">Click file to open in editor tab</span>
          </div>

          <div className="flex flex-wrap gap-2">
            {allAffectedFiles.map((file) => (
              <button
                key={file}
                type="button"
                onClick={() => onSelectFile?.(file)}
                className="px-3 py-1.5 rounded-lg bg-[#0D1117] hover:bg-[#1E222A] border border-blue-500/30 hover:border-blue-500/60 text-xs font-mono text-blue-300 flex items-center gap-2 transition-all cursor-pointer shadow-sm group"
                title={`Open ${file} in Code Editor`}
              >
                <FileCode className="w-3.5 h-3.5 text-blue-400 group-hover:scale-110 transition-transform" />
                <span>{file}</span>
                <ExternalLink className="w-3 h-3 opacity-60 group-hover:opacity-100" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 7. Implementation Tasks DAG */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-xs font-bold uppercase tracking-wider text-purple-400 font-mono">
            Implementation Tasks ({tasks.length})
          </h2>
          <span className="text-xs text-emerald-400 font-mono">Verified DAG (0 cycles)</span>
        </div>

        {tasks.length === 0 ? (
          <div className="bg-[#14181E] border border-emerald-500/40 rounded-xl p-5 text-center space-y-1.5 font-mono">
            <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-1" />
            <div className="text-xs font-bold text-emerald-300">Capability Already Exists (Assessment: EXISTING)</div>
            <p className="text-[11px] text-zinc-400 max-w-md mx-auto">
              No code modifications or file creation tasks required. The requested capability is already implemented in the repository.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {tasks.map((task: PlanTaskItem, idx: number) => {
              const isExpanded = expandedTasks[task.task_id] !== false;
              const status = task.status || "PENDING";
              const componentType = task.component_type || "EXISTING";

              return (
                <div
                  key={task.task_id || idx}
                  className="bg-[#14181E] border border-[#2F343A] rounded-xl overflow-hidden shadow-sm transition-all"
                >
                  <div
                    onClick={() => toggleTask(task.task_id || String(idx))}
                    className="p-4 flex items-center justify-between cursor-pointer hover:bg-[#1C2128] transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/40 flex items-center justify-center text-xs font-bold font-mono shrink-0">
                        {task.step_number || idx + 1}
                      </div>
                      <span className="text-sm font-semibold text-zinc-100 truncate">{task.title}</span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold shrink-0 ${
                          componentType === "EXISTING"
                            ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/30"
                            : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                        }`}
                      >
                        [{componentType}]
                      </span>
                    </div>

                    <div className="flex items-center gap-2.5 shrink-0 font-mono text-xs">
                      <span
                        className={`px-2.5 py-0.5 rounded font-medium ${
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
                        <ChevronDown className="w-4 h-4 text-zinc-400" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-zinc-400" />
                      )}
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="p-4 border-t border-[#21262D] bg-[#0D1117] space-y-3.5 text-xs font-sans">
                      {/* "Why this file?" Explicit Task Rationale */}
                      {task.rationale && (
                        <div className="bg-[#14181E] border border-purple-500/30 p-2.5 rounded-lg space-y-1 font-mono">
                          <span className="text-[10px] text-purple-400 uppercase font-bold block">
                            Why this task is necessary
                          </span>
                          <p className="text-zinc-300 text-[11px] leading-relaxed">{task.rationale}</p>
                        </div>
                      )}

                      {task.description && (
                        <div className="space-y-1">
                          <span className="text-[10px] font-mono text-zinc-500 uppercase font-bold">
                            Description
                          </span>
                          <p className="text-zinc-300 leading-relaxed">{task.description}</p>
                        </div>
                      )}

                      {task.affected_files && task.affected_files.length > 0 && (
                        <div className="space-y-1">
                          <span className="text-[10px] font-mono text-zinc-500 uppercase font-bold">
                            Target Files
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {task.affected_files.map((file) => (
                              <button
                                key={file}
                                type="button"
                                onClick={() => onSelectFile?.(file)}
                                className="px-2.5 py-1 rounded bg-blue-950/30 hover:bg-blue-900/40 border border-blue-500/30 text-[11px] font-mono text-blue-300 flex items-center gap-1.5 transition-colors cursor-pointer"
                              >
                                <FileCode className="w-3 h-3" />
                                <span>{file}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
                        <div className="space-y-1">
                          <span className="text-[10px] font-mono text-zinc-500 uppercase font-bold">
                            Acceptance Criteria
                          </span>
                          <ul className="list-disc list-inside space-y-1 text-zinc-300 pl-1">
                            {task.acceptance_criteria.map((ac, acIdx) => (
                              <li key={acIdx} className="leading-relaxed">
                                {ac}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {task.verification_strategy && (
                        <div className="space-y-1">
                          <span className="text-[10px] font-mono text-zinc-500 uppercase font-bold">
                            Verification Strategy
                          </span>
                          <p className="text-cyan-400 font-mono text-[11px] bg-[#161B22] p-2 rounded-lg border border-zinc-800">
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
        )}
      </div>

      {/* 8. Technical Risks & Unknowns */}
      {(risks.length > 0 || unknowns.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {risks.length > 0 && (
            <div className="bg-[#14181E] border border-amber-500/30 rounded-xl p-5 space-y-2.5">
              <div className="flex items-center gap-2 text-amber-400">
                <AlertTriangle className="w-4 h-4" />
                <h3 className="text-xs font-bold uppercase font-mono">
                  Technical Risks ({risks.length})
                </h3>
              </div>
              <ul className="space-y-1.5 text-xs text-zinc-300 font-sans">
                {risks.map((r, rIdx) => (
                  <li key={rIdx} className="flex items-start gap-1.5">
                    <span className="text-amber-400 font-bold">•</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {unknowns.length > 0 && (
            <div className="bg-[#14181E] border border-purple-500/30 rounded-xl p-5 space-y-2.5">
              <div className="flex items-center gap-2 text-purple-400">
                <HelpCircle className="w-4 h-4" />
                <h3 className="text-xs font-bold uppercase font-mono">
                  Assumptions & Unknowns ({unknowns.length})
                </h3>
              </div>
              <ul className="space-y-1.5 text-xs text-zinc-300 font-sans">
                {unknowns.map((u: string, uIdx: number) => (
                  <li key={uIdx} className="flex items-start gap-1.5">
                    <span className="text-purple-400 font-bold">•</span>
                    <span>{u}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
