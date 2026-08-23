"use client";

import React, { useState } from "react";
import {
  Activity,
  CheckCircle2,
  FileCode,
  FileDiff,
  Layers,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import { AgentWorkspaceView, RunState } from "@/types/workspace";
import { useAgentWorkspace } from "@/hooks/useAgentWorkspace";
import { ChatPanel } from "./ChatPanel";
import { PlanPanel } from "./PlanPanel";
import { TaskPanel } from "./TaskPanel";
import { ChangesPanel } from "./ChangesPanel";
import { VerificationPanel } from "./VerificationPanel";
import { ApprovalBanner } from "./ApprovalBanner";

interface AIAgentPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectFile: (filePath: string) => void;
  runState?: RunState;
  onStartTaskPrompt?: (prompt: string) => void;
  onTriggerRepair?: () => void;
  width?: number;
}

export function AIAgentPanel({
  isOpen,
  onClose,
  onSelectFile,
  runState,
  onStartTaskPrompt,
  onTriggerRepair,
  width = 380,
}: AIAgentPanelProps) {
  const repoId = runState?.repoId || "default";
  const initialRunId = runState?.runId || null;

  // Consume Phase 10 Agent Workspace Hook
  const {
    snapshot,
    activeView,
    setActiveView,
    connectionStatus,
    isLoading,
    startRun,
    approvePlan,
    rejectPlan,
    approveAction,
    rejectAction,
    cancelRun,
    refreshSnapshot,
  } = useAgentWorkspace({
    initialRunId,
    repositoryId: repoId,
  });

  if (!isOpen) return null;

  const pendingApprovals = snapshot?.pending_approvals || [];
  const isAwaitingPlanApproval =
    snapshot?.run?.current_state === "AWAITING_APPROVAL" ||
    snapshot?.plan?.status === "READY_FOR_APPROVAL";

  return (
    <div
      style={{ width }}
      className="h-full bg-[#0D1117] border-l border-[#21262D] flex flex-col overflow-hidden shrink-0 font-mono select-none"
    >
      {/* Top Header & View Navigation Tabs */}
      <div className="border-b border-[#21262D] bg-[#161B22] p-2 space-y-2">
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-purple-600 text-white flex items-center justify-center shadow-sm">
              <Zap className="w-3 h-3" />
            </div>
            <span className="text-xs font-semibold text-white tracking-wider uppercase">
              Agent Workspace
            </span>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={refreshSnapshot}
              title="Refresh Workspace Snapshot"
              className="p-1 rounded hover:bg-[#21262D] text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onClose}
              title="Close panel"
              className="p-1 rounded hover:bg-[#21262D] text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* 5 Primary View Tabs */}
        <div className="flex items-center gap-1 bg-[#0D1117] p-1 rounded-lg border border-[#30363D]">
          <button
            onClick={() => setActiveView("chat")}
            className={`flex-1 py-1 px-1.5 rounded text-[11px] font-medium flex items-center justify-center gap-1 transition-all ${
              activeView === "chat"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-[#161B22]"
            }`}
          >
            <MessageSquare className="w-3 h-3" />
            <span>Chat</span>
          </button>

          <button
            onClick={() => setActiveView("plan")}
            className={`flex-1 py-1 px-1.5 rounded text-[11px] font-medium flex items-center justify-center gap-1 relative transition-all ${
              activeView === "plan"
                ? "bg-purple-600 text-white shadow-sm"
                : isAwaitingPlanApproval
                ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-[#161B22]"
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>Plan</span>
            {isAwaitingPlanApproval && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping absolute top-1 right-1" />
            )}
          </button>

          <button
            onClick={() => setActiveView("tasks")}
            className={`flex-1 py-1 px-1.5 rounded text-[11px] font-medium flex items-center justify-center gap-1 transition-all ${
              activeView === "tasks"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-[#161B22]"
            }`}
          >
            <Activity className="w-3 h-3" />
            <span>Tasks</span>
          </button>

          <button
            onClick={() => setActiveView("changes")}
            className={`flex-1 py-1 px-1.5 rounded text-[11px] font-medium flex items-center justify-center gap-1 transition-all ${
              activeView === "changes"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-[#161B22]"
            }`}
          >
            <FileDiff className="w-3 h-3" />
            <span>Diff</span>
          </button>

          <button
            onClick={() => setActiveView("verify")}
            className={`flex-1 py-1 px-1.5 rounded text-[11px] font-medium flex items-center justify-center gap-1 transition-all ${
              activeView === "verify"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-[#161B22]"
            }`}
          >
            <ShieldCheck className="w-3 h-3" />
            <span>Verify</span>
          </button>
        </div>
      </div>

      {/* Main Surface View Content */}
      <div className="flex-1 overflow-hidden relative">
        {activeView === "chat" && (
          <ChatPanel
            snapshot={snapshot}
            onStartRun={(prompt) => {
              startRun(prompt);
            }}
            onApprovePlan={approvePlan}
            onRejectPlan={rejectPlan}
            onNavigateToPlan={() => setActiveView("plan")}
            onSelectFile={onSelectFile}
            isLoading={isLoading}
          />
        )}

        {activeView === "plan" && (
          <PlanPanel
            snapshot={snapshot}
            onApprovePlan={approvePlan}
            onRejectPlan={rejectPlan}
            onSelectFile={onSelectFile}
            isLoading={isLoading}
          />
        )}

        {activeView === "tasks" && (
          <TaskPanel snapshot={snapshot} onSelectFile={onSelectFile} />
        )}

        {activeView === "changes" && (
          <ChangesPanel
            snapshot={snapshot}
            activeFile={runState?.taskPrompt}
            onSelectFile={onSelectFile}
          />
        )}

        {activeView === "verify" && (
          <VerificationPanel snapshot={snapshot} onSelectFile={onSelectFile} />
        )}

        {/* Phase 9 Inline Approval Modal / Banner */}
        <ApprovalBanner
          approvals={pendingApprovals}
          onApprove={approveAction}
          onReject={rejectAction}
          isLoading={isLoading}
        />
      </div>
    </div>
  );
}
