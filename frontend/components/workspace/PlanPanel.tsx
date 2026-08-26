"use client";

import React from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Clock,
  ExternalLink,
  History,
  Layers,
  Sparkles,
} from "lucide-react";
import { ImplementationPlanData, WorkspaceSnapshot } from "@/types/workspace";

interface PlanHistoryItem extends ImplementationPlanData {
  created_at_formatted?: string;
}

interface PlanPanelProps {
  snapshot: WorkspaceSnapshot | null;
  planHistory?: ImplementationPlanData[];
  onOpenPlanInEditor?: (plan: ImplementationPlanData) => void;
  selectedPlanId?: string | null;
  isLoading?: boolean;
}

export function PlanPanel({
  snapshot,
  planHistory = [],
  onOpenPlanInEditor,
  selectedPlanId,
  isLoading = false,
}: PlanPanelProps) {
  // Combine authoritative active plan from snapshot with session history
  const activePlan = snapshot?.plan;
  
  // Deduplicate history items and ensure active plan is included
  const plansMap = new Map<string, ImplementationPlanData>();
  
  if (activePlan) {
    plansMap.set(activePlan.plan_id || `v${activePlan.version}`, activePlan);
  }
  
  planHistory.forEach((p) => {
    const key = p.plan_id || `v${p.version}`;
    if (!plansMap.has(key)) {
      plansMap.set(key, p);
    }
  });

  const allPlans = Array.from(plansMap.values()).sort((a, b) => (b.version || 0) - (a.version || 0));

  if (allPlans.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center select-none font-mono bg-[#0D1117] text-zinc-500">
        <History className="w-10 h-10 mb-3 text-zinc-600 animate-pulse" />
        <p className="text-xs font-semibold text-zinc-400">No Implementation Plans Yet</p>
        <p className="text-[11px] text-zinc-500 max-w-xs mt-1 leading-relaxed">
          Plans generated from implementation requests will appear here. Click any plan to inspect it in the main editor.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#0D1117] text-zinc-200 overflow-y-auto p-3.5 space-y-3 font-mono select-none">
      {/* Header */}
      <div className="flex items-center justify-between px-1 pb-1 border-b border-[#21262D]">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-purple-400" />
          <span className="text-xs font-bold text-white tracking-wider uppercase">
            Plan History
          </span>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#161B22] text-purple-300 border border-[#30363D] font-bold">
          {allPlans.length} {allPlans.length === 1 ? "Version" : "Versions"}
        </span>
      </div>

      <p className="text-[10px] text-zinc-400 px-1">
        Click any plan version to open and inspect in the main editor workspace.
      </p>

      {/* Plan History Items List */}
      <div className="space-y-2">
        {allPlans.map((planItem) => {
          const isCurrentActive = activePlan && (activePlan.plan_id === planItem.plan_id || activePlan.version === planItem.version);
          const isSelected = selectedPlanId === planItem.plan_id || (selectedPlanId === `v${planItem.version}`);
          const tasks = planItem.tasks || [];
          const taskCount = tasks.length || 1;
          const uniqueFiles = new Set<string>();
          tasks.forEach((t) => (t.affected_files || []).forEach((f) => uniqueFiles.add(f)));
          const fileCount = uniqueFiles.size || (planItem.architecture_context?.routes_count || 1);
          const riskCount = planItem.risks?.length || 0;
          const riskLevel = riskCount > 1 ? "Moderate" : "Low";
          const riskColor = riskCount > 1 ? "text-amber-400" : "text-emerald-400";

          return (
            <div
              key={planItem.plan_id || planItem.version}
              onClick={() => onOpenPlanInEditor?.(planItem)}
              className={`p-3 rounded-xl border transition-all cursor-pointer space-y-2 group ${
                isSelected
                  ? "bg-[#1C182A] border-purple-500/80 shadow-md shadow-purple-950/40"
                  : isCurrentActive
                  ? "bg-[#161B22] border-emerald-500/40 hover:border-emerald-500/80"
                  : "bg-[#14181E] border-[#30363D] hover:border-zinc-500/50 hover:bg-[#1A1F28]"
              }`}
            >
              {/* Top Row: Version Badge + Status */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isCurrentActive ? "bg-emerald-400 ring-2 ring-emerald-400/30 animate-pulse" : "bg-zinc-600"
                    }`}
                  />
                  <span className="text-xs font-bold font-mono text-white">
                    v{planItem.version || 1}
                  </span>
                  {isCurrentActive ? (
                    <span className="text-[9px] px-1.5 py-0.2 rounded font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                      CURRENT
                    </span>
                  ) : (
                    <span className="text-[9px] px-1.5 py-0.2 rounded font-mono bg-zinc-800 text-zinc-400 border border-zinc-700">
                      SUPERSEDED
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1 text-purple-400 group-hover:translate-x-0.5 transition-transform text-[11px]">
                  <span className="text-[10px]">Open in Editor</span>
                  <ArrowRight className="w-3 h-3" />
                </div>
              </div>

              {/* Requirement / Title */}
              <div className="text-xs text-zinc-200 font-sans font-medium line-clamp-2 leading-relaxed">
                {planItem.requirement || "Implementation Plan Specification"}
              </div>

              {/* Metrics Strip */}
              <div className="flex items-center justify-between text-[10px] text-zinc-400 pt-1 border-t border-zinc-800/80 font-mono">
                <div className="flex items-center gap-2">
                  <span>{taskCount} {taskCount === 1 ? "task" : "tasks"}</span>
                  <span className="text-zinc-600">·</span>
                  <span>{fileCount} {fileCount === 1 ? "file" : "files"}</span>
                  <span className="text-zinc-600">·</span>
                  <span className={riskColor}>{riskLevel} risk</span>
                </div>
                <span className="text-zinc-500 text-[9px] uppercase">
                  {planItem.status || "READY"}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
