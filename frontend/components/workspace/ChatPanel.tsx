"use client";

import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import {
  ArrowUp,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  FileCode,
  FileEdit,
  Mic,
  Play,
  Plus,
  Sparkles,
} from "lucide-react";
import { WorkspaceSnapshot } from "@/types/workspace";

interface ChatPanelProps {
  snapshot?: WorkspaceSnapshot | null;
  repoId?: string;
  onStartRun?: (prompt: string) => void;
  onApprovePlan?: () => void;
  onRejectPlan?: (reason?: string) => void;
  onNavigateToPlan?: () => void;
  onOpenPlanInEditor?: (plan: any) => void;
  onSelectFile?: (file: string) => void;
  isLoading?: boolean;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  timestamp: string;
  isLoading?: boolean;
  activityItems?: Array<{
    type: "read" | "write" | "test" | "verify" | "info";
    text: string;
    file?: string;
  }>;
}

export function ChatPanel({
  onStartRun,
  snapshot,
  repoId,
  onSelectFile,
  onOpenPlanInEditor,
  isLoading: externalLoading,
}: ChatPanelProps) {
  // Clean empty initial state - fills only when user types and interacts
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputPrompt, setInputPrompt] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, snapshot?.latest_events]);

  // Track execution events from snapshot and format as live activity items
  useEffect(() => {
    console.log(`[ChatPanel] latest_events changed, count: ${snapshot?.latest_events?.length || 0}`);
    if (!snapshot?.latest_events || snapshot.latest_events.length === 0) {
      console.log(`[ChatPanel] No events to process`);
      return;
    }

    const events = snapshot.latest_events;
    console.log(`[ChatPanel] Processing ${events.length} events`);
    const activityList: Array<{
      type: "read" | "write" | "test" | "verify" | "info";
      text: string;
      file?: string;
    }> = [];

    events.forEach((ev, idx) => {
      const type = ev.event_type;
      const msg = ev.message || "";
      const p = ev.payload || {};
      console.log(`[ChatPanel] Event ${idx}: type=${type}, message=${msg.substring(0, 100)}`);

      if (type === "TASK_STARTED" || type === "TOOL_CALL_STARTED") {
        const file = p.file_path || p.target_file || (p.tool_name === "read_file" ? p.arguments?.file_path : null);
        if (file) {
          console.log(`[ChatPanel] → Adding read activity for file: ${file}`);
          activityList.push({ type: "read", text: `Reading ${file}`, file });
        } else {
          console.log(`[ChatPanel] → Adding info activity`);
          activityList.push({ type: "info", text: msg });
        }
      } else if (type === "FILE_WRITTEN" || (type === "TOOL_CALL_COMPLETED" && p.tool_name === "write_file")) {
        const file = p.file_path || p.target_file || p.arguments?.file_path;
        console.log(`[ChatPanel] → Adding write activity for file: ${file}`);
        activityList.push({ type: "write", text: `Writing ${file || "file"}`, file });
      } else if (type === "TASK_VERIFYING" || type === "VERIFICATION_STARTED") {
        console.log(`[ChatPanel] → Adding test activity`);
        activityList.push({ type: "test", text: "Running tests..." });
      } else if (type === "TASK_PASSED" || type === "VERIFICATION_PASSED") {
        console.log(`[ChatPanel] → Adding verify activity`);
        activityList.push({ type: "verify", text: "Verification passed" });
      } else if (type === "PLAN_READY_FOR_APPROVAL") {
        console.log(`[ChatPanel] → Adding ready for approval info`);
        activityList.push({ type: "info", text: "Ready for approval" });
      }
    });

    console.log(`[ChatPanel] Created ${activityList.length} activity items`);
    if (activityList.length > 0) {
      setMessages((prev) => {
        const lastMsg = prev[prev.length - 1];
        console.log(`[ChatPanel] Updating messages, lastMsg role: ${lastMsg?.role}`);
        if (lastMsg && lastMsg.role === "assistant" && lastMsg.activityItems) {
          console.log(`[ChatPanel] Updating existing assistant message with new activities`);
          return [
            ...prev.slice(0, -1),
            { ...lastMsg, activityItems: activityList },
          ];
        }
        console.log(`[ChatPanel] No assistant message to update`);
        return prev;
      });
    }
  }, [snapshot?.latest_events]);

  const handleSend = async (textToSend?: string) => {
    const text = textToSend !== undefined ? textToSend : inputPrompt;
    const trimmed = text.trim();
    if (!trimmed || isSubmitting) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    const assistantMsgId = `assistant-${Date.now()}`;
    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt("");
    setIsSubmitting(true);

    try {
      // Execute classification & planning
      const res = await fetch("/api/v1/agent/classify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requirement: trimmed,
          repository_id: repoId || snapshot?.run?.repository_id || null,
        }),
      });

      if (!res.ok) {
        throw new Error(`Classification error: ${res.statusText}`);
      }

      const data = await res.json();
      const planText = data.response || "I investigated the repository and created an implementation plan.";

      if (data.intent === "implement") {
        if (onStartRun) {
          onStartRun(trimmed);
        }
        if (data.plan && onOpenPlanInEditor) {
          onOpenPlanInEditor(data.plan);
        }
      }

      const finalAssistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        text: planText,
        isLoading: false,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, finalAssistantMsg]);
    } catch (err: any) {
      const fallbackMsg: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        text: `Error: ${err.message || err}`,
        isLoading: false,
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

  return (
    <div className="flex flex-col h-full bg-[#0D1117] text-zinc-200 font-sans select-none justify-between">
      {/* Messages Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 font-sans text-xs">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-zinc-500 font-sans select-none">
            <Sparkles className="w-8 h-8 mb-2 text-purple-400/60 animate-pulse" />
            <p className="text-xs font-medium text-zinc-400">Agent Assistant</p>
            <p className="text-[11px] text-zinc-600 mt-1 max-w-[200px]">
              Ask a question or describe a task to start working with the repository agent.
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className="space-y-2">
              {msg.role === "user" ? (
                <div className="flex justify-end">
                  <div className="bg-[#21262D] text-zinc-100 px-3 py-2 rounded-xl max-w-[85%] text-xs font-sans leading-relaxed">
                    {msg.text}
                  </div>
                </div>
              ) : (
                <div className="text-xs text-zinc-200 leading-relaxed font-sans space-y-2">
                  <ReactMarkdown
                    components={{
                      h1: ({ children }) => (
                        <h1 className="text-sm font-bold text-white mt-3 mb-1.5 pb-1 border-b border-zinc-700/60">
                          {children}
                        </h1>
                      ),
                      h2: ({ children }) => (
                        <h2 className="text-xs font-bold text-purple-300 mt-2.5 mb-1 pb-0.5 border-b border-zinc-800">
                          {children}
                        </h2>
                      ),
                      h3: ({ children }) => (
                        <h3 className="text-xs font-semibold text-zinc-100 mt-2 mb-1">
                          {children}
                        </h3>
                      ),
                      p: ({ children }) => (
                        <p className="text-xs text-zinc-300 leading-relaxed my-1">
                          {children}
                        </p>
                      ),
                      ul: ({ children }) => (
                        <ul className="list-disc pl-4 space-y-1 my-1 text-zinc-300">
                          {children}
                        </ul>
                      ),
                      li: ({ children }) => (
                        <li className="text-xs text-zinc-300 leading-normal">
                          {children}
                        </li>
                      ),
                      table: ({ children }) => (
                        <div className="overflow-x-auto my-2 border border-[#30363D] rounded-lg">
                          <table className="w-full text-[11px] font-mono border-collapse">
                            {children}
                          </table>
                        </div>
                      ),
                      thead: ({ children }) => (
                        <thead className="bg-[#161B22] text-zinc-400 border-b border-[#30363D]">
                          {children}
                        </thead>
                      ),
                      th: ({ children }) => (
                        <th className="p-2 text-left font-semibold">
                          {children}
                        </th>
                      ),
                      td: ({ children }) => (
                        <td className="p-2 border-t border-[#21262D] text-zinc-300">
                          {children}
                        </td>
                      ),
                      code: ({ className, children, ...props }: any) => {
                        const isMultiline = String(children).includes("\n");
                        if (!isMultiline && !className) {
                          return (
                            <code
                              className="bg-[#21262D] text-purple-300 px-1 py-0.5 rounded font-mono text-[11px] border border-zinc-700/60"
                              {...props}
                            >
                              {children}
                            </code>
                          );
                        }
                        return (
                          <pre className="bg-[#0A0D10] border border-[#30363D] p-2.5 rounded-lg overflow-x-auto my-2 text-zinc-200 font-mono text-[11px]">
                            <code {...props}>{children}</code>
                          </pre>
                        );
                      },
                    }}
                  >
                    {msg.text}
                  </ReactMarkdown>

                  {/* Execution Activity Stream Items */}
                  {msg.activityItems && msg.activityItems.length > 0 && (
                    <div className="space-y-1.5 pt-2 border-t border-zinc-800/80 font-mono text-[11px]">
                      {msg.activityItems.map((item, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-zinc-300">
                          {item.type === "read" && <CircleDot className="w-3.5 h-3.5 text-purple-400 shrink-0" />}
                          {item.type === "write" && <FileEdit className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                          {item.type === "test" && <Play className="w-3.5 h-3.5 text-cyan-400 shrink-0" />}
                          {item.type === "verify" && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                          {item.type === "info" && <CircleDot className="w-3.5 h-3.5 text-zinc-500 shrink-0" />}

                          {item.file ? (
                            <button
                              type="button"
                              onClick={() => onSelectFile?.(item.file!)}
                              className="hover:underline text-zinc-200 hover:text-purple-300 cursor-pointer"
                            >
                              {item.text}
                            </button>
                          ) : (
                            <span>{item.text}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Clean Bottom Input Box */}
      <div className="p-3 border-t border-[#21262D] bg-[#161B22]">
        <form
          onSubmit={handleFormSubmit}
          className="bg-[#0D1117] border border-[#30363D] focus-within:border-purple-500/80 rounded-xl p-2.5 space-y-2 transition-colors shadow-inner"
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
            placeholder="Ask anything, @ to mention, / for actions"
            disabled={isSubmitting}
            className="w-full bg-transparent text-xs text-zinc-100 placeholder:text-zinc-500 font-sans focus:outline-none resize-none leading-relaxed"
          />

          <div className="flex items-center justify-between pt-1 border-t border-[#21262D]">
            {/* Model Badge */}
            <div className="flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-200 font-sans cursor-pointer px-1 py-0.5 rounded hover:bg-[#21262D] transition-colors">
              <Plus className="w-3 h-3 text-zinc-500" />
              <span>Gemini 3.7 Flash Medium</span>
              <ChevronDown className="w-3 h-3 text-zinc-500 ml-0.5" />
            </div>

            {/* Action Icons: Mic + Send */}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-[#21262D] transition-colors"
                title="Voice input"
              >
                <Mic className="w-3.5 h-3.5" />
              </button>

              <button
                type="submit"
                disabled={isSubmitting || !inputPrompt.trim()}
                className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                  inputPrompt.trim() && !isSubmitting
                    ? "bg-purple-600 hover:bg-purple-500 text-white shadow-sm cursor-pointer"
                    : isSubmitting
                    ? "bg-purple-500 text-white animate-pulse"
                    : "bg-[#21262D] text-zinc-500 cursor-not-allowed"
                }`}
              >
                <ArrowUp className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}