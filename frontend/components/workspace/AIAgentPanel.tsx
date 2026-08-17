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
}

export function AIAgentPanel({
  isOpen,
  onClose,
  onSelectFile,
  runState,
  onStartTaskPrompt,
  onTriggerRepair,
}: AIAgentPanelProps) {
  const [activeSubTab, setActiveSubTab] = useState<"chat" | "matrix" | "context">("chat");
  const [selectedModel, setSelectedModel] = useState("GPT-4o");
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [promptInput, setPromptInput] = useState("");

  const models = ["GPT-4o", "Claude 3.5 Sonnet", "Gemini 1.5 Pro", "Local Ollama"];

  const [messages, setMessages] = useState<
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
  >([
    {
      id: "1",
      sender: "user",
      text: "Add a new API route for managing user todos with GET and POST handlers.",
    },
    {
      id: "2",
      sender: "agent",
      text: "I've synthesized the Implementation Contract and created `src/pages/api/todos.ts`. Running multi-vector verification...",
      codeBlock: {
        fileName: "src/pages/api/todos.ts",
        code: `import type { NextApiRequest, NextApiResponse } from 'next';\n\ninterface Todo {\n  id: number;\n  text: string;\n  completed: boolean;\n}\n\nlet todosList: Todo[] = [\n  { id: 1, text: 'Initialize AI Workspace', completed: true },\n];\n\nexport default function handler(req: NextApiRequest, res: NextApiResponse) {\n  if (req.method === 'GET') {\n    return res.status(200).json(todosList);\n  }\n  if (req.method === 'POST') {\n    const { text } = req.body;\n    const newTodo: Todo = { id: Date.now(), text, completed: false };\n    todosList.push(newTodo);\n    return res.status(201).json(newTodo);\n  }\n  return res.status(405).end();\n}`,
      },
      quickActions: ["Trigger Repair Iteration", "View Contract Matrix"],
    },
  ]);

  if (!isOpen) return null;

  const handleSendMessage = (textToSend?: string) => {
    const query = textToSend || promptInput;
    if (!query.trim()) return;

    if (query.includes("Repair") || query.includes("Trigger Repair")) {
      if (onTriggerRepair) onTriggerRepair();
    } else if (query.includes("Matrix")) {
      setActiveSubTab("matrix");
    } else if (onStartTaskPrompt) {
      onStartTaskPrompt(query);
    }

    const userMsgId = Date.now().toString();
    setMessages((prev) => [...prev, { id: userMsgId, sender: "user", text: query }]);
    if (!textToSend) setPromptInput("");
  };

  const report = runState?.report;
  const contract = runState?.contract;
  const defects = report?.defects || [];
  const iteration = runState?.iteration || 0;

  // Triangulated evidence matrix counts
  const staticDefects = defects.filter((d) => (d.category || "").includes("STATIC"));
  const dynamicDefects = defects.filter((d) => (d.category || "").includes("DYNAMIC") || (d.category || "").includes("TEST"));
  const contractDefects = defects.filter((d) => (d.category || "").includes("CONTRACT"));

  return (
    <div className="w-80 bg-[#14181E] border-l border-[#2F343A] flex flex-col h-full select-none flex-shrink-0 text-[#E6EDF3]">
      {/* Top Bar Header */}
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
          <span className="font-bold text-xs tracking-wider text-white">VERIFICATION CONTROLLER</span>
        </div>

        <div className="flex items-center gap-1">
          <button className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Save Changes">
            <Save className="w-3.5 h-3.5" />
          </button>
          <button className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Commit Git">
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

      {/* Loading Bar */}
      {runState?.isLoading && (
        <div className="bg-purple-950/60 border-b border-purple-500/40 p-2 flex items-center gap-2 text-xs text-purple-200 animate-pulse">
          <RefreshCw className="w-3.5 h-3.5 animate-spin text-purple-400 flex-shrink-0" />
          <span>{runState.statusMessage || "Running verification mesh..."}</span>
        </div>
      )}

      {/* Main Content Body */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4 text-xs bg-[#14181E]">
        {/* SUB-PANEL 1: Contract Checklist */}
        {activeSubTab === "context" && (
          <div className="space-y-3">
            <div className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider flex items-center gap-1.5 border-b border-[#2F343A] pb-1.5">
              <ListChecks className="w-4 h-4 text-purple-400" />
              <span>Contract Verification Checklist</span>
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
                      <span>{comp}</span>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
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
                Submit a task prompt to synthesize an Implementation Contract.
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
              {/* 1. Static Check Card */}
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
                    <span>Static AST & Symbol Vector</span>
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
                    <span>Dynamic Test Execution Vector</span>
                  </div>
                  <div className="text-[10px] opacity-80 mt-0.5 font-mono">
                    Test Failures: {dynamicDefects.length} detected
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
                    <span>Implementation Contract Vector</span>
                  </div>
                  <div className="text-[10px] opacity-80 mt-0.5 font-mono">
                    Invariant Violations: {contractDefects.length} detected
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

            {/* SUB-PANEL 3: Adversarial Repair Timeline */}
            <div className="pt-2 space-y-2">
              <div className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>Adversarial Repair Timeline</span>
              </div>

              {/* Iteration Badges Timeline */}
              <div className="bg-[#0A0D10] border border-[#2F343A] p-2.5 rounded-lg space-y-2">
                <div className="flex items-center gap-2 text-[11px] font-mono">
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

                {/* Auto-Repair Diff Button */}
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

            {/* Chat Conversation History if activeSubTab === "chat" */}
            {activeSubTab === "chat" && (
              <div className="space-y-3 pt-2">
                {messages.map((msg) => (
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
                          {msg.quickActions && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {msg.quickActions.map((act, i) => (
                                <button
                                  key={i}
                                  onClick={() => handleSendMessage(act)}
                                  className="bg-purple-950 hover:bg-purple-900 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded text-[10px]"
                                >
                                  {act}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* User Input Prompt Bar */}
      <div className="p-3 bg-[#0A0D10] border-t border-[#2F343A] space-y-2 flex-shrink-0">
        <textarea
          rows={2}
          value={promptInput}
          onChange={(e) => setPromptInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
            }
          }}
          placeholder="Type feature requirement or repair prompt..."
          className="w-full bg-[#14181E] border border-[#2F343A] rounded-lg p-2 text-xs text-[#E6EDF3] placeholder-[#8B949E] focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 resize-none font-sans"
        />

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 text-[#8B949E]">
            <button className="p-1 hover:text-[#E6EDF3] rounded" title="Attach file">
              <Paperclip className="w-3.5 h-3.5" />
            </button>
            <button className="p-1 hover:text-[#E6EDF3] rounded" title="Copy">
              <ClipboardCopy className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleSendMessage()}
              disabled={runState?.isLoading}
              className="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white px-3 py-1 rounded-lg text-xs font-semibold shadow-md transition-all disabled:opacity-50 flex items-center gap-1"
            >
              <span>Send</span>
              <Send className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
