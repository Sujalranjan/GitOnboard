"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ArrowUp,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Compass,
  FileCode,
  FileDiff,
  HelpCircle,
  Info,
  Layers,
  MessageSquare,
  Mic,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Square,
  Terminal,
  User,
  Wrench,
  Zap,
} from "lucide-react";
import { EventStreamItem, WorkspaceSnapshot } from "@/types/workspace";

interface ChatPanelProps {
  snapshot: WorkspaceSnapshot | null;
  onStartRun: (prompt: string) => void;
  onApprovePlan?: () => void;
  onRejectPlan?: (reason?: string) => void;
  onNavigateToPlan?: () => void;
  onApproveAction?: (approvalId: string) => void;
  onRejectAction?: (approvalId: string, reason: string) => void;
  onSelectFile?: (file: string) => void;
  isLoading?: boolean;
}

interface IntentInfo {
  intent: "chat" | "explore" | "explain" | "plan" | "implement" | "clarify" | string;
  confidence: number;
  reason?: string;
  method?: string;
}

export function ChatPanel({
  snapshot,
  onStartRun,
  onApprovePlan,
  onRejectPlan,
  onNavigateToPlan,
  onApproveAction,
  onRejectAction,
  onSelectFile,
  isLoading = false,
}: ChatPanelProps) {
  const [inputPrompt, setInputPrompt] = useState("");
  const [selectedModel, setSelectedModel] = useState("Gemini 3.7 Flash");
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [expandedEvents, setExpandedEvents] = useState<Record<string, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const events = snapshot?.latest_events || [];
  const run = snapshot?.run;
  const plan = snapshot?.plan;
  const changes = snapshot?.changes;
  const pendingApprovals = snapshot?.pending_approvals || [];
  const isAwaitingApproval =
    run?.current_state === "AWAITING_APPROVAL" ||
    plan?.status === "READY_FOR_APPROVAL";

  const isRunning = Boolean(
    run?.id &&
    run.current_state !== "COMPLETED" &&
    run.current_state !== "CANCELLED" &&
    run.current_state !== "FAILED"
  );

  // Extract classified intent from events or run metadata
  const intentEvent = events.find((e) => e.event_type === "INTENT_CLASSIFIED");
  const agentMessageEvent = events.find((e) => e.event_type === "AGENT_MESSAGE");

  const classifiedIntent: IntentInfo | null = (() => {
    if (intentEvent?.payload?.intent) {
      return {
        intent: String(intentEvent.payload.intent).toLowerCase(),
        confidence: Number(intentEvent.payload.confidence ?? 1.0),
        reason: intentEvent.payload.reason || intentEvent.message,
        method: intentEvent.payload.method || "deterministic",
      };
    }
    const metaIntent = run?.metadata?.intent;
    if (metaIntent?.intent) {
      return {
        intent: String(metaIntent.intent).toLowerCase(),
        confidence: Number(metaIntent.confidence ?? 1.0),
        reason: metaIntent.reason,
        method: metaIntent.classification_method || "deterministic",
      };
    }
    return null;
  })();

  const agentResponseText: string | null = (() => {
    if (agentMessageEvent?.payload?.response || agentMessageEvent?.message) {
      return agentMessageEvent.payload?.response || agentMessageEvent.message;
    }
    if (run?.metadata?.response) {
      return String(run.metadata.response);
    }
    return null;
  })();

  // Sample prompt test presets for instant user evaluation
  const testPresets = [
    { label: "Greeting", prompt: "hi", icon: Sparkles, intent: "chat" },
    { label: "Explain", prompt: "how does authentication work?", icon: Info, intent: "explain" },
    { label: "Explore", prompt: "show repo tree", icon: Compass, intent: "explore" },
    { label: "Plan", prompt: "what would it take to add payments?", icon: Layers, intent: "plan" },
    { label: "Implement", prompt: "add Google OAuth", icon: Zap, intent: "implement" },
    { label: "Clarify", prompt: "make auth better", icon: HelpCircle, intent: "clarify" },
  ];

  // Auto-scroll to bottom on new events
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length, isAwaitingApproval, classifiedIntent?.intent]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputPrompt.trim() || isLoading || isRunning) return;
    onStartRun(inputPrompt.trim());
    setInputPrompt("");
  };

  const handlePresetClick = (presetPrompt: string) => {
    if (isLoading || isRunning) return;
    onStartRun(presetPrompt);
    setInputPrompt("");
  };

  const toggleEventExpand = (id: string) => {
    setExpandedEvents((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Helper for Intent theme styles
  const getIntentStyle = (intentKey?: string) => {
    switch (intentKey?.toLowerCase()) {
      case "chat":
        return {
          bg: "bg-emerald-500/10",
          border: "border-emerald-500/30",
          text: "text-emerald-400",
          badgeBg: "bg-emerald-500/20",
          title: "CHAT INTENT",
          desc: "Conversational greeting or chit-chat (Zero mutation, safe terminal)",
          icon: Sparkles,
        };
      case "explore":
        return {
          bg: "bg-cyan-500/10",
          border: "border-cyan-500/30",
          text: "text-cyan-400",
          badgeBg: "bg-cyan-500/20",
          title: "EXPLORE INTENT",
          desc: "Codebase exploration & symbol lookup (Read-only terminal)",
          icon: Compass,
        };
      case "explain":
        return {
          bg: "bg-blue-500/10",
          border: "border-blue-500/30",
          text: "text-blue-400",
          badgeBg: "bg-blue-500/20",
          title: "EXPLAIN INTENT",
          desc: "Architecture & conceptual explanation (Read-only terminal)",
          icon: Info,
        };
      case "plan":
        return {
          bg: "bg-amber-500/10",
          border: "border-amber-500/30",
          text: "text-amber-400",
          badgeBg: "bg-amber-500/20",
          title: "PLAN INTENT",
          desc: "High-level change estimation & DAG plan synthesis",
          icon: Layers,
        };
      case "implement":
        return {
          bg: "bg-purple-500/10",
          border: "border-purple-500/30",
          text: "text-purple-400",
          badgeBg: "bg-purple-500/20",
          title: "IMPLEMENT INTENT",
          desc: "Concrete code modification & feature implementation",
          icon: Zap,
        };
      case "clarify":
      default:
        return {
          bg: "bg-rose-500/10",
          border: "border-rose-500/30",
          text: "text-rose-400",
          badgeBg: "bg-rose-500/20",
          title: "CLARIFY INTENT",
          desc: "Ambiguous or underspecified request (Safe clarification prompt)",
          icon: HelpCircle,
        };
    }
  };

  const renderEventCard = (evt: EventStreamItem, idx: number) => {
    const type = String(evt?.event_type || (evt as any)?.type || "");
    const evtId = evt.event_id || `evt-${idx}`;
    const isExpanded = Boolean(expandedEvents[evtId]);

    // Skip redundant intent or message events in raw timeline since they are highlighted in dedicated cards
    if (type === "INTENT_CLASSIFIED" || type === "AGENT_MESSAGE") {
      return null;
    }

    // 1. Tool Call Execution Card
    if (type === "TOOL_CALL_STARTED" || type === "TOOL_CALL_COMPLETED" || evt.payload?.command) {
      const cmd = evt.payload?.command || evt.payload?.tool_name || evt.message;
      return (
        <div
          key={evtId}
          className="bg-[#18181B] border border-[#27272A] rounded-lg overflow-hidden font-mono text-xs my-2 transition-all shadow-sm"
        >
          <div
            onClick={() => toggleEventExpand(evtId)}
            className="px-3 py-2 bg-[#121214] flex items-center justify-between cursor-pointer hover:bg-[#1A1A1E] text-zinc-300 select-none"
          >
            <div className="flex items-center gap-2 truncate">
              <Terminal className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
              <span className="text-[11px] text-zinc-300 truncate">{cmd}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-zinc-500">
                {type === "TOOL_CALL_COMPLETED" ? "completed" : "running"}
              </span>
              <ChevronRight
                className={`w-3.5 h-3.5 text-zinc-500 transition-transform ${
                  isExpanded ? "rotate-90" : ""
                }`}
              />
            </div>
          </div>
          {isExpanded && evt.payload && (
            <div className="p-3 bg-[#0F0F11] border-t border-[#27272A] text-[11px] text-zinc-400 overflow-x-auto">
              <pre className="whitespace-pre font-mono">
                {JSON.stringify(evt.payload, null, 2)}
              </pre>
            </div>
          )}
        </div>
      );
    }

    // 2. State Transition pill
    if (type === "STATE_TRANSITION") {
      return (
        <div
          key={evtId}
          className="flex items-center gap-2 text-zinc-400 text-xs py-1 px-1 font-sans"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-purple-500" />
          <span className="text-zinc-300 text-[11px] font-mono">{evt.message}</span>
        </div>
      );
    }

    // 3. Plan Ready for Approval
    if (type === "PLANNING_COMPLETED" || type === "PLAN_READY_FOR_APPROVAL") {
      return (
        <div
          key={evtId}
          className="bg-[#18181B] border border-purple-500/30 rounded-lg p-3 my-2 space-y-1.5 font-sans"
        >
          <div className="flex items-center gap-2 text-purple-300 text-xs font-semibold">
            <Layers className="w-4 h-4 text-purple-400" />
            <span>Implementation Plan Synthesized</span>
          </div>
          <p className="text-xs text-zinc-300 font-mono leading-relaxed">{evt.message}</p>
        </div>
      );
    }

    // Default minor timeline event
    return (
      <div
        key={evtId}
        className="flex gap-2 text-xs py-1 px-2 bg-[#18181B]/40 rounded border border-[#27272A]/40 my-1 font-sans"
      >
        <div className="w-3.5 h-3.5 rounded bg-zinc-800 text-zinc-400 flex items-center justify-center shrink-0 mt-0.5">
          <Activity className="w-2 h-2" />
        </div>
        <div className="flex-1 text-zinc-400 font-mono text-[10px] leading-relaxed">
          {evt.message}
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-[#0F0F12] text-zinc-200 font-sans select-none">
      {/* Top Conversation Header */}
      <div className="px-3.5 py-2.5 border-b border-[#27272A] bg-[#141417] flex items-center justify-between">
        <div className="flex items-center gap-2 truncate">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs font-medium text-zinc-100 truncate">
            {run?.user_requirement ? run.user_requirement.slice(0, 45) + "..." : "Intent Classification Session"}
          </span>
        </div>
        <div className="flex items-center gap-1 text-zinc-400">
          <button
            onClick={() => onStartRun("")}
            title="Reset Session"
            className="p-1 hover:bg-[#27272A] hover:text-zinc-200 rounded transition-colors text-xs flex items-center gap-1"
          >
            <Plus className="w-3.5 h-3.5" />
            <span className="text-[10px]">New</span>
          </button>
        </div>
      </div>

      {/* Main Conversation & Intent Display Scroll Area */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
        {/* User Prompt Message */}
        {run?.user_requirement ? (
          <div className="flex gap-3 bg-[#18181B] p-3 rounded-xl border border-[#27272A] shadow-sm">
            <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center shrink-0 text-xs font-semibold">
              <User className="w-3.5 h-3.5" />
            </div>
            <div className="flex-1 space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-zinc-200">You</span>
                <span className="text-[10px] text-zinc-500 font-mono">
                  {run.started_at ? new Date(run.started_at).toLocaleTimeString() : "just now"}
                </span>
              </div>
              <p className="text-xs text-zinc-200 leading-relaxed font-sans">
                {run.user_requirement}
              </p>
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-zinc-500 space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-purple-600/10 border border-purple-500/20 flex items-center justify-center text-purple-400 shadow-inner">
              <Bot className="w-6 h-6" />
            </div>
            <div className="space-y-1.5 max-w-sm">
              <p className="text-sm font-semibold text-zinc-200">Intent Classification & Router</p>
              <p className="text-xs text-zinc-400 leading-relaxed">
                Ask any question or command below. The system will classify your request into <span className="text-emerald-400 font-mono">CHAT</span>, <span className="text-cyan-400 font-mono">EXPLORE</span>, <span className="text-blue-400 font-mono">EXPLAIN</span>, <span className="text-amber-400 font-mono">PLAN</span>, <span className="text-purple-400 font-mono">IMPLEMENT</span>, or <span className="text-rose-400 font-mono">CLARIFY</span>.
              </p>
            </div>

            {/* Quick Test Chips */}
            <div className="w-full max-w-md pt-2">
              <div className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider mb-2">
                Click a test question to test intent classification:
              </div>
              <div className="grid grid-cols-2 gap-1.5 text-left">
                {testPresets.map((preset) => {
                  const style = getIntentStyle(preset.intent);
                  const Icon = preset.icon;
                  return (
                    <button
                      key={preset.prompt}
                      onClick={() => handlePresetClick(preset.prompt)}
                      disabled={isLoading || isRunning}
                      className={`p-2 rounded-lg border ${style.border} ${style.bg} hover:brightness-125 transition-all text-left flex items-start gap-2 group cursor-pointer`}
                    >
                      <Icon className={`w-3.5 h-3.5 ${style.text} shrink-0 mt-0.5`} />
                      <div className="truncate">
                        <div className={`text-[10px] font-bold ${style.text}`}>
                          {preset.label}
                        </div>
                        <div className="text-[11px] text-zinc-300 truncate font-mono">
                          "{preset.prompt}"
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Dedicated Classified Intent Badge & Card */}
        {classifiedIntent && (
          <div
            className={`rounded-xl p-3.5 border ${
              getIntentStyle(classifiedIntent.intent).border
            } ${getIntentStyle(classifiedIntent.intent).bg} space-y-2 shadow-lg animate-in fade-in duration-200`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {React.createElement(getIntentStyle(classifiedIntent.intent).icon, {
                  className: `w-4 h-4 ${getIntentStyle(classifiedIntent.intent).text}`,
                })}
                <span
                  className={`text-xs font-bold font-mono tracking-wider ${
                    getIntentStyle(classifiedIntent.intent).text
                  }`}
                >
                  {getIntentStyle(classifiedIntent.intent).title}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-900/80 text-zinc-300 border border-zinc-700/60 font-mono">
                  {(classifiedIntent.confidence * 100).toFixed(0)}% Confidence
                </span>
              </div>
              <span className="text-[10px] text-zinc-400 font-mono capitalize">
                {classifiedIntent.method || "deterministic"}
              </span>
            </div>

            <p className="text-xs text-zinc-300 font-sans leading-relaxed">
              {classifiedIntent.reason || getIntentStyle(classifiedIntent.intent).desc}
            </p>
          </div>
        )}

        {/* Assistant Response Message Card (For CHAT, EXPLORE, EXPLAIN, CLARIFY) */}
        {agentResponseText && (
          <div className="flex gap-3 bg-[#161B22] p-3.5 rounded-xl border border-[#30363D] shadow-sm">
            <div className="w-6 h-6 rounded-full bg-purple-600/30 border border-purple-500/40 text-purple-300 flex items-center justify-center shrink-0 text-xs font-semibold">
              <Bot className="w-3.5 h-3.5" />
            </div>
            <div className="flex-1 space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-zinc-200">Repository Intelligence Assistant</span>
                <span className="text-[10px] text-emerald-400 font-mono">Response Delivered</span>
              </div>
              <p className="text-xs text-zinc-200 leading-relaxed font-sans whitespace-pre-wrap">
                {agentResponseText}
              </p>
            </div>
          </div>
        )}

        {/* Implementation Plan Card (For PLAN and IMPLEMENT) */}
        {(isAwaitingApproval || plan) && (
          <div className="bg-[#161B22] border border-purple-500/50 rounded-xl p-4 space-y-3.5 shadow-xl my-3 animate-in fade-in duration-300">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-md bg-purple-600/30 text-purple-300 flex items-center justify-center border border-purple-500/40 shadow-inner">
                  <Layers className="w-3.5 h-3.5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-zinc-100">Implementation Plan</span>
                    <span className="text-[10px] px-1.5 py-0.2 bg-zinc-800 text-zinc-400 rounded font-mono">
                      v{plan?.version || 1}
                    </span>
                  </div>
                  <span className="text-[10px] text-zinc-400 font-sans">
                    {snapshot?.tasks?.length || plan?.tasks?.length || 0} discrete DAG tasks
                  </span>
                </div>
              </div>
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium border ${
                  isAwaitingApproval
                    ? "bg-amber-500/10 text-amber-400 border-amber-500/30 animate-pulse"
                    : "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                }`}
              >
                {isAwaitingApproval ? "Awaiting Approval" : "Approved"}
              </span>
            </div>

            {/* Clickable Plan Artifact Pill */}
            <button
              type="button"
              onClick={() => onSelectFile?.("implementation_plan.md")}
              className="w-full bg-[#0D1117] hover:bg-[#21262D] border border-[#30363D] hover:border-purple-500/60 rounded-lg p-2.5 flex items-center justify-between text-left group transition-all"
              title="Open implementation_plan.md in Editor"
            >
              <div className="flex items-center gap-2.5 overflow-hidden">
                <FileCode className="w-4 h-4 text-purple-400 group-hover:text-purple-300 shrink-0" />
                <div className="truncate">
                  <div className="text-[11px] font-semibold text-zinc-200 group-hover:text-white truncate">
                    implementation_plan.md
                  </div>
                  <div className="text-[10px] text-zinc-500 group-hover:text-zinc-400 truncate">
                    {plan?.requirement || run?.user_requirement || "Plan specifications & acceptance criteria"}
                  </div>
                </div>
              </div>
              <span className="text-[10px] text-purple-400 group-hover:text-purple-300 flex items-center gap-1 font-sans shrink-0">
                <span>Open in editor</span>
                <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </span>
            </button>

            {/* Tasks Preview List */}
            {snapshot?.tasks && snapshot.tasks.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <div className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">
                  Task Pipeline Preview
                </div>
                <div className="space-y-1 max-h-32 overflow-y-auto pr-1">
                  {snapshot.tasks.map((t, idx) => (
                    <div
                      key={t.task_id || idx}
                      onClick={() => {
                        if (t.affected_files && t.affected_files.length > 0) {
                          onSelectFile?.(t.affected_files[0]);
                        } else {
                          onSelectFile?.("implementation_plan.md");
                        }
                      }}
                      className="bg-[#0D1117]/80 hover:bg-[#1E232B] p-2 rounded border border-[#21262D] flex items-center justify-between text-xs cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-2 truncate">
                        <span className="text-[10px] w-4 h-4 rounded-full bg-zinc-800 text-zinc-400 flex items-center justify-center font-bold shrink-0">
                          {idx + 1}
                        </span>
                        <span className="text-[11px] text-zinc-300 hover:text-white truncate font-medium">
                          {t.title}
                        </span>
                      </div>
                      {t.affected_files && t.affected_files.length > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-zinc-800/80 text-zinc-400 rounded shrink-0 font-mono">
                          {t.affected_files[0].split("/").pop()}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Timeline Events Feed */}
        {events.map((evt, idx) => renderEventCard(evt, idx))}

        <div ref={messagesEndRef} />
      </div>

      {/* Bottom Preset Chips for quick testing */}
      <div className="px-3 py-1.5 border-t border-[#222226] bg-[#121215] flex items-center gap-1.5 overflow-x-auto no-scrollbar">
        <span className="text-[10px] font-bold text-zinc-500 uppercase shrink-0">Test:</span>
        {testPresets.map((preset) => {
          const style = getIntentStyle(preset.intent);
          return (
            <button
              key={preset.prompt}
              onClick={() => handlePresetClick(preset.prompt)}
              disabled={isLoading || isRunning}
              className={`text-[10px] px-2 py-0.5 rounded-full border ${style.border} ${style.bg} ${style.text} hover:brightness-125 transition-all shrink-0 font-mono`}
            >
              {preset.label}: "{preset.prompt}"
            </button>
          );
        })}
      </div>

      {/* Signature Chat Input Container */}
      <div className="p-3 border-t border-[#27272A] bg-[#141417]">
        <div className="bg-[#18181B] border border-[#27272A] focus-within:border-purple-500/80 rounded-xl p-2.5 space-y-2 shadow-inner transition-colors">
          <form onSubmit={handleSubmit} className="space-y-2">
            <textarea
              rows={2}
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder="Ask a question (e.g. 'hi', 'how does auth work?', 'show repo tree', 'add OAuth')..."
              disabled={isLoading || isRunning}
              className="w-full bg-transparent text-xs text-zinc-100 placeholder:text-zinc-500 font-sans focus:outline-none resize-none leading-relaxed"
            />

            {/* Bottom Controls */}
            <div className="flex items-center justify-between pt-1 border-t border-[#222226]">
              {/* Left Model Selector */}
              <div className="flex items-center gap-1.5 relative">
                <button
                  type="button"
                  onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}
                  className="flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-200 px-2 py-0.5 rounded-md hover:bg-[#27272A] transition-colors font-sans"
                >
                  <Sparkles className="w-3 h-3 text-purple-400" />
                  <span>{selectedModel}</span>
                  <ChevronDown className="w-3 h-3 text-zinc-500" />
                </button>

                {isModelDropdownOpen && (
                  <div className="absolute bottom-7 left-0 w-48 bg-[#18181B] border border-[#27272A] rounded-lg shadow-xl py-1 z-50 text-xs">
                    {["Gemini 3.7 Flash", "Claude 3.7 Sonnet", "Ollama: Qwen-2.5-Coder"].map((m) => (
                      <div
                        key={m}
                        onClick={() => {
                          setSelectedModel(m);
                          setIsModelDropdownOpen(false);
                        }}
                        className={`px-3 py-1.5 flex items-center justify-between cursor-pointer hover:bg-[#27272A] ${
                          selectedModel === m ? "text-purple-400 font-medium" : "text-zinc-300"
                        }`}
                      >
                        <span className="truncate">{m}</span>
                        {selectedModel === m && <Check className="w-3.5 h-3.5" />}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Right Send Button */}
              <div className="flex items-center gap-2">
                <button
                  type="submit"
                  disabled={isLoading || !inputPrompt.trim() || isRunning}
                  className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                    inputPrompt.trim() && !isRunning
                      ? "bg-purple-600 hover:bg-purple-500 text-white shadow-sm"
                      : isRunning
                      ? "bg-purple-500 text-white animate-pulse"
                      : "bg-[#27272A] text-zinc-500 cursor-not-allowed"
                  }`}
                >
                  {isRunning ? (
                    <div className="w-2.5 h-2.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <ArrowUp className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
