"use client";

import React, { useState } from "react";
import {
  Terminal as TerminalIcon,
  AlertCircle,
  Play,
  Square,
  Columns,
  Trash2,
  Plus,
  ChevronDown,
  X,
} from "lucide-react";

import { RunState } from "@/types/workspace";

interface TerminalPanelProps {
  isOpen: boolean;
  onClose: () => void;
  runState?: RunState;
}

export function TerminalPanel({ isOpen, onClose, runState }: TerminalPanelProps) {
  const [activeTab, setActiveTab] = useState("TERMINAL");
  const [selectedShell, setSelectedShell] = useState("zsh");
  const [isShellDropdownOpen, setIsShellDropdownOpen] = useState(false);

  const [commandInput, setCommandInput] = useState("");
  const [logs, setLogs] = useState<string[]>([
    "\x1b[36m> next dev\x1b[0m",
    "  \x1b[35m▲ Next.js 16.2.10\x1b[0m",
    "  - Local:        \x1b[32mhttp://localhost:3000\x1b[0m",
    "  - Network:      \x1b[32mhttp://192.168.1.15:3000\x1b[0m",
    "",
    "\x1b[32m✓ Ready in 1.2s\x1b[0m",
    "\x1b[33m○ Compiling /src/pages/api/index.tsx ...\x1b[0m",
    "\x1b[32m✓ Compiled /src/pages/api/index.tsx in 142ms (420 modules)\x1b[0m",
    "\x1b[32m✓ GET /api/todos 200 in 18ms\x1b[0m",
    "\x1b[32m✓ POST /api/todos 201 in 24ms\x1b[0m",
  ]);

  if (!isOpen) return null;

  const handleCommandSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!commandInput.trim()) return;

    const newLogs = [...logs, `\x1b[34mgit:(main)✗\x1b[0m ${commandInput}`];

    if (commandInput.trim() === "clear") {
      setLogs([]);
      setCommandInput("");
      return;
    }

    if (commandInput.includes("npm test") || commandInput.includes("pytest")) {
      newLogs.push("Running verification test suite...");
      newLogs.push("\x1b[32m✓ 14 tests passed in 1.8s\x1b[0m");
    } else if (commandInput.includes("git status")) {
      newLogs.push("On branch main");
      newLogs.push("Changes not staged for commit:");
      newLogs.push("  \x1b[31mmodified:   src/pages/api/index.tsx\x1b[0m");
      newLogs.push("  \x1b[32mnew file:   src/pages/api/todos.ts\x1b[0m");
    } else {
      newLogs.push(`Executed: ${commandInput}`);
    }

    setLogs(newLogs);
    setCommandInput("");
  };

  const renderColorizedLog = (logLine: string) => {
    // Convert rudimentary ANSI escape strings to HTML styled spans
    let formatted = logLine
      .replace(/\x1b\[32m/g, '<span style="color: #22C55E;">')
      .replace(/\x1b\[35m/g, '<span style="color: #A855F7; font-weight: bold;">')
      .replace(/\x1b\[36m/g, '<span style="color: #06B6D4;">')
      .replace(/\x1b\[33m/g, '<span style="color: #F59E0B;">')
      .replace(/\x1b\[31m/g, '<span style="color: #EF4444;">')
      .replace(/\x1b\[34m/g, '<span style="color: #3B82F6;">')
      .replace(/\x1b\[0m/g, "</span>");

    return <span dangerouslySetInnerHTML={{ __html: formatted }} />;
  };

  return (
    <div className="h-48 bg-[#0A0D10] border-t border-[#2F343A] flex flex-col flex-shrink-0 select-none text-[#E6EDF3]">
      {/* Top Bar Tabs & Actions */}
      <div className="h-8 bg-[#14181E] border-b border-[#2F343A] flex items-center justify-between px-3 text-xs">
        {/* Left Tabs */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => setActiveTab("TERMINAL")}
            className={`h-full flex items-center gap-1.5 font-semibold transition-colors ${
              activeTab === "TERMINAL"
                ? "text-purple-400 border-b-2 border-purple-500"
                : "text-[#8B949E] hover:text-[#E6EDF3]"
            }`}
          >
            <TerminalIcon className="w-3.5 h-3.5" />
            <span>TERMINAL</span>
          </button>

          <button
            onClick={() => setActiveTab("PROBLEMS")}
            className={`h-full flex items-center gap-1.5 font-semibold transition-colors ${
              activeTab === "PROBLEMS"
                ? "text-purple-400 border-b-2 border-purple-500"
                : "text-[#8B949E] hover:text-[#E6EDF3]"
            }`}
          >
            <AlertCircle className="w-3.5 h-3.5 text-emerald-400" />
            <span>PROBLEMS</span>
            <span className="bg-purple-950 text-purple-300 text-[10px] px-1.5 py-0.2 rounded-full font-mono">
              3
            </span>
          </button>

          <button
            onClick={() => setActiveTab("OUTPUT")}
            className={`h-full flex items-center gap-1.5 font-semibold transition-colors ${
              activeTab === "OUTPUT"
                ? "text-purple-400 border-b-2 border-purple-500"
                : "text-[#8B949E] hover:text-[#E6EDF3]"
            }`}
          >
            <span>OUTPUT</span>
          </button>

          <button
            onClick={() => setActiveTab("DEBUG CONSOLE")}
            className={`h-full flex items-center gap-1.5 font-semibold transition-colors ${
              activeTab === "DEBUG CONSOLE"
                ? "text-purple-400 border-b-2 border-purple-500"
                : "text-[#8B949E] hover:text-[#E6EDF3]"
            }`}
          >
            <span>DEBUG CONSOLE</span>
          </button>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2 text-[#8B949E]">
          {/* Shell Dropdown */}
          <div className="relative">
            <button
              onClick={() => setIsShellDropdownOpen(!isShellDropdownOpen)}
              className="flex items-center gap-1 bg-[#0A0D10] px-2 py-0.5 rounded border border-[#2F343A] text-xs hover:text-[#E6EDF3] transition-colors"
            >
              <span className="font-mono">{selectedShell}</span>
              <ChevronDown className="w-3 h-3" />
            </button>

            {isShellDropdownOpen && (
              <div className="absolute right-0 bottom-full mb-1 w-24 bg-[#14181E] border border-[#2F343A] rounded shadow-xl py-1 z-50 text-xs font-mono">
                {["zsh", "bash", "node", "pwsh"].map((sh) => (
                  <button
                    key={sh}
                    onClick={() => {
                      setSelectedShell(sh);
                      setIsShellDropdownOpen(false);
                    }}
                    className="w-full text-left px-3 py-1 hover:bg-[#1E222A] text-[#E6EDF3]"
                  >
                    {sh}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button className="p-1 hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Split Terminal">
            <Columns className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setLogs([])}
            className="p-1 hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors"
            title="Clear Terminal"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          <button className="p-1 hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="New Terminal">
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onClose}
            className="p-1 hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors"
            title="Close Panel"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Terminal Content Area */}
      <div className="flex-1 p-3 font-mono text-xs overflow-y-auto space-y-1 bg-[#0A0D10]">
        {activeTab === "TERMINAL" && (
          <>
            {logs.map((line, idx) => (
              <div key={idx} className="leading-5">
                {renderColorizedLog(line)}
              </div>
            ))}

            {/* Git Prompt & Command Input */}
            <form onSubmit={handleCommandSubmit} className="flex items-center gap-2 pt-1">
              <span className="text-purple-400 font-bold">git:(<span className="text-emerald-400">main</span>)✗</span>
              <input
                type="text"
                value={commandInput}
                onChange={(e) => setCommandInput(e.target.value)}
                placeholder="npm run dev..."
                className="flex-1 bg-transparent text-[#E6EDF3] focus:outline-none font-mono text-xs"
              />
            </form>
          </>
        )}

        {activeTab === "PROBLEMS" && (
          <div className="space-y-2 text-xs font-mono">
            <div className="text-emerald-400 font-semibold">0 Errors, 3 Warnings</div>
            <div className="text-[#8B949E] pl-2 border-l-2 border-amber-500">
              [Warning] src/pages/api/index.tsx (Line 12): Unused variable &apos;input&apos; before submit handler.
            </div>
            <div className="text-[#8B949E] pl-2 border-l-2 border-amber-500">
              [Warning] src/pages/api/todos.ts (Line 8): Type implicit &apos;any&apos; on handler response interface.
            </div>
          </div>
        )}

        {activeTab === "OUTPUT" && (
          <div className="text-[#8B949E] font-mono text-xs">
            [Next.js Compiler Service] Listening on port 3000. Ready for hot replacement.
          </div>
        )}

        {activeTab === "DEBUG CONSOLE" && (
          <div className="text-[#8B949E] font-mono text-xs">
            Debugger attached. Process 48210 running.
          </div>
        )}
      </div>
    </div>
  );
}
