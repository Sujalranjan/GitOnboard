"use client";

import React, { useState } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Copy,
  Download,
  Layers,
  Loader2,
  Play,
  X,
} from "lucide-react";
import { ImplementationPlanData } from "@/types/workspace";

interface PlanDocumentViewerProps {
  plan: ImplementationPlanData | null;
  activePlan?: ImplementationPlanData | null;
  onApprovePlan?: () => void;
  onRejectPlan?: (reason?: string) => void;
  onSelectFile?: (file: string) => void;
  onSelectPlan?: (plan: ImplementationPlanData) => void;
  onSendMessage?: (msg: string) => void;
  isLoading?: boolean;
}

export function PlanDocumentViewer({
  plan,
  activePlan,
  onApprovePlan,
  onRejectPlan,
  onSelectFile,
  onSelectPlan,
  onSendMessage,
  isLoading = false,
}: PlanDocumentViewerProps) {
  const [copied, setCopied] = useState(false);
  const [showReviewPopup, setShowReviewPopup] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [bottomInput, setBottomInput] = useState("");

  if (!plan) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-center select-none font-mono bg-[#0A0D10] text-zinc-500">
        <Layers className="w-10 h-10 mb-3 text-zinc-700 animate-pulse" />
        <p className="text-sm font-semibold text-zinc-400">No Implementation Plan</p>
        <p className="text-xs text-zinc-600 max-w-sm mt-1">
          Type an implementation request in the chat to synthesize a repository plan.
        </p>
      </div>
    );
  }

  const isCurrent = !activePlan || activePlan.plan_id === plan.plan_id || activePlan.version === plan.version;
  const isAwaitingApproval = isCurrent && (plan.status === "READY_FOR_APPROVAL" || plan.status === "PENDING_APPROVAL");
  const isApproved = plan.status === "APPROVED";
  const isExecuting = plan.status === "EXECUTING" || plan.status === "RUNNING";
  const isCompleted = plan.status === "COMPLETED" || plan.status === "PASSED";

  const tasks = plan.tasks || [];
  const allAffectedFiles = Array.from(
    new Set(tasks.flatMap((t) => t.affected_files || []).concat(plan.investigation?.inspected_files || []))
  );

  const getMarkdownPlan = () => {
    return (
      `# Implementation Plan v${plan.version || 1}\n\n` +
      `## ${plan.requirement || "Implementation Plan"}\n` +
      `${plan.description || ""}\n\n` +
      `### Files (${allAffectedFiles.length})\n` +
      allAffectedFiles.map((f) => `- ${f}`).join("\n") +
      "\n\n" +
      `### Steps (${tasks.length})\n` +
      tasks.map((t, i) => `${i + 1}. ${t.title}${t.affected_files ? ` (in ${t.affected_files.join(", ")})` : ""}`).join("\n")
    );
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(getMarkdownPlan());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  const handleCommentSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentText.trim()) return;
    onRejectPlan?.(commentText.trim());
    setCommentText("");
    setShowReviewPopup(false);
  };

  const handleBottomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!bottomInput.trim()) return;
    onSendMessage?.(bottomInput.trim());
    setBottomInput("");
  };

  return (
    <div className="h-full overflow-y-auto bg-[#0A0D10] text-zinc-200 p-6 lg:p-8 font-sans selection:bg-purple-900 selection:text-white flex flex-col justify-between">
      <div className="space-y-5 max-w-3xl">
        {/* 1. Header with [Copy] [Review v] [Proceed] */}
        <div className="flex items-center justify-between pb-3 border-b border-[#21262D]">
          <h1 className="text-base font-bold text-white tracking-tight">
            Implementation Plan
          </h1>

          <div className="flex items-center gap-2 relative">
            {/* Copy Icon Button */}
            <button
              type="button"
              onClick={handleCopy}
              className="p-1.5 rounded-lg hover:bg-[#21262D] text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
              title="Copy markdown plan"
            >
              {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            </button>

            {/* Review Dropdown Button */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowReviewPopup((prev) => !prev)}
                className={`px-3 py-1 rounded-lg border text-xs font-sans flex items-center gap-1.5 transition-colors cursor-pointer ${
                  showReviewPopup
                    ? "bg-[#282E3E] border-purple-500/50 text-white"
                    : "bg-[#1E232F] hover:bg-[#282E3E] border-[#30363D] text-zinc-300 hover:text-white"
                }`}
              >
                <span>Review</span>
                <ChevronDown className="w-3.5 h-3.5 text-zinc-400" />
              </button>

              {/* Review / Submit Comment Popover (Cloned from reference) */}
              {showReviewPopup && (
                <div className="absolute right-0 mt-2 w-96 bg-[#1A1F2C] border border-[#2D3344] rounded-2xl shadow-2xl p-4 z-50 text-xs font-sans animate-in fade-in zoom-in-95 duration-100">
                  <h3 className="text-xs font-semibold text-white mb-2.5">
                    Submit comment
                  </h3>

                  <form onSubmit={handleCommentSubmit} className="space-y-3">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        autoFocus
                        value={commentText}
                        onChange={(e) => setCommentText(e.target.value)}
                        placeholder="Add a message..."
                        className="flex-1 bg-[#242A3B] border border-[#323B50] rounded-xl px-3 py-2 text-xs text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-purple-500/80 transition-colors"
                      />
                      <button
                        type="submit"
                        disabled={!commentText.trim()}
                        className={`px-3.5 py-2 rounded-xl text-xs font-semibold transition-colors ${
                          commentText.trim()
                            ? "bg-purple-600 hover:bg-purple-500 text-white cursor-pointer"
                            : "bg-[#323B50] text-zinc-500 cursor-not-allowed"
                        }`}
                      >
                        Submit
                      </button>
                    </div>

                    <p className="text-[11px] text-zinc-400">
                      Select text in the artifact to add a comment
                    </p>
                  </form>
                </div>
              )}
            </div>

            {/* Proceed Primary Button */}
            <button
              type="button"
              disabled={isLoading || isApproved || isExecuting}
              onClick={onApprovePlan}
              className={`px-4 py-1 rounded-lg font-semibold text-xs font-sans flex items-center gap-1.5 transition-all shadow-sm ${
                isApproved
                  ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40 cursor-default"
                  : isExecuting
                  ? "bg-purple-950 text-purple-300 border border-purple-500/40 cursor-default"
                  : "bg-[#C084FC] hover:bg-[#D8B4FE] text-[#1E1B4B] cursor-pointer hover:shadow-purple-900/30"
              }`}
            >
              {isLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : isApproved ? (
                <Check className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <Play className="w-3 h-3 fill-current" />
              )}
              <span>{isApproved ? "Approved" : isExecuting ? "Executing..." : isCompleted ? "Completed" : "Proceed"}</span>
            </button>
          </div>
        </div>

        {/* 2. Files Section */}
        <div className="space-y-2 pt-2">
          <div className="text-xs font-bold text-zinc-200">
            Files ({allAffectedFiles.length || 2})
          </div>
          <ul className="space-y-1.5 pl-1">
            {(allAffectedFiles.length > 0
              ? allAffectedFiles
              : ["pls_cli/please.py", "tests/test_pls_cli.py"]
            ).map((file) => (
              <li key={file} className="flex items-center gap-2 text-xs">
                <span className="text-zinc-500">•</span>
                <button
                  type="button"
                  onClick={() => onSelectFile?.(file)}
                  className="text-xs text-zinc-300 hover:text-purple-300 font-mono transition-colors cursor-pointer"
                >
                  {file}
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* 3. Steps Section */}
        <div className="space-y-2 pt-2">
          <div className="text-xs font-bold text-zinc-200">
            Steps ({tasks.length || 2})
          </div>
          <ol className="space-y-2 pl-1">
            {(tasks.length > 0
              ? tasks
              : [
                  { step_number: 1, title: "Add hello() function to pls_cli/please.py" },
                  { step_number: 2, title: "Add automated test for hello() in tests/test_pls_cli.py" },
                ]
            ).map((task, idx) => (
              <li key={idx} className="text-xs text-zinc-300 leading-relaxed flex items-start gap-2">
                <span className="text-zinc-400 font-mono shrink-0">{idx + 1}.</span>
                <span>
                  {task.title || `Task step ${idx + 1}`}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>

      {/* 8. Bottom Center Message Input Box */}
      <div className="pt-6 mt-6 border-t border-[#21262D]">
        <form
          onSubmit={handleBottomSubmit}
          className="bg-[#14181E] border border-[#27272A] rounded-xl p-3 focus-within:border-purple-500/80 transition-colors shadow-inner space-y-2"
        >
          <textarea
            rows={2}
            value={bottomInput}
            onChange={(e) => setBottomInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleBottomSubmit(e);
              }
            }}
            placeholder="Type your message..."
            className="w-full bg-transparent text-xs text-zinc-100 placeholder:text-zinc-500 font-sans focus:outline-none resize-none leading-relaxed"
          />

          <div className="flex items-center justify-between pt-1 border-t border-[#222226]">
            <span className="text-[10px] text-zinc-500 font-sans">
              Press Enter to send, Shift+Enter for new line
            </span>

            <button
              type="submit"
              disabled={!bottomInput.trim()}
              className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                bottomInput.trim()
                  ? "bg-purple-600 hover:bg-purple-500 text-white shadow-sm cursor-pointer"
                  : "bg-[#27272A] text-zinc-500 cursor-not-allowed"
              }`}
            >
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}