"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  ArrowUp,
  Bot,
  Compass,
  HelpCircle,
  Info,
  Layers,
  RotateCcw,
  Sparkles,
  User,
  Zap,
} from "lucide-react";
import { WorkspaceSnapshot } from "@/types/workspace";

interface ChatPanelProps {
  snapshot?: WorkspaceSnapshot | null;
  onStartRun?: (prompt: string) => void;
  onApprovePlan?: () => void;
  onRejectPlan?: (reason?: string) => void;
  onNavigateToPlan?: () => void;
  onApproveAction?: (approvalId: string) => void;
  onRejectAction?: (approvalId: string, reason: string) => void;
  onSelectFile?: (file: string) => void;
  isLoading?: boolean;
}

interface IntentData {
  intent: string;
  confidence: number;
  reason?: string;
  method?: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  intent?: IntentData;
  timestamp: string;
}

export function ChatPanel({ onStartRun }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputPrompt, setInputPrompt] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const testPresets = [
    { label: "Greeting", prompt: "hi", intent: "chat", icon: Sparkles },
    { label: "Explain", prompt: "how does authentication work?", intent: "explain", icon: Info },
    { label: "Explore", prompt: "show repo tree", intent: "explore", icon: Compass },
    { label: "Plan", prompt: "what would it take to add payments?", intent: "plan", icon: Layers },
    { label: "Implement", prompt: "add Google OAuth", intent: "implement", icon: Zap },
    { label: "Clarify", prompt: "make auth better", intent: "clarify", icon: HelpCircle },
  ];

  const handleSend = async (promptText: string) => {
    const trimmed = promptText.trim();
    if (!trimmed || isSubmitting) return;

    const userMsgId = `user-${Date.now()}`;
    const userMsg: ChatMessage = {
      id: userMsgId,
      role: "user",
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt("");
    setIsSubmitting(true);

    try {
      // Optional: notify background runner if provided
      if (onStartRun) {
        try {
          onStartRun(trimmed);
        } catch {}
      }

      // Fast, synchronous classification endpoint
      const res = await fetch("/api/v1/agent/classify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requirement: trimmed }),
      });

      if (!res.ok) {
        throw new Error(`Classification error: ${res.statusText}`);
      }

      const data = await res.json();
      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        text: data.response || "Request processed.",
        intent: {
          intent: data.intent,
          confidence: data.confidence,
          reason: data.reason,
          method: data.method,
        },
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const fallbackMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        text: `Error communicating with intent router: ${err.message || err}`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, fallbackMsg]);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSend(inputPrompt);
  };

  const getIntentStyle = (intentKey?: string) => {
    switch (intentKey?.toLowerCase()) {
      case "chat":
        return {
          bg: "bg-emerald-500/10",
          border: "border-emerald-500/30",
          text: "text-emerald-400",
          title: "CHAT INTENT",
          icon: Sparkles,
        };
      case "explore":
        return {
          bg: "bg-cyan-500/10",
          border: "border-cyan-500/30",
          text: "text-cyan-400",
          title: "EXPLORE INTENT",
          icon: Compass,
        };
      case "explain":
        return {
          bg: "bg-blue-500/10",
          border: "border-blue-500/30",
          text: "text-blue-400",
          title: "EXPLAIN INTENT",
          icon: Info,
        };
      case "plan":
        return {
          bg: "bg-amber-500/10",
          border: "border-amber-500/30",
          text: "text-amber-400",
          title: "PLAN INTENT",
          icon: Layers,
        };
      case "implement":
        return {
          bg: "bg-purple-500/10",
          border: "border-purple-500/30",
          text: "text-purple-400",
          title: "IMPLEMENT INTENT",
          icon: Zap,
        };
      case "clarify":
      default:
        return {
          bg: "bg-rose-500/10",
          border: "border-rose-500/30",
          text: "text-rose-400",
          title: "CLARIFY INTENT",
          icon: HelpCircle,
        };
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0F0F12] text-zinc-200 font-sans select-none">
      {/* Header */}
      <div className="px-3.5 py-2.5 border-b border-[#27272A] bg-[#141417] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400" />
          <span className="text-xs font-semibold text-zinc-100">
            Intent Classification
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono">
            v2.0
          </span>
        </div>
        <button
          onClick={() => setMessages([])}
          title="Clear Conversation"
          className="p-1 hover:bg-[#27272A] hover:text-zinc-200 rounded text-zinc-400 text-xs flex items-center gap-1 transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span className="text-[10px]">Reset</span>
        </button>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-zinc-500 space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-purple-600/10 border border-purple-500/20 flex items-center justify-center text-purple-400 shadow-inner">
              <Bot className="w-6 h-6" />
            </div>
            <div className="space-y-1 max-w-sm">
              <p className="text-sm font-semibold text-zinc-200">
                Ask any question or command
              </p>
              <p className="text-xs text-zinc-400 leading-relaxed">
                The router will immediately classify the intent, display confidence, and return the response.
              </p>
            </div>

            {/* Quick Test Preset Buttons */}
            <div className="w-full max-w-sm pt-2">
              <div className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider mb-2">
                Quick Test Queries:
              </div>
              <div className="grid grid-cols-2 gap-1.5 text-left">
                {testPresets.map((preset) => {
                  const style = getIntentStyle(preset.intent);
                  const Icon = preset.icon;
                  return (
                    <button
                      key={preset.prompt}
                      onClick={() => handleSend(preset.prompt)}
                      disabled={isSubmitting}
                      className={`p-2 rounded-lg border ${style.border} ${style.bg} hover:brightness-125 transition-all text-left flex items-start gap-2 cursor-pointer`}
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
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className="space-y-2">
              {msg.role === "user" ? (
                /* User Message */
                <div className="flex gap-2.5 bg-[#18181B] p-3 rounded-xl border border-[#27272A] shadow-sm">
                  <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center shrink-0 text-xs font-semibold">
                    <User className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-zinc-200">You</span>
                      <span className="text-[10px] text-zinc-500 font-mono">
                        {msg.timestamp}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-200 leading-relaxed font-sans">
                      {msg.text}
                    </p>
                  </div>
                </div>
              ) : (
                /* Assistant Message & Intent Breakdown */
                <div className="space-y-2">
                  {msg.intent && (
                    <div
                      className={`rounded-xl p-3 border ${
                        getIntentStyle(msg.intent.intent).border
                      } ${getIntentStyle(msg.intent.intent).bg} space-y-1.5 shadow-md`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {React.createElement(getIntentStyle(msg.intent.intent).icon, {
                            className: `w-4 h-4 ${getIntentStyle(msg.intent.intent).text}`,
                          })}
                          <span
                            className={`text-xs font-bold font-mono tracking-wider ${
                              getIntentStyle(msg.intent.intent).text
                            }`}
                          >
                            {getIntentStyle(msg.intent.intent).title}
                          </span>
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-900/80 text-zinc-300 border border-zinc-700/60 font-mono">
                            {(msg.intent.confidence * 100).toFixed(0)}% Confidence
                          </span>
                        </div>
                        <span className="text-[10px] text-zinc-400 font-mono capitalize">
                          {msg.intent.method || "deterministic"}
                        </span>
                      </div>
                      {msg.intent.reason && (
                        <p className="text-xs text-zinc-300 font-mono leading-relaxed">
                          {msg.intent.reason}
                        </p>
                      )}
                    </div>
                  )}

                  <div className="flex gap-2.5 bg-[#161B22] p-3.5 rounded-xl border border-[#30363D] shadow-sm">
                    <div className="w-6 h-6 rounded-full bg-purple-600/30 border border-purple-500/40 text-purple-300 flex items-center justify-center shrink-0 text-xs font-semibold">
                      <Bot className="w-3.5 h-3.5" />
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-zinc-200">
                          Repository Assistant
                        </span>
                        <span className="text-[10px] text-emerald-400 font-mono">
                          Delivered
                        </span>
                      </div>
                      <p className="text-xs text-zinc-200 leading-relaxed font-sans whitespace-pre-wrap">
                        {msg.text}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))
        )}

        {isSubmitting && (
          <div className="flex items-center gap-2 text-xs text-zinc-400 font-mono py-1 px-2">
            <div className="w-3 h-3 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            <span>Classifying intent...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Preset Chips Bar */}
      {messages.length > 0 && (
        <div className="px-3 py-1.5 border-t border-[#222226] bg-[#121215] flex items-center gap-1.5 overflow-x-auto no-scrollbar">
          <span className="text-[10px] font-bold text-zinc-500 uppercase shrink-0">Test:</span>
          {testPresets.map((preset) => {
            const style = getIntentStyle(preset.intent);
            return (
              <button
                key={preset.prompt}
                onClick={() => handleSend(preset.prompt)}
                disabled={isSubmitting}
                className={`text-[10px] px-2 py-0.5 rounded-full border ${style.border} ${style.bg} ${style.text} hover:brightness-125 transition-all shrink-0 font-mono cursor-pointer`}
              >
                {preset.label}: "{preset.prompt}"
              </button>
            );
          })}
        </div>
      )}

      {/* Input Box */}
      <div className="p-3 border-t border-[#27272A] bg-[#141417]">
        <form
          onSubmit={handleFormSubmit}
          className="bg-[#18181B] border border-[#27272A] focus-within:border-purple-500/80 rounded-xl p-2.5 space-y-2 shadow-inner transition-colors"
        >
          <textarea
            rows={2}
            value={inputPrompt}
            onChange={(e) => setInputPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend(inputPrompt);
              }
            }}
            placeholder="Type anything (e.g. 'hi', 'how does auth work?', 'show repo tree', 'add OAuth')..."
            disabled={isSubmitting}
            className="w-full bg-transparent text-xs text-zinc-100 placeholder:text-zinc-500 font-sans focus:outline-none resize-none leading-relaxed"
          />

          <div className="flex items-center justify-between pt-1 border-t border-[#222226]">
            <span className="text-[10px] text-zinc-500 font-sans">
              Press Enter to submit
            </span>

            <button
              type="submit"
              disabled={isSubmitting || !inputPrompt.trim()}
              className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                inputPrompt.trim() && !isSubmitting
                  ? "bg-purple-600 hover:bg-purple-500 text-white shadow-sm cursor-pointer"
                  : isSubmitting
                  ? "bg-purple-500 text-white animate-pulse"
                  : "bg-[#27272A] text-zinc-500 cursor-not-allowed"
              }`}
            >
              {isSubmitting ? (
                <div className="w-2.5 h-2.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <ArrowUp className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
