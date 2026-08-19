"use client";

import React, { useState } from "react";
import {
  Sparkles,
  Save,
  GitCommit,
  Rocket,
  MessageSquare,
  FileDiff,
  Layers,
  Paperclip,
  ClipboardCopy,
  Send,
  ChevronDown,
  CheckCircle2,
  AlertTriangle,
  FileCode,
  X,
  RefreshCw,
  ShieldCheck,
  ShieldAlert,
  Check,
  ListChecks,
  Activity,
  ArrowRight,
  Zap,
} from "lucide-react";
import { DefectItem, RunState } from "@/types/workspace";

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
  width = 340,
}: AIAgentPanelProps) {
  const [activeSubTab, setActiveSubTab] = useState<"chat" | "matrix" | "context">("chat");
  const [selectedModel, setSelectedModel] = useState("GPT-4o");
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [promptInput, setPromptInput] = useState("");

  const supportedModels = [
    { name: "GPT-4o", provider: "OpenAI" },
    { name: "Claude 3.5 Sonnet", provider: "Anthropic" },
    { name: "Gemini 1.5 Pro", provider: "Google" },
    { name: "Local Ollama (Llama 3.2)", provider: "Ollama" },
  ];

  const [chatMessages, setChatMessages] = useState<
    Array<{
      id: string;
      sender: "user" | "agent";
      text: string;
      codeBlock?: {
        fileName: string;
        code: string;
      };
      quickActions?: string[];
    }>
  >([]);

  if (!isOpen) return null;

  const handleSendMessage = (textToSend?: string) => {
    const query = textToSend || promptInput;
    if (!query.trim()) return;

    if (query.includes("Repair") || query.includes("Auto-Repair")) {
      if (onTriggerRepair) onTriggerRepair();
    } else if (query.includes("Matrix")) {
      setActiveSubTab("matrix");
    } else if (onStartTaskPrompt) {
      onStartTaskPrompt(query);
    }

    const userMsgId = Date.now().toString();
    setChatMessages((prev) => [...prev, { id: userMsgId, sender: "user", text: query }]);
    if (!textToSend) setPromptInput("");
  };

  const report = runState?.report;
  const contract = runState?.contract;
  const defects = report?.defects || [];
  const iteration = runState?.iteration || 0;

  // Evidence matrix defect categories
  const staticDefects = defects.filter((d) => (d.category || "").includes("STATIC") || (d.category || "").includes("SYMBOL") || (d.category || "").includes("IMPORT"));
  const dynamicDefects = defects.filter((d) => (d.category || "").includes("DYNAMIC") || (d.category || "").includes("TEST") || (d.category || "").includes("BUILD"));
  const contractDefects = defects.filter((d) => (d.category || "").includes("CONTRACT"));

  return (
    <div
      style={{ width: `${width}px` }}
      className="bg-[#14181E] border-l border-[#2F343A] flex flex-col h-full select-none flex-shrink-0 text-[#E6EDF3]"
    >
      {/* Top Header */}
      <div className="h-12 px-3 border-b border-[#2F343A] flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="relative flex items-center justify-center">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                runState?.isLoading
                  ? "bg-amber-400 animate-ping"
                  : report?.passed
                  ? "bg-emerald-500"
                  : "bg-purple-500 animate-pulse"
              }`}
            />
            <span
              className={`w-2 h-2 rounded-full ${
                runState?.isLoading
                  ? "bg-amber-400"
                  : report?.passed
                  ? "bg-emerald-500"
                  : "bg-purple-500"
              }`}
            />
          </div>
          <span className="font-bold text-xs tracking-wider text-white">AI VERIFICATION AGENT</span>
        </div>

        <div className="flex items-center gap-1">
          <button className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Save Changes">
            <Save className="w-3.5 h-3.5" />
          </button>
          <button className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Commit Changes">
            <GitCommit className="w-3.5 h-3.5" />
          </button>
          <button onClick={onClose} className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Close Panel">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Sub-Tabs: Chat, Matrix, Contract */}
      <div className="h-9 bg-[#0A0D10] border-b border-[#2F343A] flex items-center px-2 text-xs flex-shrink-0">
        <button
          onClick={() => setActiveSubTab("chat")}
          className={`flex-1 py-1.5 flex items-center justify-center gap-1.5 font-medium transition-colors border-b-2 ${
            activeSubTab === "chat"
              ? "text-purple-400 border-purple-500 font-semibold"
              : "text-[#8B949E] border-transparent hover:text-[#E6EDF3]"
          }`}
        >
          <MessageSquare className="w-3.5 h-3.5" />
          <span>Chat</span>
        </button>

        <button
          onClick={() => setActiveSubTab("matrix")}
          className={`flex-1 py-1.5 flex items-center justify-center gap-1.5 font-medium transition-colors border-b-2 ${
            activeSubTab === "matrix"
              ? "text-purple-400 border-purple-500 font-semibold"
              : "text-[#8B949E] border-transparent hover:text-[#E6EDF3]"
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          <span>Matrix</span>
          {defects.length > 0 && (
            <span className="bg-rose-950 text-rose-300 text-[10px] px-1.5 rounded-full font-mono">
              {defects.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveSubTab("context")}
          className={`flex-1 py-1.5 flex items-center justify-center gap-1.5 font-medium transition-colors border-b-2 ${
            activeSubTab === "context"
              ? "text-purple-400 border-purple-500 font-semibold"
              : "text-[#8B949E] border-transparent hover:text-[#E6EDF3]"
          }`}
        >
          <ListChecks className="w-3.5 h-3.5" />
          <span>Contract</span>
        </button>
      </div>

      {/* Real-time Status Loader */}
      {runState?.isLoading && (
        <div className="bg-purple-950/60 border-b border-purple-500/40 p-2 flex items-center gap-2 text-xs text-purple-200 animate-pulse">
          <RefreshCw className="w-3.5 h-3.5 animate-spin text-purple-400 flex-shrink-0" />
          <span>{runState.statusMessage || "Dispatching requirement..."}</span>
        </div>
      )}

      {/* Main Sub-Panel Body */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4 text-xs bg-[#14181E] scrollbar-thin">
        {/* SUB-PANEL 1: Contract Checklist */}
        {activeSubTab === "context" && (
          <div className="space-y-3">
            <div className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider flex items-center gap-1.5 border-b border-[#2F343A] pb-1.5">
              <ListChecks className="w-4 h-4 text-purple-400" />
              <span>Contract Checklist</span>
            </div>

            {contract ? (
              <div className="space-y-3">
                {/* Required Endpoints */}
                <div className="bg-[#0A0D10] border border-[#2F343A] p-2.5 rounded-lg space-y-1.5">
                  <div className="font-semibold text-purple-300 text-[11px] uppercase tracking-wider">
                    Required Endpoints
                  </div>
                  {contract.required_endpoints.map((ep, idx) => (
                    <div key={idx} className="flex items-center justify-between text-[11px] font-mono">
                      <span>{ep}</span>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    </div>
                  ))}
                </div>

                {/* Expected Components */}
                <div className="bg-[#0A0D10] border border-[#2F343A] p-2.5 rounded-lg space-y-1.5">
                  <div className="font-semibold text-purple-300 text-[11px] uppercase tracking-wider">
                    Expected Components
                  </div>
                  {contract.expected_components.map((comp, idx) => (
                    <div key={idx} className="flex items-center justify-between text-[11px] font-mono">
                      <span className="truncate">{comp}</span>
                      <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 ml-1" />
                    </div>
                  ))}
                </div>

                {/* Invariants & Validation */}
                <div className="bg-[#0A0D10] border border-[#2F343A] p-2.5 rounded-lg space-y-1.5">
                  <div className="font-semibold text-purple-300 text-[11px] uppercase tracking-wider">
                    Invariants & Rules
                  </div>
                  {contract.invariants.map((inv, idx) => {
                    const isViolated = defects.some((d) => (d.category || "").includes("CONTRACT"));
                    return (
                      <div key={idx} className="flex items-center justify-between text-[11px]">
                        <span>{inv}</span>
                        {isViolated ? (
                          <X className="w-3.5 h-3.5 text-rose-400 flex-shrink-0 ml-1" />
                        ) : (
                          <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 ml-1" />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="text-[#8B949E] text-xs italic">
                No active contract. Enter a prompt below to synthesize an Implementation Contract.
              </div>
            )}
          </div>
        )}

        {/* SUB-PANEL 2: Triangulated Evidence Matrix & Adversarial Repair */}
        {(activeSubTab === "matrix" || activeSubTab === "chat") && (
          <div className="space-y-3">
            <div className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider flex items-center justify-between border-b border-[#2F343A] pb-1.5">
              <span className="flex items-center gap-1.5">
                <Activity className="w-4 h-4 text-purple-400" />
                Triangulated Evidence Matrix
              </span>
              <span className="text-[10px] font-mono text-purple-300">3 Vectors</span>
            </div>

            {/* Matrix Cards */}
            <div className="grid grid-cols-1 gap-2">
              {/* 1. Static AST Check Card */}
              <div
                className={`p-2.5 rounded-lg border flex items-center justify-between ${
                  report?.static_passed
                    ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-300"
                    : "bg-rose-950/20 border-rose-500/30 text-rose-300"
                }`}
              >
                <div>
                  <div className="font-semibold text-xs flex items-center gap-1.5">
                    {report?.static_passed ? (
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <ShieldAlert className="w-4 h-4 text-rose-400" />
                    )}
                    <span>Static AST Check Card</span>
                  </div>
                  <div className="text-[10px] opacity-80 mt-0.5 font-mono">
                    Phantom Symbols: {staticDefects.length} detected
                  </div>
                </div>
                <span
                  className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                    report?.static_passed ? "bg-emerald-900/50 text-emerald-300" : "bg-rose-900/50 text-rose-300"
                  }`}
                >
                  {report?.static_passed ? "PASS" : "FAIL"}
                </span>
              </div>

              {/* 2. Dynamic Tests Card */}
              <div
                className={`p-2.5 rounded-lg border flex items-center justify-between ${
                  report?.dynamic_passed
                    ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-300"
                    : "bg-rose-950/20 border-rose-500/30 text-rose-300"
                }`}
              >
                <div>
                  <div className="font-semibold text-xs flex items-center gap-1.5">
                    {report?.dynamic_passed ? (
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <ShieldAlert className="w-4 h-4 text-rose-400" />
                    )}
                    <span>Dynamic Tests Card</span>
                  </div>
                  <div className="text-[10px] opacity-80 mt-0.5 font-mono">
                    Test Executions: {report?.dynamic_passed ? "All passed" : `${dynamicDefects.length} failed`}
                  </div>
                </div>
                <span
                  className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                    report?.dynamic_passed ? "bg-emerald-900/50 text-emerald-300" : "bg-rose-900/50 text-rose-300"
                  }`}
                >
                  {report?.dynamic_passed ? "PASS" : "FAIL"}
                </span>
              </div>

              {/* 3. Contract Verification Card */}
              <div
                className={`p-2.5 rounded-lg border flex items-center justify-between ${
                  report?.semantic_passed
                    ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-300"
                    : "bg-rose-950/20 border-rose-500/30 text-rose-300"
                }`}
              >
                <div>
                  <div className="font-semibold text-xs flex items-center gap-1.5">
                    {report?.semantic_passed ? (
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <ShieldAlert className="w-4 h-4 text-rose-400" />
                    )}
                    <span>Contract Verification Card</span>
                  </div>
                  <div className="text-[10px] opacity-80 mt-0.5 font-mono">
                    Semantic Violations: {contractDefects.length} detected
                  </div>
                </div>
                <span
                  className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                    report?.semantic_passed ? "bg-emerald-900/50 text-emerald-300" : "bg-rose-900/50 text-rose-300"
                  }`}
                >
                  {report?.semantic_passed ? "PASS" : "FAIL"}
                </span>
              </div>
            </div>

            {/* Adversarial Repair Timeline */}
            <div className="pt-2 space-y-2">
              <div className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>Adversarial Repair Timeline</span>
              </div>

              <div className="bg-[#0A0D10] border border-[#2F343A] p-2.5 rounded-lg space-y-2">
                <div className="flex items-center gap-1.5 text-[11px] font-mono flex-wrap">
                  <span className={`px-2 py-0.5 rounded font-bold ${defects.length > 0 ? "bg-rose-950 text-rose-300" : "bg-emerald-950 text-emerald-300"}`}>
                    Iteration {iteration || 1} ({defects.length > 0 ? `Failed: ${defects.length} defects` : "Passed"})
                  </span>

                  {iteration > 0 && report?.passed && (
                    <>
                      <ArrowRight className="w-3 h-3 text-purple-400" />
                      <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 font-bold">
                        Iteration {iteration} (Passed)
                      </span>
                    </>
                  )}
                </div>

                {/* Auto-Repair Button */}
                {defects.length > 0 && onTriggerRepair && (
                  <button
                    onClick={onTriggerRepair}
                    disabled={runState?.isLoading || iteration >= 3}
                    className="w-full mt-1 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-md shadow-purple-600/30 transition-all disabled:opacity-50"
                  >
                    <RefreshCw className="w-3.5 h-3.5 animate-spin-slow" />
                    <span>Auto-Repair Diff (Pass {iteration + 1}/3)</span>
                  </button>
                )}
              </div>
            </div>

            {/* Live Conversation Thread if activeSubTab === "chat" */}
            {activeSubTab === "chat" && (
              <div className="space-y-3 pt-2">
                {chatMessages.length === 0 ? (
                  <div className="p-3 bg-[#0A0D10] border border-[#2F343A] rounded-lg text-slate-400 text-xs italic">
                    No prompt dispatched yet. Type your requirement below to dispatch to FastAPI planning & verification backend.
                  </div>
                ) : (
                  chatMessages.map((msg) => (
                    <div key={msg.id} className="space-y-2">
                      {msg.sender === "user" ? (
                        <div className="flex items-start gap-2 justify-end">
                          <div className="bg-purple-600/25 border border-purple-500/40 text-[#E6EDF3] p-2.5 rounded-xl text-xs max-w-[85%] leading-relaxed">
                            {msg.text}
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start gap-2">
                          <div className="w-5 h-5 rounded-full bg-purple-600 text-white flex items-center justify-center flex-shrink-0 text-[10px]">
                            <Sparkles className="w-3 h-3" />
                          </div>
                          <div className="flex-1 bg-[#0A0D10] border border-[#2F343A] p-2.5 rounded-xl text-xs leading-relaxed">
                            {msg.text}
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* User Input & Model Selector */}
      <div className="p-3 bg-[#0A0D10] border-t border-[#2F343A] space-y-2 flex-shrink-0">
        <textarea
          rows={2}
          value={promptInput}
          onChange={(e) => setPromptInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
            } else if (e.key === "Tab") {
              e.preventDefault();
              const suggestions = [
                "Add a new API route for managing user todos with GET and POST handlers.",
                "Implement user authentication middleware with JWT tokens.",
                "Create unit tests for verification and database models.",
                "Refactor error handling to use standard HTTPException details.",
              ];
              if (!promptInput.trim()) {
                setPromptInput(suggestions[0]);
              } else {
                const match = suggestions.find((s) => s.toLowerCase().startsWith(promptInput.toLowerCase().trim()));
                if (match) {
                  setPromptInput(match);
                } else {
                  const nextIndex = (suggestions.findIndex((s) => s === promptInput) + 1) % suggestions.length;
                  setPromptInput(suggestions[nextIndex]);
                }
              }
            }
          }}
          placeholder="Enter feature requirement (Press Tab to autocomplete)..."
          className="w-full bg-[#14181E] border border-[#2F343A] rounded-lg p-2 text-xs text-[#E6EDF3] placeholder-[#8B949E] focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 resize-none font-sans"
        />

        <div className="flex items-center justify-between">
          {/* Model Selector Dropdown */}
          <div className="relative">
            <button
              onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}
              className="flex items-center gap-1.5 bg-[#14181E] hover:bg-[#1E222A] text-[11px] text-[#8B949E] hover:text-[#E6EDF3] px-2.5 py-1 rounded border border-[#2F343A] font-medium transition-colors"
            >
              <span>{selectedModel}</span>
              <ChevronDown className="w-3 h-3" />
            </button>

            {isModelDropdownOpen && (
              <div className="absolute left-0 bottom-full mb-1 w-48 bg-[#14181E] border border-[#2F343A] rounded shadow-xl py-1 z-50 text-xs">
                <div className="px-2 py-1 text-[10px] uppercase font-bold text-[#8B949E] border-b border-[#2F343A]">
                  Supported LLM Provider
                </div>
                {supportedModels.map((m) => (
                  <button
                    key={m.name}
                    onClick={() => {
                      setSelectedModel(m.name);
                      setIsModelDropdownOpen(false);
                    }}
                    className="w-full text-left px-3 py-1.5 hover:bg-[#1E222A] text-[#E6EDF3] flex items-center justify-between text-[11px]"
                  >
                    <span>{m.name}</span>
                    <span className="text-[9px] text-[#8B949E] uppercase">{m.provider}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => handleSendMessage()}
            disabled={runState?.isLoading}
            className="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white px-3 py-1 rounded-lg text-xs font-semibold shadow-md transition-all disabled:opacity-50 flex items-center gap-1"
          >
            <span>Dispatch</span>
            <Send className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
