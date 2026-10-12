'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  Bot,
  Layers,
  FileCode2,
  CheckCircle2,
  Radio,
  Clock,
  Square,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Copy,
  Check,
  Eye,
  EyeOff,
  Maximize2,
  Minimize2,
  ArrowRight
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AgentInfo,
  TaskItem,
  FindingItem,
  ToolActivityItem,
  TimelineEvent,
  ChatMessage
} from '@/types/investigation';
import { InvestigationChatPanel } from './InvestigationChatPanel';
import { InvestigationAgentCards } from './InvestigationAgentCards';
import { InvestigationTimeline } from './InvestigationTimeline';
import { InvestigationAgentInspector } from './InvestigationAgentInspector';

interface MultiAgentInvestigationViewProps {
  repoName: string;
}

export const MultiAgentInvestigationView: React.FC<MultiAgentInvestigationViewProps> = ({ repoName }) => {
  // State
  const [repoHash, setRepoHash] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'failed' | 'cancelled'>('idle');
  const [currentQuery, setCurrentQuery] = useState('');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [finalAnswer, setFinalAnswer] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Agent Brain visibility preferences:
  // - Starts false (user opens tab as normal chatbot)
  // - Turns true automatically when backend emits agent/plan events
  // - User can toggle hide/unhide anytime
  const [hasTriggeredBrain, setHasTriggeredBrain] = useState<boolean>(false);
  const [isBrainVisible, setIsBrainVisible] = useState<boolean>(false);

  // Filter & Tabs for central visualizer
  const [activeCenterTab, setActiveCenterTab] = useState<'timeline' | 'tasks' | 'evidence' | 'files'>('timeline');
  const [agentFilter, setAgentFilter] = useState<string>('all');
  const [filterDropdownOpen, setFilterDropdownOpen] = useState(false);
  const [isFindingsMinimized, setIsFindingsMinimized] = useState<boolean>(false);

  // Multi-agent entities
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [toolActivity, setToolActivity] = useState<ToolActivityItem[]>([]);
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  // Models
  const [availableModels, setAvailableModels] = useState<Record<string, string>>({});
  const [selectedModel, setSelectedModel] = useState<string>('qwen3:4b-instruct');

  // Timer & abort controller
  const startTimeRef = useRef<number>(0);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 1. Fetch available models & resolve repo hash
  useEffect(() => {
    async function loadModelsAndHash() {
      try {
        const resModels = await fetch('/api/llm/models');
        if (resModels.ok) {
          const mData = await resModels.json();
          if (mData.models) {
            setAvailableModels(mData.models);
            const firstModel = Object.keys(mData.models)[0];
            if (firstModel) setSelectedModel(firstModel);
          }
        }
      } catch (err) {
        console.warn('Failed to load LLM models:', err);
      }

      try {
        const resHash = await fetch(`/api/repos/lookup-hash?name=${encodeURIComponent(repoName)}`);
        if (resHash.ok) {
          const hData = await resHash.json();
          if (hData.repository_hash) {
            setRepoHash(hData.repository_hash);
          }
        }
      } catch (err) {
        console.warn('Failed to lookup repo hash:', err);
      }
    }

    loadModelsAndHash();
  }, [repoName]);

  // Elapsed timer handler
  useEffect(() => {
    if (running) {
      startTimeRef.current = Date.now();
      timerIntervalRef.current = setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);
    } else {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    }
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, [running]);

  const formatTimestamp = (date: Date = new Date()) => {
    return date.toTimeString().split(' ')[0];
  };

  // Helper to add timeline event
  const appendTimelineEvent = (event: Omit<TimelineEvent, 'id' | 'timestamp' | 'formatted_time'>) => {
    const now = Date.now();
    const formatted = formatTimestamp(new Date(now));
    const newEv: TimelineEvent = {
      ...event,
      id: `ev_${now}_${Math.random().toString(36).substring(2, 7)}`,
      timestamp: now,
      formatted_time: formatted,
    };
    setTimelineEvents((prev) => [...prev, newEv]);
  };

  // Start new prompt / investigation
  const handleStartInvestigation = async (queryText: string) => {
    if (!queryText.trim() || running) return;

    setCurrentQuery(queryText);
    setRunning(true);
    setStatus('running');
    setFinalAnswer(null);
    setAgents([]);
    setTasks([]);
    setFindings([]);
    setToolActivity([]);
    setTimelineEvents([]);
    setSelectedAgentId(null);
    setElapsedSeconds(0);

    // Append user message immediately
    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      role: 'user',
      content: queryText,
      timestamp: formatTimestamp(),
    };

    // Acknowledge assistant message (starts as normal conversational answer or thinking)
    const botMsgId = `assistant_${Date.now()}`;
    const botMsg: ChatMessage = {
      id: botMsgId,
      role: 'assistant',
      content: `I'm analyzing your request for **${repoName}**...`,
      timestamp: formatTimestamp(),
    };

    setMessages((prev) => [...prev, userMsg, botMsg]);

    appendTimelineEvent({
      type: 'investigation-start',
      title: 'Investigation initialized',
      description: `Target question: ${queryText}`,
    });

    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;

    try {
      const response = await fetch('/api/llm/analyze/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortCtrl.signal,
        body: JSON.stringify({
          query: queryText,
          repo_hash: repoHash || repoName,
          model: selectedModel,
          show_tool_details: true,
          investigation_mode: 'multi_agent',
        }),
      });

      if (!response.ok) {
        throw new Error(`Investigation failed with status ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No stream body received');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines[lines.length - 1];

        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i].trim();
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              processEvent(data, botMsgId);
            } catch (jsonErr) {
              // Ignore non-json lines or keepalives
            }
          }
        }
      }

      // Process any trailing SSE event remaining in buffer after stream closes
      if (buffer.trim().length > 0) {
        const remainingLines = buffer.split('\n');
        for (const lineRaw of remainingLines) {
          const line = lineRaw.trim();
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              processEvent(data, botMsgId);
            } catch (jsonErr) {
              // Ignore non-json
            }
          }
        }
      }

      setStatus('completed');
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setStatus('cancelled');
        appendTimelineEvent({
          type: 'error',
          title: 'Investigation stopped by user',
          status: 'failed',
        });
      } else {
        setStatus('failed');
        appendTimelineEvent({
          type: 'error',
          title: 'Investigation failed',
          description: err.message,
          status: 'failed',
        });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === botMsgId
              ? { ...m, content: `Error during investigation: ${err.message}` }
              : m
          )
        );
      }
    } finally {
      setRunning(false);
      abortControllerRef.current = null;
    }
  };

  // Process incoming SSE events from backend orchestrator
  const processEvent = (data: any, currentBotMsgId?: string) => {
    // Whenever an agent or planner activity is detected, mark brain triggered and reveal brain
    if (
      data.type === 'agent-spawn' ||
      data.type === 'plan-created' ||
      data.type === 'task-discovered' ||
      data.type === 'tool-call'
    ) {
      setHasTriggeredBrain(true);
      setIsBrainVisible(true);
    }

    if (data.type === 'agent-spawn') {
      const newAgent: AgentInfo = {
        agent_id: data.agent_id,
        role: data.role || 'Explorer',
        model: data.model || selectedModel,
        provider: data.provider || 'ollama',
        is_local: data.is_local ?? true,
        status: data.status || 'running',
        current_task: data.current_task,
        task_id: data.task_id,
        acceptance_criteria: data.acceptance_criteria,
        tool_calls_count: 0,
      };

      setAgents((prev) => {
        const idx = prev.findIndex((a) => a.agent_id === data.agent_id);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = { ...updated[idx], ...newAgent };
          return updated;
        }
        return [...prev, newAgent];
      });

      setSelectedAgentId((prev) => prev || data.agent_id);

      appendTimelineEvent({
        type: 'agent-spawn',
        agent_id: data.agent_id,
        title: `Spawned ${data.role || data.agent_id}`,
        description: data.current_task,
      });
    } else if (data.type === 'agent-update') {
      setAgents((prev) =>
        prev.map((a) =>
          a.agent_id === data.agent_id
            ? {
                ...a,
                status: data.status || a.status,
                current_task: data.current_task || a.current_task,
                summary: data.summary || a.summary,
              }
            : a
        )
      );

      if (data.summary) {
        appendTimelineEvent({
          type: 'agent-update',
          agent_id: data.agent_id,
          title: data.summary,
        });
      }
    } else if (data.type === 'plan-created') {
      if (Array.isArray(data.tasks)) {
        setTasks(data.tasks);
      }
      appendTimelineEvent({
        type: 'plan-created',
        agent_id: 'planner-main',
        title: 'Created investigation plan and spawned sub-agents',
        description: data.message,
      });
    } else if (data.type === 'task-update') {
      setTasks((prev) =>
        prev.map((t) =>
          t.id === data.task_id
            ? {
                ...t,
                status: data.status || t.status,
                assigned_agent: data.assigned_agent || t.assigned_agent,
                findings_count: data.findings_count ?? t.findings_count,
                files_inspected: data.files_inspected || t.files_inspected,
              }
            : t
        )
      );

      appendTimelineEvent({
        type: 'task-update',
        agent_id: data.assigned_agent,
        title: `Task ${data.task_id} updated: ${data.status}`,
      });
    } else if (data.type === 'task-discovered') {
      if (data.task) {
        setTasks((prev) => {
          if (prev.some((t) => t.id === data.task.id)) return prev;
          return [...prev, data.task];
        });
        appendTimelineEvent({
          type: 'task-discovered',
          title: `Discovered new subtask: ${data.task.title}`,
        });
      }
    } else if (data.type === 'tool-call') {
      setAgents((prev) =>
        prev.map((a) =>
          a.agent_id === data.agent_id
            ? { ...a, tool_calls_count: (a.tool_calls_count || 0) + 1 }
            : a
        )
      );

      const toolCallId = data.tool_call_id || `tc_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
      
      setToolActivity((prev) => [
        ...prev,
        {
          id: toolCallId,
          timestamp: Date.now(),
          agent_id: data.agent_id,
          task_id: data.task_id,
          tool_name: data.tool_name,
          arguments: data.arguments,
        },
      ]);

      appendTimelineEvent({
        type: 'tool-call',
        tool_call_id: toolCallId,
        agent_id: data.agent_id,
        tool_name: data.tool_name,
        arguments: data.arguments,
        status: 'running',
        title: `Executing ${data.tool_name}`,
        file_path: data.arguments?.path || data.arguments?.file_path,
      });
    } else if (data.type === 'tool-response') {
      const toolCallId = data.tool_call_id;

      setToolActivity((prev) => {
        // Merge into the matching tool call by tool_call_id, or fallback to matching recent tool call for this agent & tool
        const idx = [...prev].reverse().findIndex(
          (t) => (toolCallId && t.id === toolCallId) || (!toolCallId && t.tool_name === data.tool_name && (!data.agent_id || t.agent_id === data.agent_id))
        );
        if (idx !== -1) {
          const actualIndex = prev.length - 1 - idx;
          const updated = [...prev];
          updated[actualIndex] = {
            ...updated[actualIndex],
            success: data.success,
            result_summary: data.result_summary,
            duration_ms: data.duration_ms,
          };
          return updated;
        }
        return [
          ...prev,
          {
            id: toolCallId,
            timestamp: Date.now(),
            agent_id: data.agent_id,
            task_id: data.task_id,
            tool_name: data.tool_name,
            success: data.success,
            result_summary: data.result_summary,
            duration_ms: data.duration_ms,
          },
        ];
      });

      // Update the existing tool-call timeline event so it displays the completed status and response payload
      setTimelineEvents((prev) => {
        const idx = [...prev].reverse().findIndex(
          (e) => (toolCallId && e.tool_call_id === toolCallId) ||
                 (e.type === 'tool-call' && e.tool_name === data.tool_name && (!data.agent_id || e.agent_id === data.agent_id))
        );
        if (idx !== -1) {
          const actualIndex = prev.length - 1 - idx;
          const updated = [...prev];
          const isSuccess = data.success !== false;
          updated[actualIndex] = {
            ...updated[actualIndex],
            status: isSuccess ? 'completed' : 'failed',
            success: isSuccess,
            error: data.error,
            title: isSuccess ? `Completed ${data.tool_name}` : `Failed ${data.tool_name}`,
            result_summary: data.result_summary !== undefined ? data.result_summary : updated[actualIndex].result_summary,
            code_excerpt: data.code_excerpt || updated[actualIndex].code_excerpt,
            line_start: data.line_start || updated[actualIndex].line_start,
            line_end: data.line_end || updated[actualIndex].line_end,
            file_path: data.file_path || updated[actualIndex].file_path,
            duration_s: data.duration_ms ? Number((data.duration_ms / 1000).toFixed(2)) : updated[actualIndex].duration_s,
          };
          return updated;
        }
        // If no prior tool-call event was recorded, create one coherent completed entry
        const now = Date.now();
        return [
          ...prev,
          {
            id: `ev_${now}_${Math.random().toString(36).substring(2, 7)}`,
            timestamp: now,
            formatted_time: formatTimestamp(new Date(now)),
            type: 'tool-call',
            tool_call_id: toolCallId,
            agent_id: data.agent_id,
            tool_name: data.tool_name,
            status: data.success !== false ? 'completed' : 'failed',
            success: data.success !== false,
            error: data.error,
            result_summary: data.result_summary,
            code_excerpt: data.code_excerpt,
            line_start: data.line_start,
            line_end: data.line_end,
            file_path: data.file_path,
            title: data.success !== false ? `Completed ${data.tool_name}` : `Failed ${data.tool_name}`,
            duration_s: data.duration_ms ? Number((data.duration_ms / 1000).toFixed(2)) : undefined,
          },
        ];
      });
    } else if (data.type === 'finding-saved') {
      if (data.finding) {
        setFindings((prev) => [...prev, data.finding]);

        appendTimelineEvent({
          type: 'finding-saved',
          agent_id: data.finding.agent_id,
          title: `Verified finding: ${data.finding.summary}`,
          file_path: data.finding.file_path,
          line_start: data.finding.line_start,
          line_end: data.finding.line_end,
          code_excerpt: data.finding.code_excerpt,
          finding: data.finding,
        });
      }
    } else if (data.type === 'memory-update') {
      appendTimelineEvent({
        type: 'memory-update',
        agent_id: data.agent_id,
        title: data.title || `Worker contributed to main agent memory dossier`,
        result_summary: {
          findings_returned: data.findings || [],
          files_read: data.files_read || [],
          coverage_gaps: data.coverage_gaps || [],
        },
      });
    } else if (data.type === 'final-answer') {
      setFinalAnswer(data.content);

      // Update the active assistant message with the final grounded answer
      setMessages((prev) => {
        if (currentBotMsgId && prev.some((m) => m.id === currentBotMsgId)) {
          return prev.map((m) =>
            m.id === currentBotMsgId ? { ...m, content: data.content } : m
          );
        }
        return [
          ...prev,
          {
            id: `ans_${Date.now()}`,
            role: 'assistant',
            content: data.content,
            timestamp: formatTimestamp(),
          },
        ];
      });

      appendTimelineEvent({
        type: 'final-answer',
        agent_id: 'planner-main',
        title: 'Synthesized final verified response',
      });
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleCopy = () => {
    if (!finalAnswer) return;
    navigator.clipboard.writeText(finalAnswer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Filtered timeline
  const filteredTimeline = timelineEvents.filter((ev) => {
    if (agentFilter === 'all') return true;
    return ev.agent_id === agentFilter;
  });

  const selectedAgent = agents.find((a) => a.agent_id === selectedAgentId) || agents[0] || null;

  // Compute completed tasks percentage
  const completedTasks = tasks.filter((t) => t.status === 'COMPLETED').length;
  const progressPercent = tasks.length > 0 ? Math.round((completedTasks / tasks.length) * 100) : 0;

  // Unique files inspected across all findings
  const uniqueFiles = Array.from(new Set(findings.map((f) => f.file_path))).filter(Boolean);

  return (
    <div className="flex h-full w-full bg-slate-50 dark:bg-[#070D1D] text-slate-800 dark:text-slate-100 overflow-hidden font-sans">
      {/* 1. Chatbot View (Default full-width or left panel) */}
      <InvestigationChatPanel
        messages={messages}
        running={running}
        onSendMessage={handleStartInvestigation}
        onNewInvestigation={() => {
          setMessages([]);
          setTimelineEvents([]);
          setFindings([]);
          setTasks([]);
          setAgents([]);
          setFinalAnswer(null);
          setStatus('idle');
          setHasTriggeredBrain(false);
          setIsBrainVisible(false);
        }}
        selectedModel={selectedModel}
        onSelectModel={setSelectedModel}
        availableModels={availableModels}
        tasks={tasks}
        hasTriggeredBrain={hasTriggeredBrain}
        isBrainVisible={isBrainVisible}
        onToggleBrain={() => setIsBrainVisible((prev) => !prev)}
        isFullScreenChat={!isBrainVisible}
      />

      {/* 2. Multi-Agent Brain & Execution Visualizer (Appears when agents trigger, hideable anytime) */}
      {isBrainVisible && (
        <div className="flex-1 flex h-full overflow-hidden min-w-0 border-l border-slate-200 dark:border-[#1D2B43] animate-in fade-in duration-200">
          {/* Main Visualizer (Timeline & Tasks) */}
          <div className="flex-1 flex flex-col h-full bg-slate-50 dark:bg-[#070D1D] overflow-hidden min-w-[400px]">
            {/* Top Execution Status Bar */}
            <div className="h-14 px-4 border-b border-slate-200 dark:border-[#1D2B43] flex items-center justify-between flex-shrink-0 bg-white dark:bg-[#070D1D]">
              <div className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-lg bg-blue-100 dark:bg-blue-950 border border-blue-200 dark:border-blue-800/40 flex items-center justify-center text-blue-600 dark:text-blue-400">
                  <Bot className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">Brain</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider ${
                        running
                          ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-800 animate-pulse'
                          : status === 'completed'
                          ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400 border border-blue-300 dark:border-blue-800'
                          : 'bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                      }`}
                    >
                      {running ? '● Running' : status === 'completed' ? 'Completed' : 'Ready'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Status metrics: Elapsed, Agent count, Progress %, Stop Button & Hide Button */}
              <div className="flex items-center gap-3 text-xs font-mono text-slate-500 dark:text-slate-400">
                {running && (
                  <span className="flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" />
                    <span>{elapsedSeconds}s</span>
                  </span>
                )}

                <span>{agents.length} agents</span>
                <span>{progressPercent}% complete</span>

                {running && (
                  <button
                    onClick={handleStop}
                    className="px-2.5 py-1 rounded bg-red-100 hover:bg-red-200 dark:bg-red-950/80 dark:hover:bg-red-900 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 font-medium text-xs flex items-center gap-1.5 transition-colors"
                  >
                    <Square className="w-3 h-3 fill-current" />
                    <span>Stop</span>
                  </button>
                )}

                {/* Quick hide visualizer toggle */}
                <button
                  onClick={() => setIsBrainVisible(false)}
                  title="Hide visualizer and return to full chatbot"
                  className="p-1.5 rounded-lg bg-slate-100 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] hover:text-slate-900 dark:hover:text-white text-slate-500 dark:text-slate-400 transition-colors"
                >
                  <EyeOff className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Top Agent Overview Grid */}
            <div className="p-3 border-b border-slate-200 dark:border-[#1D2B43] bg-slate-100/70 dark:bg-[#0A1224] flex-shrink-0">
              <InvestigationAgentCards
                agents={agents}
                selectedAgentId={selectedAgentId}
                onSelectAgent={(id) => setSelectedAgentId(id)}
                completedTasksCount={completedTasks}
                totalTasksCount={tasks.length}
              />
            </div>

            {/* Middle Filter & Sub-Navigation Tabs */}
            <div className="h-10 px-4 border-b border-slate-200 dark:border-[#1D2B43] flex items-center justify-between flex-shrink-0 bg-white dark:bg-[#070D1D] text-xs font-medium">
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setActiveCenterTab('timeline')}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    activeCenterTab === 'timeline'
                      ? 'bg-blue-100 dark:bg-[#15233E] text-blue-700 dark:text-blue-400 font-semibold'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  Timeline
                </button>
                <button
                  onClick={() => setActiveCenterTab('tasks')}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    activeCenterTab === 'tasks'
                      ? 'bg-blue-100 dark:bg-[#15233E] text-blue-700 dark:text-blue-400 font-semibold'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  Tasks ({tasks.length})
                </button>
                <button
                  onClick={() => setActiveCenterTab('evidence')}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    activeCenterTab === 'evidence'
                      ? 'bg-blue-100 dark:bg-[#15233E] text-blue-700 dark:text-blue-400 font-semibold'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  Evidence ({findings.length})
                </button>
                <button
                  onClick={() => setActiveCenterTab('files')}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    activeCenterTab === 'files'
                      ? 'bg-blue-100 dark:bg-[#15233E] text-blue-700 dark:text-blue-400 font-semibold'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  Files ({uniqueFiles.length})
                </button>
              </div>

              {/* Agent Filter Dropdown & Live pulse indicator */}
              <div className="flex items-center gap-2">
                <div className="relative">
                  <button
                    onClick={() => setFilterDropdownOpen(!filterDropdownOpen)}
                    className="px-2 py-0.5 rounded bg-slate-100 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] text-slate-700 dark:text-slate-300 text-xs flex items-center gap-1 font-mono"
                  >
                    <span>{agentFilter === 'all' ? 'All Agents' : agentFilter}</span>
                    <ChevronDown className="w-3 h-3 text-slate-500" />
                  </button>

                  {filterDropdownOpen && (
                    <div className="absolute right-0 top-full mt-1 w-36 rounded-lg bg-white dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] shadow-xl py-1 z-30 font-mono text-xs">
                      <button
                        onClick={() => {
                          setAgentFilter('all');
                          setFilterDropdownOpen(false);
                        }}
                        className={`w-full px-2.5 py-1 text-left hover:bg-slate-100 dark:hover:bg-[#15233E] ${
                          agentFilter === 'all' ? 'text-blue-600 dark:text-blue-400 font-semibold' : 'text-slate-700 dark:text-slate-300'
                        }`}
                      >
                        All Agents
                      </button>
                      {agents.map((a) => (
                        <button
                          key={a.agent_id}
                          onClick={() => {
                            setAgentFilter(a.agent_id);
                            setFilterDropdownOpen(false);
                          }}
                          className={`w-full px-2.5 py-1 text-left hover:bg-slate-100 dark:hover:bg-[#15233E] truncate ${
                            agentFilter === a.agent_id ? 'text-blue-600 dark:text-blue-400 font-semibold' : 'text-slate-700 dark:text-slate-300'
                          }`}
                        >
                          {a.agent_id}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400 font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping"></span>
                  <span>Live</span>
                </div>
              </div>
            </div>

            {/* Scrollable Center Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {activeCenterTab === 'timeline' && (
                <InvestigationTimeline
                  events={filteredTimeline}
                  selectedAgentId={selectedAgentId}
                  onSelectAgent={(id) => setSelectedAgentId(id)}
                  onOpenFinding={(f) => setActiveCenterTab('evidence')}
                />
              )}

              {activeCenterTab === 'tasks' && (
                <div className="space-y-2">
                  {tasks.length === 0 ? (
                    <div className="text-center py-12 text-slate-400 dark:text-slate-500 text-xs font-mono">
                      No investigation tasks planned yet.
                    </div>
                  ) : (
                    tasks.map((task, idx) => (
                      <div
                        key={task.id || idx}
                        className="p-3 rounded-xl bg-white dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] flex items-start justify-between gap-3 text-xs shadow-sm"
                      >
                        <div className="space-y-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-slate-400 dark:text-slate-500">{task.id}</span>
                            <span className="font-medium text-slate-800 dark:text-slate-200 truncate">{task.title}</span>
                          </div>
                          <div className="text-slate-500 dark:text-slate-400 text-[11px]">{task.description}</div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0 font-mono text-[10px]">
                          <span
                            className={`px-2 py-0.5 rounded border uppercase font-bold ${
                              task.status === 'COMPLETED'
                                ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800/40'
                                : task.status === 'RUNNING'
                                ? 'bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-400 border-blue-300 dark:border-blue-800/40 animate-pulse'
                                : 'bg-slate-100 dark:bg-slate-900 text-slate-500 border-slate-300 dark:border-slate-800'
                            }`}
                          >
                            {task.status}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {activeCenterTab === 'evidence' && (
                <div className="space-y-2">
                  {findings.length === 0 ? (
                    <div className="text-center py-12 text-slate-400 dark:text-slate-500 text-xs font-mono">
                      No verified findings collected yet.
                    </div>
                  ) : (
                    findings.map((finding) => (
                      <div
                        key={finding.id}
                        className="p-3 rounded-xl bg-white dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] space-y-2 text-xs shadow-sm"
                      >
                        <div className="flex items-center justify-between text-slate-700 dark:text-slate-300">
                          <span className="font-semibold text-slate-900 dark:text-white">{finding.summary}</span>
                          <span className="font-mono text-[10px] text-blue-600 dark:text-blue-400 px-1.5 py-0.5 rounded bg-blue-50 dark:bg-[#111C31] border border-blue-200 dark:border-[#1D2B43]">
                            {finding.file_path} {finding.line_start && `L${finding.line_start}-${finding.line_end}`}
                          </span>
                        </div>
                        {finding.code_excerpt && (
                          <pre className="p-2 rounded bg-slate-50 dark:bg-[#070D1D] border border-slate-200 dark:border-[#1D2B43]/50 font-mono text-[11px] text-slate-800 dark:text-slate-300 overflow-x-auto whitespace-pre">
                            {finding.code_excerpt}
                          </pre>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}

              {activeCenterTab === 'files' && (
                <div className="space-y-2">
                  {uniqueFiles.length === 0 ? (
                    <div className="text-center py-12 text-slate-400 dark:text-slate-500 text-xs font-mono">
                      No repository files inspected yet.
                    </div>
                  ) : (
                    uniqueFiles.map((file) => (
                      <div
                        key={file}
                        className="p-2.5 rounded-lg bg-white dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] flex items-center justify-between text-xs font-mono text-slate-700 dark:text-slate-300 shadow-sm"
                      >
                        <div className="flex items-center gap-2 truncate">
                          <FileCode2 className="w-4 h-4 text-blue-500 dark:text-blue-400 flex-shrink-0" />
                          <span className="truncate">{file}</span>
                        </div>
                        <span className="text-[10px] text-slate-400 dark:text-slate-500">Verified</span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            {/* Bottom Verified Findings Banner */}
            <div className="p-2.5 border-t border-slate-200 dark:border-[#1D2B43] bg-white dark:bg-[#0A1224] flex-shrink-0 text-xs transition-all">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white">
                  <div className="w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  </div>
                  <span>Verified Findings ({findings.length})</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setActiveCenterTab('evidence')}
                    className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline font-mono"
                  >
                    View all ({findings.length})
                  </button>
                  <button
                    onClick={() => setIsFindingsMinimized((prev) => !prev)}
                    className="p-1 rounded hover:bg-slate-100 dark:hover:bg-[#15233E] text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
                    title={isFindingsMinimized ? 'Expand Verified Findings' : 'Minimize Verified Findings'}
                  >
                    {isFindingsMinimized ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>

              {!isFindingsMinimized && (
                <div className="mt-1.5">
                  {findings.length > 0 ? (
                    <div className="space-y-1 max-h-20 overflow-y-auto">
                      {findings.slice(0, 2).map((f, idx) => (
                        <div
                          key={f.id}
                          className="flex items-center justify-between gap-2 p-1.5 rounded-lg bg-slate-50 dark:bg-[#070D1D] border border-slate-200 dark:border-[#1D2B43]/70 text-[11px]"
                        >
                          <div className="flex items-center gap-1.5 truncate">
                            <span className="text-slate-400 dark:text-slate-500 font-mono">{idx + 1}</span>
                            <span className="text-slate-700 dark:text-slate-300 truncate">{f.summary}</span>
                          </div>
                          <span className="text-blue-600 dark:text-blue-400 px-1 py-0.5 rounded bg-blue-50 dark:bg-[#111C31] border border-blue-200 dark:border-[#1D2B43] font-mono text-[10px] flex-shrink-0">
                            {f.file_path} {f.line_start && `L${f.line_start}`}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[11px] text-slate-400 dark:text-slate-500 font-mono">
                      No verified findings recorded yet.
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Final Answer Banner if available */}
            {finalAnswer && (
              <div className="p-3 border-t border-emerald-900/60 bg-emerald-950/20 text-xs space-y-1.5 flex-shrink-0 max-h-40 overflow-y-auto">
                <div className="flex items-center justify-between text-emerald-400 font-bold">
                  <span className="flex items-center gap-1.5">
                    <Sparkles className="w-4 h-4" />
                    Final Grounded Synthesis
                  </span>
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-emerald-900/40 border border-emerald-700/50 hover:bg-emerald-800/40 text-emerald-300 transition-colors"
                  >
                    {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    <span>{copied ? 'Copied' : 'Copy Answer'}</span>
                  </button>
                </div>
                <div className="prose prose-invert max-w-none text-slate-200 text-xs leading-relaxed">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{finalAnswer}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>

          {/* Right Agent Inspector Panel */}
          {selectedAgent ? (
            <InvestigationAgentInspector
              agent={selectedAgent}
              toolActivity={toolActivity}
              findings={findings}
              tasks={tasks}
              onClose={() => setSelectedAgentId(null)}
              onOpenFinding={(f) => {
                setActiveCenterTab('evidence');
              }}
            />
          ) : (
            <div className="w-[300px] bg-[#070D1D] border-l border-[#1D2B43] flex flex-col items-center justify-center p-6 text-center text-slate-500 text-xs space-y-2">
              <Bot className="w-8 h-8 text-slate-600" />
              <span>Select any agent to inspect its tools and context</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default MultiAgentInvestigationView;
