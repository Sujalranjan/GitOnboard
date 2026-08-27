"use client";

import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import {
  ArrowUp,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleDot,
  Clock,
  Eye,
  FileCode,
  FileEdit,
  FlaskConical,
  Mic,
  PenTool,
  Play,
  Plus,
  Search,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";
import { ActivityItem, WorkspaceSnapshot } from "@/types/workspace";

interface ChatPanelProps {
  snapshot?: WorkspaceSnapshot | null;
  repoId?: string;
  newChatTrigger?: number;
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
  activityItems?: ActivityItem[];
}

export function ChatPanel({
  onStartRun,
  snapshot,
  repoId,
  newChatTrigger,
  onSelectFile,
  onOpenPlanInEditor,
  isLoading: externalLoading,
}: ChatPanelProps) {
  const storageKey = `gitonboard_chat_${repoId || "default"}`;

  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = sessionStorage.getItem(storageKey);
        if (saved) {
          return JSON.parse(saved);
        }
      } catch (e) {
        console.debug("Failed loading chat from sessionStorage", e);
      }
    }
    return [];
  });
  const [inputPrompt, setInputPrompt] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [expandedActivities, setExpandedActivities] = useState<Record<string, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Clear chat when newChatTrigger fires
  useEffect(() => {
    if (newChatTrigger && newChatTrigger > 0) {
      setMessages([]);
      if (typeof window !== "undefined") {
        try {
          sessionStorage.removeItem(storageKey);
        } catch (e) {}
      }
      setIsSubmitting(false);
      setInputPrompt("");
      textareaRef.current?.focus();
    }
  }, [newChatTrigger, storageKey]);

  // Persist messages across reconnections and hot-reloads
  useEffect(() => {
    if (typeof window !== "undefined" && messages.length > 0) {
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(messages));
      } catch (e) {
        console.debug("Failed saving chat to sessionStorage", e);
      }
    }
  }, [messages, storageKey]);

  // Auto-scroll on new messages or activity updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, snapshot?.latest_events]);

  const toggleActivityExpand = (msgId: string) => {
    setExpandedActivities((prev) => ({
      ...prev,
      [msgId]: prev[msgId] === undefined ? false : !prev[msgId],
    }));
  };

  // ──────────────────────────────────────────────────────────────────────────
  // SSE Event Processing: Map real-time events to structured ActivityItems
  // ──────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!snapshot?.latest_events || snapshot.latest_events.length === 0) {
      return;
    }

    const events = snapshot.latest_events;
    const sseActivities: ActivityItem[] = [];

    events.forEach((ev, idx) => {
      const type = ev.event_type;
      const msg = ev.message || "";
      const p = ev.payload || {};
      const evId = ev.event_id || `sse-${ev.sequence || idx}`;

      const actType = p.activity_type || "";
      const tool = p.tool || p.tool_name || "";
      const rawPath = p.path || p.file_path || p.target_file || p.arguments?.path || p.arguments?.file_path;
      const startLine = p.start_line || p.arguments?.start_line;
      const endLine = p.end_line || p.arguments?.end_line;
      const symbol = p.symbol || p.arguments?.name || p.arguments?.symbol_name || p.arguments?.seed_id;
      const query = p.query || p.arguments?.query || p.arguments?.pattern;
      const task = p.task || p.arguments?.task || p.arguments?.test_command;
      const isCompleted = type === "TOOL_CALL_COMPLETED" || p.status === "completed" || type === "TASK_PASSED" || type === "VERIFICATION_PASSED" || type === "FILE_WRITTEN";
      const isFailed = type === "TOOL_CALL_FAILED" || type === "TASK_FAILED" || type === "VERIFICATION_FAILED" || p.status === "failed";
      const status: "running" | "completed" | "failed" = isFailed ? "failed" : isCompleted ? "completed" : "running";

      if (actType === "reading" || tool === "read_file") {
        const title = isCompleted ? `Read ${rawPath || "file"}` : isFailed ? `Failed to read ${rawPath || "file"}` : `Reading ${rawPath || "file"}`;
        sseActivities.push({
          id: `read-${rawPath || evId}`,
          type: "read",
          title,
          status,
          file: rawPath,
          startLine,
          endLine,
          error: isFailed ? (p.error_message || msg) : undefined,
        });
      } else if (actType === "searching" || tool === "search_code" || tool === "search_symbols") {
        const title = isCompleted ? `Searched repository` : isFailed ? `Search failed` : `Searching repository`;
        sseActivities.push({
          id: `search-${query || evId}`,
          type: "search",
          title,
          status,
          query: query || msg,
          error: isFailed ? (p.error_message || msg) : undefined,
        });
      } else if (actType === "inspecting" || tool === "get_symbol" || tool === "get_callers" || tool === "get_callees" || tool === "trace_feature") {
        const title = isCompleted ? `Inspected ${symbol || "symbol"}` : isFailed ? `Failed inspecting ${symbol || "symbol"}` : `Inspecting ${symbol || "symbol"}`;
        sseActivities.push({
          id: `inspect-${symbol || rawPath || evId}`,
          type: "inspect",
          title,
          status,
          symbol,
          file: rawPath,
          error: isFailed ? (p.error_message || msg) : undefined,
        });
      } else if (actType === "writing" || type === "FILE_WRITTEN" || tool === "create_file" || tool === "modify_file" || tool === "write_file" || tool === "apply_patch") {
        const title = isCompleted ? `Wrote ${rawPath || "file"}` : isFailed ? `Failed to write ${rawPath || "file"}` : `Writing ${rawPath || "file"}`;
        sseActivities.push({
          id: `write-${rawPath || evId}`,
          type: "write",
          title,
          status,
          file: rawPath,
          error: isFailed ? (p.error_message || msg) : undefined,
        });
      } else if (actType === "deleting" || tool === "delete_file") {
        const title = isCompleted ? `Deleted ${rawPath || "file"}` : isFailed ? `Failed to delete ${rawPath || "file"}` : `Deleting ${rawPath || "file"}`;
        sseActivities.push({
          id: `del-${rawPath || evId}`,
          type: "delete",
          title,
          status,
          file: rawPath,
          error: isFailed ? (p.error_message || msg) : undefined,
        });
      } else if (actType === "testing" || type === "TASK_VERIFYING" || type === "VERIFICATION_STARTED" || tool === "verify_dynamic" || tool === "run_tests") {
        const title = isCompleted ? `Tests completed` : isFailed ? `Tests failed` : (task || "Running tests...");
        sseActivities.push({
          id: `test-${evId}`,
          type: "test",
          title,
          status,
          task: task || msg,
          error: isFailed ? (p.error_message || msg) : undefined,
        });
      } else if (actType === "verifying" || type === "TASK_PASSED" || type === "VERIFICATION_PASSED" || type === "VERIFICATION_CHECK_COMPLETED" || tool === "verify_static" || tool === "verify_contract") {
        const title = isCompleted ? `Verification passed` : isFailed ? `Verification failed` : `Verifying task...`;
        sseActivities.push({
          id: `verify-${evId}`,
          type: "verify",
          title,
          status,
          error: isFailed ? (p.error_message || msg) : undefined,
        });
      } else if (type === "PLAN_READY_FOR_APPROVAL") {
        sseActivities.push({
          id: `plan-ready-${evId}`,
          type: "info",
          title: "Implementation plan synthesized. Ready for human review.",
          status: "completed",
        });
      } else if (type === "TASK_STARTED" || type === "AGENT_TASK_STARTED") {
        sseActivities.push({
          id: `task-${evId}`,
          type: "info",
          title: msg || "Executing task",
          status: "running",
        });
      }
    });

    if (sseActivities.length > 0) {
      setMessages((prev) => {
        if (prev.length === 0) {
          return [
            {
              id: `assistant-stream-${Date.now()}`,
              role: "assistant",
              text: "Executing repository tasks...",
              isLoading: false,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              activityItems: sseActivities,
            },
          ];
        }

        const lastIdx = prev.length - 1;
        const lastMsg = prev[lastIdx];

        if (lastMsg.role === "assistant") {
          // Merge SSE activities with existing activities without duplicates
          const existing = lastMsg.activityItems || [];
          const merged = [...existing];

          sseActivities.forEach((newItem) => {
            const matchIdx = merged.findIndex(
              (e) => (newItem.id && e.id === newItem.id) || (e.type === newItem.type && e.file && e.file === newItem.file)
            );
            if (matchIdx >= 0) {
              merged[matchIdx] = newItem; // update status (running -> completed/failed)
            } else {
              merged.push(newItem);
            }
          });

          return [
            ...prev.slice(0, lastIdx),
            { ...lastMsg, activityItems: merged },
          ];
        }

        return prev;
      });
    }
  }, [snapshot?.latest_events]);

  // ──────────────────────────────────────────────────────────────────────────
  // User Prompt Submission & Synchronous Classification Flow
  // ──────────────────────────────────────────────────────────────────────────
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
    const isGreeting = /^(hi|hello|hey|greetings|howdy|sup)\b/i.test(trimmed);

    // Immediate assistant activity state: screen never looks frozen
    const initialActivities: ActivityItem[] = [
      {
        id: `init-${Date.now()}`,
        type: "info",
        title: isGreeting ? "Understanding request..." : "Investigating repository...",
        status: "running",
      },
    ];

    const pendingAssistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      text: "",
      isLoading: true,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      activityItems: initialActivities,
    };

    setMessages((prev) => [...prev, userMsg, pendingAssistantMsg]);
    setInputPrompt("");
    setIsSubmitting(true);

    const timeoutWarningTimer = setTimeout(() => {
      setMessages((prev) => {
        return prev.map((m) => {
          if (m.id === assistantMsgId && m.isLoading) {
            const existing = m.activityItems || [];
            const hasWaitInfo = existing.some((a) => a.id === "wait-info-60s");
            if (!hasWaitInfo) {
              return {
                ...m,
                activityItems: [
                  ...existing,
                  {
                    id: "wait-info-60s",
                    type: "info",
                    title: "Processing with local LLM (deep code synthesis in progress, kindly wait)...",
                    status: "running",
                  },
                ],
              };
            }
          }
          return m;
        });
      });
    }, 60000);

    try {
      // Stream live activities and response in real-time
      const streamRes = await fetch("/api/v1/agent/classify/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requirement: trimmed,
          repository_id: repoId || snapshot?.run?.repository_id || null,
        }),
      });

      if (streamRes.ok && streamRes.body) {
        const reader = streamRes.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        const formatTitle = (rawTitle: string): string => {
          let t = rawTitle;
          t = t.replace(/^Reading\s+/i, "Read ");
          t = t.replace(/^Writing\s+/i, "Write ");
          t = t.replace(/^Searching\s+/i, "Search ");
          t = t.replace(/^Synthesizing\s+/i, "Synthesize ");
          t = t.replace(/^Inspecting\s+/i, "Inspect ");
          t = t.replace(/^Verifying\s+/i, "Verify ");
          t = t.replace(/^Testing\s+/i, "Test ");
          return t;
        };

        const finalizeItems = (items: ActivityItem[] = []): ActivityItem[] => {
          return items
            .filter((it) => !it.id.startsWith("wait-info-") && !it.id.startsWith("init-") && !it.id.startsWith("llm-"))
            .map((it) => ({
              ...it,
              title: formatTitle(it.title),
              status: it.status === "running" ? ("completed" as const) : it.status,
            }));
        };

        const parseSSEBlock = (block: string) => {
          const trimmedBlock = block.trim();
          if (!trimmedBlock || trimmedBlock.startsWith(":")) return;

          let eventType = "message";
          let dataStr = "";
          const lines = trimmedBlock.split(/\r?\n/);
          for (const line of lines) {
            const tl = line.trim();
            if (tl.startsWith("event:")) {
              eventType = tl.slice(6).trim();
            } else if (tl.startsWith("data:")) {
              dataStr = tl.slice(5).trim();
            }
          }

          if (!dataStr) return;

          try {
            const payload = JSON.parse(dataStr);

            if (eventType === "activity" || payload.type === "activity" || payload.item) {
              const rawItem: ActivityItem = payload.item || payload;
              const sLine = rawItem.startLine ?? (rawItem as any).start_line;
              const eLine = rawItem.endLine ?? (rawItem as any).end_line;
              const item: ActivityItem = {
                ...rawItem,
                title: formatTitle(rawItem.title),
                startLine: sLine,
                endLine: eLine,
              };

              setMessages((prev) => {
                return prev.map((msg) => {
                  if (msg.id === assistantMsgId) {
                    const existing = msg.activityItems || [];
                    const matchIdx = existing.findIndex(
                      (a) => (item.id && a.id === item.id) || (a.type === item.type && a.file && a.file === item.file)
                    );
                    const updated = [...existing];
                    if (matchIdx >= 0) {
                      updated[matchIdx] = item;
                    } else {
                      const filtered = updated.filter((a) => !a.id.startsWith("init-"));
                      filtered.push(item);
                      return { ...msg, activityItems: filtered };
                    }
                    return { ...msg, activityItems: updated };
                  }
                  return msg;
                });
              });
            } else if (eventType === "result" || payload.type === "result" || payload.response) {
              const data = payload.data || payload;
              const planText = data.response || "Investigation completed.";

              if (data.intent === "implement") {
                if (onStartRun) onStartRun(trimmed);
                if (data.plan && onOpenPlanInEditor) onOpenPlanInEditor(data.plan);
              }

              const confirmedActivities: ActivityItem[] = [];
              if (data.evidence && Array.isArray(data.evidence)) {
                data.evidence.forEach((ev: any) => {
                  const path = ev.path || ev.source_id;
                  if (path) {
                    const sLine = ev.start_line ?? ev.startLine ?? 1;
                    const eLine = ev.end_line ?? ev.endLine ?? 120;
                    confirmedActivities.push({
                      id: `ev-read-${path}`,
                      type: "read",
                      title: `Read ${path}`,
                      status: "completed",
                      file: path,
                      startLine: sLine,
                      endLine: eLine,
                    });
                  }
                });
              }

              setMessages((prev) => {
                return prev.map((msg) => {
                  if (msg.id === assistantMsgId) {
                    const sourceList = confirmedActivities.length > 0 ? confirmedActivities : (msg.activityItems || []);
                    return {
                      ...msg,
                      text: planText,
                      isLoading: false,
                      activityItems: finalizeItems(sourceList),
                    };
                  }
                  return msg;
                });
              });
            } else if (eventType === "error") {
              const errMsg = payload.data?.message || payload.message || "Failed to process request";
              setMessages((prev) => {
                return prev.map((msg) => {
                  if (msg.id === assistantMsgId) {
                    return {
                      ...msg,
                      text: `✕ Request failed: ${errMsg}`,
                      isLoading: false,
                      activityItems: finalizeItems(msg.activityItems),
                    };
                  }
                  return msg;
                });
              });
            }
          } catch (pErr) {
            console.debug("Stream parse skip:", pErr);
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (value) {
            buffer += decoder.decode(value, { stream: !done });
            const parts = buffer.split(/\r?\n\r?\n/);
            buffer = parts.pop() || "";
            for (const part of parts) {
              parseSSEBlock(part);
            }
          }
          if (done) {
            if (buffer.trim()) {
              parseSSEBlock(buffer);
            }
            break;
          }
        }

        // Ensure final loading state is cleared and activities are all finalized to completed
        setMessages((prev) => {
          return prev.map((msg) => {
            if (msg.id === assistantMsgId) {
              return {
                ...msg,
                text: msg.text || "Investigation completed.",
                isLoading: false,
                activityItems: finalizeItems(msg.activityItems),
              };
            }
            return msg;
          });
        });
      } else {
        // Fallback to synchronous classify if stream fails
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
        const planText = data.response || "Investigation completed.";

        const confirmedActivities: ActivityItem[] = [];
        const seenKeys = new Set<string>();

        const addActivity = (item: ActivityItem) => {
          const key = `${item.type}:${item.file || ""}:${item.symbol || ""}:${item.title}`;
          if (!seenKeys.has(key)) {
            seenKeys.add(key);
            confirmedActivities.push(item);
          }
        };

        if (data.evidence && Array.isArray(data.evidence)) {
          data.evidence.forEach((ev: any) => {
            const path = ev.path || ev.source_id;
            if (path && (ev.source_type === "source_code" || ev.source_type === "file" || path.includes("."))) {
              addActivity({
                id: `ev-read-${path}`,
                type: "read",
                title: `Read ${path}`,
                status: "completed",
                file: path,
                startLine: ev.start_line || 1,
                endLine: ev.end_line || 120,
              });
            }
          });
        }

        if (data.intent === "implement") {
          if (onStartRun) onStartRun(trimmed);
          if (data.plan && onOpenPlanInEditor) onOpenPlanInEditor(data.plan);
        }

        setMessages((prev) => {
          return prev.map((msg) => {
            if (msg.id === assistantMsgId) {
              return {
                ...msg,
                text: planText,
                isLoading: false,
                activityItems: confirmedActivities.length > 0 ? confirmedActivities : msg.activityItems,
              };
            }
            return msg;
          });
        });
      }
    } catch (err: any) {
      setMessages((prev) => {
        return prev.map((msg) => {
          if (msg.id === assistantMsgId) {
            return {
              ...msg,
              text: `✕ Unable to complete request: ${err.message || err}`,
              isLoading: false,
              activityItems: [
                {
                  id: `err-${Date.now()}`,
                  type: "info",
                  title: `Failed: ${err.message || "Unknown error"}`,
                  status: "failed",
                  error: err.message || String(err),
                },
              ],
            };
          }
          return msg;
        });
      });
    } finally {
      clearTimeout(timeoutWarningTimer);
      setIsSubmitting(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSend(inputPrompt);
  };

  // Helper to render activity icon
  const renderActivityIcon = (type: ActivityItem["type"], status: ActivityItem["status"]) => {
    if (status === "running") {
      return (
        <span className="relative flex h-2.5 w-2.5 mr-1 shrink-0">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-purple-500"></span>
        </span>
      );
    }

    if (status === "failed") {
      return <XCircle className="w-3.5 h-3.5 text-rose-400 shrink-0 mr-1" />;
    }

    switch (type) {
      case "read":
        return <BookOpen className="w-3.5 h-3.5 text-purple-400 shrink-0 mr-1" />;
      case "search":
        return <Search className="w-3.5 h-3.5 text-cyan-400 shrink-0 mr-1" />;
      case "inspect":
        return <Eye className="w-3.5 h-3.5 text-indigo-400 shrink-0 mr-1" />;
      case "write":
        return <PenTool className="w-3.5 h-3.5 text-amber-400 shrink-0 mr-1" />;
      case "delete":
        return <Trash2 className="w-3.5 h-3.5 text-rose-400 shrink-0 mr-1" />;
      case "test":
        return <FlaskConical className="w-3.5 h-3.5 text-cyan-400 shrink-0 mr-1" />;
      case "verify":
        return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mr-1" />;
      default:
        return <Check className="w-3.5 h-3.5 text-zinc-400 shrink-0 mr-1" />;
    }
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
              Ask a question, request code explanation, explore symbols, or describe a feature to implement.
            </p>
          </div>
        ) : (
          messages.map((msg) => {
            const isMsgExpanded = expandedActivities[msg.id] ?? true;
            const hasActivities = msg.activityItems && msg.activityItems.length > 0;
            const completedCount = msg.activityItems?.filter((a) => a.status === "completed").length || 0;
            const runningCount = msg.activityItems?.filter((a) => a.status === "running").length || 0;

            return (
              <div key={msg.id} className="space-y-2">
                {msg.role === "user" ? (
                  <div className="flex justify-end">
                    <div className="bg-[#21262D] text-zinc-100 px-3 py-2 rounded-xl max-w-[85%] text-xs font-sans leading-relaxed">
                      {msg.text}
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-zinc-200 leading-relaxed font-sans space-y-2.5">
                    {/* Live / Completed Activity Stream Container */}
                    {hasActivities && (
                      <div className="bg-[#161B22]/80 border border-[#30363D] rounded-lg p-2 font-mono text-[11px] space-y-1.5 shadow-sm">
                        {/* Header with expand/collapse toggle */}
                        <div
                          onClick={() => toggleActivityExpand(msg.id)}
                          className="flex items-center justify-between text-zinc-400 hover:text-zinc-200 cursor-pointer select-none pb-1 border-b border-zinc-800/60"
                        >
                          <div className="flex items-center gap-1.5 font-sans font-medium text-[11px]">
                            {runningCount > 0 ? (
                              <span className="relative flex h-2 w-2 mr-0.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-500"></span>
                              </span>
                            ) : (
                              <Check className="w-3 h-3 text-emerald-400" />
                            )}
                            <span>
                              {runningCount > 0
                                ? "Investigating & executing..."
                                : `${completedCount} ${completedCount === 1 ? "operation" : "operations"} completed`}
                            </span>
                          </div>

                          <div className="flex items-center gap-1 text-[10px] text-zinc-500">
                            {isMsgExpanded ? (
                              <ChevronDown className="w-3 h-3" />
                            ) : (
                              <ChevronRight className="w-3 h-3" />
                            )}
                          </div>
                        </div>

                        {/* Activity Item List */}
                        {isMsgExpanded && (
                          <div className="space-y-1.5 pt-1">
                            {msg.activityItems!.map((item) => (
                              <div
                                key={item.id}
                                className={`flex items-start justify-between gap-2 text-zinc-300 py-0.5 rounded transition-colors ${
                                  item.status === "running" ? "bg-purple-950/20 px-1" : ""
                                }`}
                              >
                                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                                  {renderActivityIcon(item.type, item.status)}

                                  <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                      {item.file ? (
                                        <button
                                          type="button"
                                          onClick={() => onSelectFile?.(item.file!)}
                                          title={`Open ${item.file}`}
                                          className="text-left font-mono text-purple-300 hover:text-purple-200 hover:underline cursor-pointer truncate"
                                        >
                                          {item.title}
                                        </button>
                                      ) : (
                                        <span className="text-zinc-300 truncate">{item.title}</span>
                                      )}

                                       {/* Line range badge if available */}
                                       {(item.startLine !== undefined || (item as any).start_line !== undefined) && (
                                         <span className="text-[10px] font-mono bg-purple-950/70 text-purple-300 px-1.5 py-0.5 rounded border border-purple-700/60 shrink-0 inline-flex items-center gap-1 shadow-sm">
                                           {((item.startLine === 1 || (item as any).start_line === 1) && (item.endLine ?? (item as any).end_line) > 1) ? (
                                             <>
                                               <span className="text-purple-300 font-semibold">Full file</span>
                                               <span className="text-purple-400/50">·</span>
                                               <span>L1–L{item.endLine ?? (item as any).end_line}</span>
                                             </>
                                           ) : (
                                             <>
                                               <span>L{item.startLine ?? (item as any).start_line}</span>
                                               <span>–</span>
                                               <span>{item.endLine ?? (item as any).end_line ?? (item.startLine ?? (item as any).start_line)}</span>
                                             </>
                                           )}
                                         </span>
                                       )}

                                      {/* Symbol detail */}
                                      {item.symbol && item.file && (
                                        <span className="text-[10px] text-indigo-300 truncate">
                                          ({item.symbol})
                                        </span>
                                      )}
                                    </div>

                                    {/* Error text if failed */}
                                    {item.error && (
                                      <p className="text-[10px] text-rose-400 mt-0.5">
                                        {item.error}
                                      </p>
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Markdown Content (Rendered Answer / Plan Summary) */}
                    {msg.text ? (
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
                    ) : (
                      msg.isLoading && (
                        <div className="flex items-center gap-2 text-zinc-400 font-sans text-xs pt-1">
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-500"></span>
                          </span>
                          <span>Synthesizing answer...</span>
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>
            );
          })
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