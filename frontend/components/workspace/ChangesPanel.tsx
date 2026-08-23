"use client";

import React, { useState } from "react";
import {
  Check,
  ClipboardCopy,
  FileCode,
  FileDiff,
  FileMinus,
  FilePlus,
  Layers,
  Sparkles,
} from "lucide-react";
import { WorkspaceChangesData, WorkspaceSnapshot } from "@/types/workspace";

interface ChangesPanelProps {
  snapshot: WorkspaceSnapshot | null;
  activeFile?: string | null;
  onSelectFile?: (file: string) => void;
}

export function ChangesPanel({
  snapshot,
  activeFile,
  onSelectFile,
}: ChangesPanelProps) {
  const [copied, setCopied] = useState(false);
  const changes = snapshot?.changes;
  const modFiles = changes?.modified_files || [];
  const addFiles = changes?.added_files || [];
  const delFiles = changes?.deleted_files || [];
  const totalChanges = modFiles.length + addFiles.length + delFiles.length;
  const rawDiff = changes?.diff || "";

  const handleCopyDiff = () => {
    if (!rawDiff) return;
    navigator.clipboard.writeText(rawDiff);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (totalChanges === 0 && !rawDiff) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-zinc-500 font-mono text-center">
        <FileDiff className="w-10 h-10 mb-3 text-zinc-600 animate-pulse" />
        <p className="text-xs font-semibold text-zinc-400">No Changes Recorded</p>
        <p className="text-[11px] text-zinc-500 max-w-sm mt-1">
          Working tree is currently clean. Modifications by the agent will be tracked here in real time.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#0D1117] text-zinc-200 overflow-y-auto p-4 space-y-4 font-mono">
      {/* Changes Summary Header */}
      <div className="bg-[#161B22] p-3 rounded-lg border border-[#30363D] flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs">
          <span className="font-semibold text-white">Total Changed Files: {totalChanges}</span>
          <div className="flex items-center gap-2 text-[11px]">
            {modFiles.length > 0 && (
              <span className="text-amber-400 font-medium">~{modFiles.length} modified</span>
            )}
            {addFiles.length > 0 && (
              <span className="text-emerald-400 font-medium">+{addFiles.length} added</span>
            )}
            {delFiles.length > 0 && (
              <span className="text-rose-400 font-medium">-{delFiles.length} deleted</span>
            )}
          </div>
        </div>

        {rawDiff && (
          <button
            onClick={handleCopyDiff}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#0D1117] hover:bg-[#21262D] border border-[#30363D] text-[11px] text-zinc-300 transition-colors"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <ClipboardCopy className="w-3 h-3" />}
            <span>{copied ? "Copied" : "Copy Diff"}</span>
          </button>
        )}
      </div>

      {/* File List Grid */}
      <div className="space-y-1.5">
        <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
          Changed Files
        </span>

        {modFiles.map((f) => (
          <button
            key={f}
            onClick={() => onSelectFile && onSelectFile(f)}
            className={`w-full p-2 rounded flex items-center justify-between border text-left text-xs transition-colors ${
              activeFile === f
                ? "bg-purple-950/30 border-purple-500/50 text-white"
                : "bg-[#161B22] hover:bg-[#1C2128] border-[#30363D] text-zinc-300"
            }`}
          >
            <div className="flex items-center gap-2 truncate">
              <span className="w-4 text-center font-bold text-amber-400">M</span>
              <span className="truncate">{f}</span>
            </div>
            <FileCode className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
          </button>
        ))}

        {addFiles.map((f) => (
          <button
            key={f}
            onClick={() => onSelectFile && onSelectFile(f)}
            className={`w-full p-2 rounded flex items-center justify-between border text-left text-xs transition-colors ${
              activeFile === f
                ? "bg-purple-950/30 border-purple-500/50 text-white"
                : "bg-[#161B22] hover:bg-[#1C2128] border-[#30363D] text-zinc-300"
            }`}
          >
            <div className="flex items-center gap-2 truncate">
              <span className="w-4 text-center font-bold text-emerald-400">A</span>
              <span className="truncate">{f}</span>
            </div>
            <FilePlus className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          </button>
        ))}

        {delFiles.map((f) => (
          <div
            key={f}
            className="w-full p-2 rounded flex items-center justify-between border bg-[#161B22]/50 border-[#30363D]/50 text-zinc-500 text-xs"
          >
            <div className="flex items-center gap-2 truncate">
              <span className="w-4 text-center font-bold text-rose-400">D</span>
              <span className="truncate line-through">{f}</span>
            </div>
            <FileMinus className="w-3.5 h-3.5 text-rose-400 shrink-0" />
          </div>
        ))}
      </div>

      {/* Unified Diff Output Box */}
      {rawDiff && (
        <div className="space-y-1.5 flex-1 flex flex-col min-h-0">
          <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
            Unified Git Diff
          </span>
          <div className="bg-[#080B0E] p-3 rounded-lg border border-[#21262D] font-mono text-[11px] overflow-auto flex-1 leading-relaxed">
            <pre className="text-zinc-300 whitespace-pre">
              {rawDiff.split("\n").map((line, idx) => {
                let colorClass = "text-zinc-300";
                if (line.startsWith("+") && !line.startsWith("+++")) {
                  colorClass = "text-emerald-400 bg-emerald-950/30";
                } else if (line.startsWith("-") && !line.startsWith("---")) {
                  colorClass = "text-rose-400 bg-rose-950/30";
                } else if (line.startsWith("@@")) {
                  colorClass = "text-cyan-400";
                } else if (line.startsWith("diff") || line.startsWith("index")) {
                  colorClass = "text-zinc-500 font-bold";
                }
                return (
                  <div key={idx} className={colorClass}>
                    {line}
                  </div>
                );
              })}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
