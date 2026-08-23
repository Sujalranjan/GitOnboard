"use client";

import React from "react";
import {
  AlertCircle,
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  FileCode,
  RotateCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import { WorkspaceSnapshot } from "@/types/workspace";

interface VerificationPanelProps {
  snapshot: WorkspaceSnapshot | null;
  onSelectFile?: (file: string) => void;
}

export function VerificationPanel({ snapshot, onSelectFile }: VerificationPanelProps) {
  const verif = snapshot?.verification;
  const checks = verif?.checks || [];
  const defects = verif?.defects || [];
  const status = verif?.status || "NOT_STARTED";
  const passed = Boolean(verif?.passed);
  const summary = verif?.summary || "No verification checks executed yet.";

  // Filter repair events from latest_events
  const repairEvents = (snapshot?.latest_events || []).filter((e) => {
    const et = String(e?.event_type || (e as any)?.type || "");
    return et.startsWith("REPAIR_") || et.startsWith("DIAGNOSIS_");
  });

  if (status === "NOT_STARTED" && checks.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-zinc-500 font-mono text-center">
        <ShieldCheck className="w-10 h-10 mb-3 text-zinc-600 animate-pulse" />
        <p className="text-xs font-semibold text-zinc-400">Verification Not Started</p>
        <p className="text-[11px] text-zinc-500 max-w-sm mt-1">
          Multi-vector checks (Static AST, Dynamic Tests, Contract Verification, and Judge) will execute automatically after task implementation.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#0D1117] text-zinc-200 overflow-y-auto p-4 space-y-4 font-mono">
      {/* Verification Executive Summary Card */}
      <div
        className={`p-4 rounded-lg border space-y-2 ${
          passed
            ? "bg-emerald-950/20 border-emerald-500/40"
            : status === "FAILED"
            ? "bg-rose-950/20 border-rose-500/40"
            : "bg-[#161B22] border-[#30363D]"
        }`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {passed ? (
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
            ) : (
              <ShieldAlert className="w-5 h-5 text-rose-400" />
            )}
            <span className="text-xs font-bold uppercase tracking-wider text-white">
              Verification Verdict: {status}
            </span>
          </div>
          <span
            className={`text-[10px] px-2.5 py-0.5 rounded-full font-bold uppercase border ${
              passed
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                : "bg-rose-500/20 text-rose-300 border-rose-500/40"
            }`}
          >
            Judge: {passed ? "PASS" : "FAIL"}
          </span>
        </div>
        <p className="text-xs text-zinc-300">{summary}</p>
      </div>

      {/* Verification Check Vectors */}
      {checks.length > 0 && (
        <div className="space-y-2">
          <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
            Evaluated Verification Checks ({checks.length})
          </span>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {checks.map((chk: any, idx: number) => {
              const chkPassed = chk.status === "PASSED" || chk.passed === true;
              return (
                <div
                  key={chk.check_id || idx}
                  className="bg-[#161B22] p-3 rounded-lg border border-[#30363D] flex items-center justify-between"
                >
                  <div className="flex items-center gap-2 truncate">
                    {chkPassed ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                    )}
                    <div className="truncate">
                      <div className="text-xs font-medium text-zinc-200 truncate">
                        {chk.name || chk.check_type || "Verification Vector"}
                      </div>
                      <span className="text-[10px] text-zinc-500">{chk.vector_type || "check"}</span>
                    </div>
                  </div>

                  <span
                    className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${
                      chkPassed
                        ? "bg-emerald-500/10 text-emerald-400"
                        : "bg-rose-500/10 text-rose-400"
                    }`}
                  >
                    {chk.status || (chkPassed ? "PASSED" : "FAILED")}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Captured Defects List */}
      {defects.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-rose-400">
            <AlertOctagon className="w-4 h-4" />
            <span className="text-[11px] font-semibold uppercase tracking-wider">
              Normalized Defects ({defects.length})
            </span>
          </div>

          <div className="space-y-2">
            {defects.map((d: any, idx: number) => (
              <div
                key={d.id || idx}
                className="bg-rose-950/20 border border-rose-500/30 p-3 rounded-lg space-y-1.5"
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-rose-300 font-mono">
                    {d.type || d.category || "DEFECT"}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400 font-bold">
                    {d.severity || "HIGH"}
                  </span>
                </div>

                <p className="text-xs text-zinc-300">{d.message || d.description}</p>

                {d.file && (
                  <button
                    onClick={() => onSelectFile && onSelectFile(d.file)}
                    className="text-[11px] text-blue-400 hover:text-blue-300 flex items-center gap-1 mt-1 transition-colors"
                  >
                    <FileCode className="w-3 h-3" />
                    <span>
                      {d.file}
                      {d.line ? `:${d.line}` : ""}
                    </span>
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Live Phase 8 Repair Activity Cards */}
      {repairEvents.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-amber-400">
            <RotateCw className="w-4 h-4 animate-spin" />
            <span className="text-[11px] font-semibold uppercase tracking-wider">
              Phase 8 Diagnosis & Repair Loop
            </span>
          </div>

          <div className="space-y-2">
            {repairEvents.map((re, idx) => (
              <div
                key={re.event_id || idx}
                className="bg-[#161B22] border border-amber-500/30 p-2.5 rounded text-xs space-y-1"
              >
                <div className="flex items-center justify-between text-[10px] text-amber-400 font-semibold">
                  <span>{re.event_type}</span>
                  <span className="text-zinc-500">
                    {re.created_at ? new Date(re.created_at).toLocaleTimeString() : ""}
                  </span>
                </div>
                <p className="text-zinc-300 text-[11px]">{re.message}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
