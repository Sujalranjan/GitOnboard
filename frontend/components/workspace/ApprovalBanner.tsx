"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  Terminal,
  XCircle,
} from "lucide-react";
import { ApprovalRequestItem } from "@/types/workspace";

interface ApprovalBannerProps {
  approvals: ApprovalRequestItem[];
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string, reason: string) => void;
  isLoading?: boolean;
}

export function ApprovalBanner({
  approvals,
  onApprove,
  onReject,
  isLoading = false,
}: ApprovalBannerProps) {
  const [rejectReason, setRejectReason] = useState<Record<string, string>>({});
  const [showRejectInput, setShowRejectInput] = useState<Record<string, boolean>>({});

  if (!approvals || approvals.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-md w-full space-y-2 pointer-events-auto font-mono">
      {approvals.map((req) => {
        const isCritical = req.risk_level === "CRITICAL" || req.risk_level === "HIGH";
        const hasRejectBox = showRejectInput[req.id];
        const reason = rejectReason[req.id] || "";

        return (
          <div
            key={req.id}
            className="bg-[#161B22] border-2 border-amber-500/80 rounded-xl p-4 shadow-2xl shadow-black/80 space-y-3 animate-in fade-in slide-in-from-bottom-5 duration-200"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-amber-400">
                <AlertTriangle className="w-5 h-5 animate-pulse shrink-0" />
                <span className="text-xs font-bold uppercase tracking-wider">
                  Approval Required (Phase 9 Safety)
                </span>
              </div>
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase border ${
                  isCritical
                    ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                    : "bg-amber-500/20 text-amber-300 border-amber-500/40"
                }`}
              >
                {req.risk_level} Risk
              </span>
            </div>

            <div className="space-y-1">
              <p className="text-xs text-white font-medium">{req.action_description}</p>
              {req.command && (
                <div className="bg-[#0D1117] p-2 rounded border border-[#30363D] text-[11px] text-cyan-300 flex items-center gap-1.5 overflow-x-auto">
                  <Terminal className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
                  <code>{req.command}</code>
                </div>
              )}
              {req.reason && (
                <p className="text-[11px] text-zinc-400">Reason: {req.reason}</p>
              )}
            </div>

            {hasRejectBox && (
              <div className="space-y-1 pt-1">
                <label className="text-[10px] text-zinc-400 uppercase">
                  Rejection explanation for agent:
                </label>
                <input
                  type="text"
                  value={reason}
                  onChange={(e) =>
                    setRejectReason((prev) => ({ ...prev, [req.id]: e.target.value }))
                  }
                  placeholder="e.g. Destructive operation not permitted"
                  className="w-full bg-[#0D1117] border border-amber-500/40 rounded px-2 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-amber-400"
                />
              </div>
            )}

            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={() => {
                  if (!hasRejectBox) {
                    setShowRejectInput((prev) => ({ ...prev, [req.id]: true }));
                  } else {
                    onReject(req.id, reason || "Operation rejected by user");
                  }
                }}
                disabled={isLoading}
                className="px-3 py-1.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-xs font-medium transition-all"
              >
                {hasRejectBox ? "Submit Rejection" : "Reject"}
              </button>

              <button
                onClick={() => onApprove(req.id)}
                disabled={isLoading}
                className="flex-1 px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium shadow-md transition-all flex items-center justify-center gap-1.5"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>Approve Action</span>
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
