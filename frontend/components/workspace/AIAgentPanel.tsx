"use client";

import React from "react";
import {
  History,
  Plus,
  X,
} from "lucide-react";
import { RunState } from "@/types/workspace";
import { useAgentWorkspace } from "@/hooks/useAgentWorkspace";
import { ChatPanel } from "./ChatPanel";

interface AIAgentPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectFile: (filePath: string) => void;
  runState?: RunState;
  onStartTaskPrompt?: (prompt: string) => void;
  onTriggerRepair?: () => void;
  onOpenPlanInEditor?: (plan: any) => void;
  selectedPlanId?: string | null;
  agentWorkspace?: ReturnType<typeof useAgentWorkspace>;
  width?: number;
}

export function AIAgentPanel({
  isOpen,
  onClose,
  onSelectFile,
  runState,
  onStartTaskPrompt,
  onTriggerRepair,
  onOpenPlanInEditor,
  selectedPlanId,
  agentWorkspace: externalAgentWorkspace,
  width = 380,
}: AIAgentPanelProps) {
  const repoId = runState?.repoId || "default";
  const initialRunId = runState?.runId || null;

  const localWorkspace = useAgentWorkspace({
    initialRunId,
    repositoryId: repoId,
  });

  const workspace = externalAgentWorkspace || localWorkspace;

  const {
    snapshot,
    isLoading,
    startRun,
    approvePlan,
    rejectPlan,
    refreshSnapshot,
  } = workspace;

  if (!isOpen) return null;

  return (
    <div
      style={{ width }}
      className="h-full bg-[#0D1117] border-l border-[#21262D] flex flex-col overflow-hidden shrink-0 font-sans select-none"
    >
      {/* Top Clean Header */}
      <div className="border-b border-[#21262D] bg-[#161B22] px-3.5 py-2.5 flex items-center justify-between">
        <span className="text-xs font-semibold text-zinc-200 tracking-tight truncate">
          Agent Workspace Workflow Validation
        </span>

        <div className="flex items-center gap-1 shrink-0 text-zinc-400">
          <button
            onClick={() => refreshSnapshot()}
            title="New Chat Session"
            className="p-1 rounded hover:bg-[#21262D] hover:text-zinc-200 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => refreshSnapshot()}
            title="Session History"
            className="p-1 rounded hover:bg-[#21262D] hover:text-zinc-200 transition-colors"
          >
            <History className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onClose}
            title="Close panel"
            className="p-1 rounded hover:bg-[#21262D] hover:text-zinc-200 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Chat Body */}
      <div className="flex-1 overflow-hidden relative">
        <ChatPanel
          snapshot={snapshot}
          repoId={repoId}
          onStartRun={(prompt) => {
            startRun(prompt);
          }}
          onApprovePlan={approvePlan}
          onRejectPlan={rejectPlan}
          onOpenPlanInEditor={onOpenPlanInEditor}
          onSelectFile={onSelectFile}
          isLoading={isLoading}
        />
      </div>
    </div>
  );
}
