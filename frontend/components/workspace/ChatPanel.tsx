"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ArrowUp,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileCode,
  FileDiff,
  FileMinus,
  FilePlus,
  GitBranch,
  Layers,
  Mic,
  MoreHorizontal,
  PauseCircle,
  Play,
  Plus,
  RotateCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Square,
  Terminal,
  User,
  Wrench,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import { EventStreamItem, WorkspaceSnapshot } from "@/types/workspace";

interface ChatPanelProps {
  snapshot: WorkspaceSnapshot | null;
  onStartRun: (prompt: string) => void;
  onApprovePlan?: () => void;
  onRejectPlan?: (reason?: string) => void;
  onNavigateToPlan?: () => void;
  onApproveAction?: (approvalId: string) => void;
  onRejectAction?: (approvalId: string, reason: string) => void;
  onSelectFile?: (file: string) => void;
  isLoading?: boolean;
}

export function ChatPanel({
  snapshot,
  onStartRun,
  onApprovePlan,
  onRejectPlan,
  onNavigateToPlan,
  onApproveAction,
  onRejectAction,
  onSelectFile,
  isLoading = false,
}: ChatPanelProps) {
  const [inputPrompt, setInputPrompt] = useState("");
  const [selectedModel, setSelectedModel] = useState("Gemini 3.7 Flash Medium");
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [expandedEvents, setExpandedEvents] = useState<Record<string, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const events = snapshot?.latest_events || [];
  const run = snapshot?.run;
  const plan = snapshot?.plan;
  const changes = snapshot?.changes;
  const pendingApprovals = snapshot?.pending_approvals || [];
  const isAwaitingApproval =
    run?.current_state === "AWAITING_APPROVAL" ||
    plan?.status === "READY_FOR_APPROVAL";
  const isRunning = Boolean(
    run?.id &&
    run.current_state !== "COMPLETED" &&
    run.current_state !== "CANCELLED" &&
    run.current_state !== "FAILED"
  );

  const availableModels = [
    "Gemini 3.7 Flash Medium",
    "Gemini 2.5 Pro",
    "Claude 3.7 Sonnet (Thinking)",
    "Ollama: Qwen-2.5-Coder-7B",
    "Ollama: DeepSeek-R1-14B",
  ];

  // Auto-scroll to bottom on new events
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length, isAwaitingApproval, pendingApprovals.length]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputPrompt.trim() || isLoading) return;
    onStartRun(inputPrompt.trim());
    setInputPrompt("");
  };

  const toggleEventExpand = (id: string) => {
    setExpandedEvents((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Render Antigravity-style activity / stream cards
  const renderEventCard = (evt: EventStreamItem, idx: number) => {
    const type = String(evt?.event_type || (evt as any)?.type || "");
    const evtId = evt.event_id || `evt-${idx}`;
    const isExpanded = Boolean(expandedEvents[evtId]);

    // 1. Tool Call / Terminal Execution Card (e.g. npm run build, AST extraction)
    if (type === "TOOL_CALL_STARTED" || type === "TOOL_CALL_COMPLETED" || evt.payload?.command) {
      const cmd = evt.payload?.command || evt.payload?.tool_name || evt.message;
      return (
        <div
          key={evtId}
          className="bg-[#18181B] border border-[#27272A] rounded-lg overflow-hidden font-mono text-xs my-2 transition-all shadow-sm"
        >
          <div
            onClick={() => toggleEventExpand(evtId)}
            className="px-3 py-2 bg-[#121214] flex items-center justify-between cursor-pointer hover:bg-[#1A1A1E] text-zinc-300 select-none"
          >
            <div className="flex items-center gap-2 truncate">
              <Terminal className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
              <span className="text-[11px] text-zinc-300 truncate">{cmd}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-zinc-500">
                {type === "TOOL_CALL_COMPLETED" ? "completed" : "running"}
              </span>
              <ChevronRight
                className={`w-3.5 h-3.5 text-zinc-500 transition-transform ${
                  isExpanded ? "rotate-90" : ""
                }`}
              />
            </div>
          </div>
          {isExpanded && evt.payload && (
            <div className="p-3 bg-[#0F0F11] border-t border-[#27272A] text-[11px] text-zinc-400 overflow-x-auto">
              <pre className="whitespace-pre font-mono">
                {JSON.stringify(evt.payload, null, 2)}
              </pre>
            </div>
          )}
        </div>
      );
    }

    // 2. State Transition / Progress pill
    if (type === "STATE_TRANSITION") {
      return (
        <div
          key={evtId}
          className="flex items-center gap-2 text-zinc-400 text-xs py-1 px-1 font-sans"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-purple-500" />
          <span className="text-zinc-300 text-[11px] font-mono">{evt.message}</span>
        </div>
      );
    }

    // 3. Plan / Milestone completed
    if (type === "PLANNING_COMPLETED" || type === "PLAN_READY_FOR_APPROVAL") {
      return (
        <div
          key={evtId}
          className="bg-[#18181B] border border-purple-500/30 rounded-lg p-3 my-2 space-y-1.5 font-sans"
        >
          <div className="flex items-center gap-2 text-purple-300 text-xs font-semibold">
            <Layers className="w-4 h-4 text-purple-400" />
            <span>Implementation Plan Synthesized</span>
          </div>
          <p className="text-xs text-zinc-300 font-mono leading-relaxed">{evt.message}</p>
        </div>
      );
    }

    // 4. Verification Passed / Defect Cards
    if (type === "VERIFICATION_PASSED") {
      return (
        <div
          key={evtId}
          className="bg-emerald-950/20 border border-emerald-500/30 rounded-lg p-3 my-2 space-y-1 font-sans"
        >
          <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold">
            <ShieldCheck className="w-4 h-4" />
            <span>Verification Succeeded</span>
          </div>
          <p className="text-xs text-zinc-300 font-mono">{evt.message}</p>
        </div>
      );
    }

    if (type === "VERIFICATION_FAILED" || type === "VERIFICATION_CHECK_FAILED") {
      return (
        <div
          key={evtId}
          className="bg-rose-950/20 border border-rose-500/30 rounded-lg p-3 my-2 space-y-1 font-sans"
        >
          <div className="flex items-center gap-2 text-rose-400 text-xs font-semibold">
            <ShieldAlert className="w-4 h-4" />
            <span>Defect Detected (Entering Self-Repair)</span>
          </div>
          <p className="text-xs text-zinc-300 font-mono">{evt.message}</p>
        </div>
      );
    }

    // Default message
    return (
      <div
        key={evtId}
        className="flex gap-2 text-xs py-1.5 px-2 bg-[#18181B]/50 rounded border border-[#27272A]/50 my-1 font-sans"
      >
        <div className="w-4 h-4 rounded bg-zinc-800 text-zinc-400 flex items-center justify-center shrink-0 mt-0.5">
          <Activity className="w-2.5 h-2.5" />
        </div>
        <div className="flex-1 text-zinc-300 font-mono text-[11px] leading-relaxed">
          {evt.message}
        </div>
      </div>
    );
  };

  const totalFilesChanged =
    (changes?.modified_files?.length || 0) +
    (changes?.added_files?.length || 0) +
    (changes?.deleted_files?.length || 0);

  return (
    <div className="flex flex-col h-full bg-[#0F0F12] text-zinc-200 font-sans select-none">
      {/* Top Conversation Header */}
      <div className="px-3.5 py-2.5 border-b border-[#27272A] bg-[#141417] flex items-center justify-between">
        <div className="flex items-center gap-2 truncate">
          <span className="text-xs font-medium text-zinc-100 truncate">
            {run?.user_requirement ? run.user_requirement.slice(0, 45) + "..." : "Engineering Agent Session"}
          </span>
        </div>
        <div className="flex items-center gap-1 text-zinc-400">
          <button
            onClick={() => onStartRun("")}
            title="New Chat / Reset"
            className="p-1 hover:bg-[#27272A] hover:text-zinc-200 rounded transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button
            title="Search conversation"
            className="p-1 hover:bg-[#27272A] hover:text-zinc-200 rounded transition-colors"
          >
            <Search className="w-3.5 h-3.5" />
          </button>
          <button
            title="Options"
            className="p-1 hover:bg-[#27272A] hover:text-zinc-200 rounded transition-colors"
          >
            <MoreHorizontal className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Conversation & Activity Scroll Area */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
        {/* User Prompt Message */}
        {run?.user_requirement ? (
          <div className="flex gap-3 bg-[#18181B] p-3 rounded-xl border border-[#27272A] shadow-sm">
            <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center shrink-0 text-xs font-semibold">
              <User className="w-3.5 h-3.5" />
            </div>
            <div className="flex-1 space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-zinc-200">You</span>
                <span className="text-[10px] text-zinc-500 font-mono">
                  {run.started_at ? new Date(run.started_at).toLocaleTimeString() : "just now"}
                </span>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed font-sans">
                {run.user_requirement}
              </p>
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-zinc-500 space-y-3">
            <div className="w-10 h-10 rounded-2xl bg-purple-600/10 border border-purple-500/20 flex items-center justify-center text-purple-400 shadow-inner">
              <Bot className="w-5 h-5" />
            </div>
            <div className="space-y-1 max-w-xs">
              <p className="text-xs font-semibold text-zinc-300">Engineering Agent Workspace</p>
              <p className="text-[11px] text-zinc-500 leading-relaxed">
                Describe a feature, refactor, or bug fix. The agent will analyze CST symbols, synthesize an execution contract, and stream verified changes.
              </p>
            </div>
          </div>
        )}

        {/* Timeline Events Feed */}
        {events.map((evt, idx) => renderEventCard(evt, idx))}

        {/* Antigravity-style Implementation Plan Card */}
        {(isAwaitingApproval || plan) && (
          <div className="bg-[#161B22] border border-purple-500/50 rounded-xl p-4 space-y-3.5 shadow-xl my-3 animate-in fade-in duration-300">
            {/* Plan Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-md bg-purple-600/30 text-purple-300 flex items-center justify-center border border-purple-500/40 shadow-inner">
                  <Layers className="w-3.5 h-3.5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-zinc-100">Implementation Plan</span>
                    <span className="text-[10px] px-1.5 py-0.2 bg-zinc-800 text-zinc-400 rounded font-mono">
                      v{plan?.version || 1}
                    </span>
                  </div>
                  <span className="text-[10px] text-zinc-400 font-sans">
                    {snapshot?.tasks?.length || plan?.tasks?.length || 0} discrete DAG tasks
                  </span>
                </div>
              </div>
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium border ${
                  isAwaitingApproval
                    ? "bg-amber-500/10 text-amber-400 border-amber-500/30 animate-pulse"
                    : "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                }`}
              >
                {isAwaitingApproval ? "Awaiting Approval" : "Approved"}
              </span>
            </div>

            {/* Clickable Antigravity Plan Artifact Pill (Opens implementation_plan.md in Code Editor) */}
            <button
              type="button"
              onClick={() => onSelectFile?.("implementation_plan.md")}
              className="w-full bg-[#0D1117] hover:bg-[#21262D] border border-[#30363D] hover:border-purple-500/60 rounded-lg p-2.5 flex items-center justify-between text-left group transition-all"
              title="Open implementation_plan.md in Editor"
            >
              <div className="flex items-center gap-2.5 overflow-hidden">
                <FileCode className="w-4 h-4 text-purple-400 group-hover:text-purple-300 shrink-0" />
                <div className="truncate">
                  <div className="text-[11px] font-semibold text-zinc-200 group-hover:text-white truncate">
                    implementation_plan.md
                  </div>
                  <div className="text-[10px] text-zinc-500 group-hover:text-zinc-400 truncate">
                    {plan?.requirement || run?.user_requirement || "Plan specifications & acceptance criteria"}
                  </div>
                </div>
              </div>
              <span className="text-[10px] text-purple-400 group-hover:text-purple-300 flex items-center gap-1 font-sans shrink-0">
                <span>Open in editor</span>
                <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </span>
            </button>

            {/* Tasks Preview List */}
            {snapshot?.tasks && snapshot.tasks.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <div className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">
                  Task Execution Pipeline
                </div>
                <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                  {snapshot.tasks.map((t, idx) => (
                    <div
                      key={t.task_id || idx}
                      onClick={() => {
                        if (t.affected_files && t.affected_files.length > 0) {
                          onSelectFile?.(t.affected_files[0]);
                        } else {
                          onSelectFile?.("implementation_plan.md");
                        }
                      }}
                      className="bg-[#0D1117]/80 hover:bg-[#1E232B] p-2 rounded border border-[#21262D] flex items-center justify-between text-xs cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-2 truncate">
                        <span className="text-[10px] w-4 h-4 rounded-full bg-zinc-800 text-zinc-400 flex items-center justify-center font-bold shrink-0">
                          {idx + 1}
                        </span>
                        <span className="text-[11px] text-zinc-300 hover:text-white truncate font-medium">
                          {t.title}
                        </span>
                      </div>
                      {t.affected_files && t.affected_files.length > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-zinc-800/80 text-zinc-400 rounded shrink-0 font-mono">
                          {t.affected_files[0].split("/").pop()}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Invariants & Acceptance Preview */}
            {plan?.acceptance_criteria && plan.acceptance_criteria.length > 0 && (
              <div className="text-[11px] text-zinc-400 font-sans space-y-1 bg-[#0D1117]/60 p-2 rounded border border-[#21262D]">
                <div className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3 text-emerald-400" />
                  <span>Acceptance Invariants</span>
                </div>
                <ul className="list-disc list-inside space-y-0.5 text-zinc-300 text-[10px]">
                  {plan.acceptance_criteria.slice(0, 2).map((ac: string, i: number) => (
                    <li key={i} className="truncate">{ac}</li>
                  ))}
                  {plan.acceptance_criteria.length > 2 && (
                    <li className="text-zinc-500 italic">+{plan.acceptance_criteria.length - 2} more criteria</li>
                  )}
                </ul>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex items-center justify-between pt-1 border-t border-[#21262D]">
              <button
                type="button"
                onClick={() => onSelectFile?.("implementation_plan.md")}
                className="text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1 font-sans"
              >
                <FileCode className="w-3 h-3 text-purple-400" />
                <span>View Full Spec</span>
              </button>

              <div className="flex items-center gap-2">
                {onNavigateToPlan && (
                  <button
                    type="button"
                    onClick={onNavigateToPlan}
                    className="px-2.5 py-1.5 rounded-lg bg-[#21262D] hover:bg-[#30363D] text-zinc-300 text-xs font-medium transition-all"
                  >
                    <span>Plan Tab</span>
                  </button>
                )}
                {isAwaitingApproval && onApprovePlan && (
                  <button
                    type="button"
                    onClick={onApprovePlan}
                    disabled={isLoading}
                    className="px-4 py-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-purple-600/30 transition-all flex items-center gap-1.5"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Proceed (Approve)</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Antigravity-style Diff Review & Approval Card (Files With Changes) */}
        {totalFilesChanged > 0 && (
          <div className="bg-[#18181B] border border-[#27272A] rounded-xl overflow-hidden shadow-lg my-3 font-mono text-xs">
            <div className="p-3 bg-[#141417] border-b border-[#27272A] flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-200">
                {totalFilesChanged} Files With Changes
              </span>
              <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
                Worktree Patch
              </span>
            </div>

            <div className="p-2.5 space-y-1.5 max-h-48 overflow-y-auto">
              {changes?.modified_files?.map((file) => (
                <div
                  key={file}
                  onClick={() => onSelectFile?.(file)}
                  className="flex items-center justify-between p-1.5 rounded hover:bg-[#202024] cursor-pointer text-zinc-300 text-[11px]"
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="text-amber-400 font-bold">M</span>
                    <span className="truncate">{file}</span>
                  </div>
                  <span className="text-[10px] text-zinc-500">modified</span>
                </div>
              ))}

              {changes?.added_files?.map((file) => (
                <div
                  key={file}
                  onClick={() => onSelectFile?.(file)}
                  className="flex items-center justify-between p-1.5 rounded hover:bg-[#202024] cursor-pointer text-zinc-300 text-[11px]"
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="text-emerald-400 font-bold">+</span>
                    <span className="truncate">{file}</span>
                  </div>
                  <span className="text-[10px] text-emerald-500">added</span>
                </div>
              ))}
            </div>

            {/* Bottom Actions Bar */}
            <div className="p-2.5 bg-[#141417] border-t border-[#27272A] flex items-center justify-between">
              <div className="flex items-center gap-1 text-[11px] text-zinc-400">
                <ArrowRight className="w-3 h-3" />
                <span>{totalFilesChanged} Files Modified</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onRejectPlan?.("Changes rejected by user")}
                  className="px-2.5 py-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  Reject all
                </button>
                <button
                  onClick={onApprovePlan}
                  className="px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded-md text-xs font-semibold shadow-sm transition-all"
                >
                  Accept all
                </button>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Antigravity Signature Chat Input Container */}
      <div className="p-3 border-t border-[#27272A] bg-[#141417]">
        <div className="bg-[#18181B] border border-[#27272A] focus-within:border-purple-500/80 rounded-xl p-2.5 space-y-2 shadow-inner transition-colors">
          {/* Main Input Textarea */}
          <form onSubmit={handleSubmit} className="space-y-2">
            <textarea
              rows={2}
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder="Ask anything, @ to mention, / for actions"
              disabled={isLoading || isRunning}
              className="w-full bg-transparent text-xs text-zinc-100 placeholder:text-zinc-500 font-sans focus:outline-none resize-none leading-relaxed"
            />

            {/* Bottom Controls inside input card */}
            <div className="flex items-center justify-between pt-1 border-t border-[#222226]">
              {/* Left Model Selector & Plus Icon */}
              <div className="flex items-center gap-1.5 relative">
                <button
                  type="button"
                  title="Add context / attachment"
                  className="w-5 h-5 rounded hover:bg-[#27272A] text-zinc-400 hover:text-zinc-200 flex items-center justify-center text-xs transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>

                {/* Model Selector Pill */}
                <button
                  type="button"
                  onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}
                  className="flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-200 px-2 py-0.5 rounded-md hover:bg-[#27272A] transition-colors font-sans"
                >
                  <span>{selectedModel}</span>
                  <ChevronDown className="w-3 h-3 text-zinc-500" />
                </button>

                {/* Model Dropdown Menu */}
                {isModelDropdownOpen && (
                  <div className="absolute bottom-7 left-0 w-52 bg-[#18181B] border border-[#27272A] rounded-lg shadow-xl py-1 z-50 text-xs">
                    {availableModels.map((m) => (
                      <div
                        key={m}
                        onClick={() => {
                          setSelectedModel(m);
                          setIsModelDropdownOpen(false);
                        }}
                        className={`px-3 py-1.5 flex items-center justify-between cursor-pointer hover:bg-[#27272A] ${
                          selectedModel === m ? "text-purple-400 font-medium" : "text-zinc-300"
                        }`}
                      >
                        <span className="truncate">{m}</span>
                        {selectedModel === m && <Check className="w-3.5 h-3.5" />}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Right Mic & Circular Send Button */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  title="Voice input"
                  className="p-1 text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <Mic className="w-3.5 h-3.5" />
                </button>

                <button
                  type="submit"
                  disabled={isLoading || !inputPrompt.trim() || isRunning}
                  className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                    inputPrompt.trim() && !isRunning
                      ? "bg-purple-600 hover:bg-purple-500 text-white shadow-sm"
                      : isRunning
                      ? "bg-rose-500 text-white animate-pulse"
                      : "bg-[#27272A] text-zinc-500 cursor-not-allowed"
                  }`}
                >
                  {isRunning ? (
                    <Square className="w-2.5 h-2.5 fill-current" />
                  ) : (
                    <ArrowUp className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
