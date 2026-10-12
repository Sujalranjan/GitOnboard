'use client';

import React, { useState } from 'react';
import {
  X,
  Maximize2,
  Minimize2,
  Cpu,
  Bot,
  Wrench,
  CheckCircle2,
  Clock,
  Layers,
  FileCode2,
  ExternalLink,
  ShieldCheck,
  ChevronDown
} from 'lucide-react';
import { AgentInfo, ToolActivityItem, FindingItem, TaskItem } from '@/types/investigation';

interface AgentInspectorProps {
  agent: AgentInfo;
  toolActivity: ToolActivityItem[];
  findings: FindingItem[];
  tasks: TaskItem[];
  onClose?: () => void;
  onOpenFinding?: (finding: FindingItem) => void;
}

export const InvestigationAgentInspector: React.FC<AgentInspectorProps> = ({
  agent,
  toolActivity,
  findings,
  tasks,
  onClose,
  onOpenFinding,
}) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'tools' | 'context' | 'findings'>('overview');
  const [expandedToolIndex, setExpandedToolIndex] = useState<number | null>(null);

  // Filter tool activity and findings by this agent
  const agentTools = toolActivity.filter((t) => !t.agent_id || t.agent_id === agent.agent_id);
  const agentFindings = findings.filter((f) => !agent.task_id || f.task_id === agent.task_id);
  const isPlanner = agent.agent_id === 'planner-main' || agent.role.toLowerCase().includes('planner');

  return (
    <div className="w-[320px] flex-shrink-0 bg-white dark:bg-[#070D1D] border-l border-slate-200 dark:border-[#1D2B43] flex flex-col h-full text-slate-800 dark:text-slate-200 select-none">
      {/* Header with Agent ID & Controls */}
      <div className="h-14 px-4 border-b border-slate-200 dark:border-[#1D2B43] flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          <span className="text-xs font-bold text-slate-900 dark:text-white tracking-wide">Agent Inspector</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-400">
          {onClose && (
            <button
              onClick={onClose}
              className="p-1 rounded hover:bg-slate-100 dark:hover:bg-[#0D162A] hover:text-slate-900 dark:hover:text-white transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Selected Agent identity card */}
      <div className="p-3 border-b border-slate-200 dark:border-[#1D2B43]/80 bg-slate-50 dark:bg-[#0A1224] flex items-center justify-between">
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
              isPlanner
                ? 'bg-purple-100 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 border border-purple-200 dark:border-purple-800/40'
                : 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/40'
            }`}
          >
            {isPlanner ? <Cpu className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-bold text-slate-900 dark:text-white font-mono truncate">{agent.agent_id}</div>
            <div className="text-[10px] text-slate-500 dark:text-slate-400 truncate">{agent.role}</div>
          </div>
        </div>

        <span
          className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase tracking-wider ${
            agent.status === 'completed'
              ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/50'
              : agent.status === 'running'
              ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-800/50 animate-pulse'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700'
          }`}
        >
          {agent.status}
        </span>
      </div>

      {/* Tab navigation pills */}
      <div className="flex items-center border-b border-slate-200 dark:border-[#1D2B43] px-2 pt-1.5 gap-1 bg-white dark:bg-[#070D1D] text-[11px] font-medium text-slate-500 dark:text-slate-400">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-2.5 py-1.5 border-b-2 transition-all ${
            activeTab === 'overview'
              ? 'border-blue-600 dark:border-[#2165FF] text-blue-600 dark:text-white font-semibold'
              : 'border-transparent hover:text-slate-900 dark:hover:text-slate-200'
          }`}
        >
          Overview
        </button>
        <button
          onClick={() => setActiveTab('tools')}
          className={`px-2.5 py-1.5 border-b-2 transition-all ${
            activeTab === 'tools'
              ? 'border-blue-600 dark:border-[#2165FF] text-blue-600 dark:text-white font-semibold'
              : 'border-transparent hover:text-slate-900 dark:hover:text-slate-200'
          }`}
        >
          Tool Calls ({agentTools.length})
        </button>
        <button
          onClick={() => setActiveTab('context')}
          className={`px-2.5 py-1.5 border-b-2 transition-all ${
            activeTab === 'context'
              ? 'border-blue-600 dark:border-[#2165FF] text-blue-600 dark:text-white font-semibold'
              : 'border-transparent hover:text-slate-900 dark:hover:text-slate-200'
          }`}
        >
          Context
        </button>
        <button
          onClick={() => setActiveTab('findings')}
          className={`px-2.5 py-1.5 border-b-2 transition-all ${
            activeTab === 'findings'
              ? 'border-blue-600 dark:border-[#2165FF] text-blue-600 dark:text-white font-semibold'
              : 'border-transparent hover:text-slate-900 dark:hover:text-slate-200'
          }`}
        >
          Findings ({agentFindings.length})
        </button>
      </div>

      {/* Tab Content Container */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4 text-xs font-sans">
        {/* 1. OVERVIEW TAB */}
        {activeTab === 'overview' && (
          <div className="space-y-4">
            {/* Model & Provider specs */}
            <div className="grid grid-cols-2 gap-2 p-2.5 rounded-xl bg-slate-50 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] text-[11px] font-mono shadow-sm">
              <div>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase block font-bold">Model</span>
                <span className="text-slate-900 dark:text-white font-semibold">{agent.model}</span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase block font-bold">Provider</span>
                <span className="text-amber-600 dark:text-amber-400 font-semibold uppercase">{agent.provider}</span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase block font-bold">Temperature</span>
                <span className="text-slate-600 dark:text-slate-300">0.1</span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase block font-bold">Max Tokens</span>
                <span className="text-slate-600 dark:text-slate-300">4096</span>
              </div>
            </div>

            {/* Current Task */}
            <div className="space-y-1.5">
              <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase font-bold tracking-wider block">
                Current Task
              </span>
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-sans shadow-sm">
                {agent.current_task || agent.acceptance_criteria || 'Executing assigned repository investigation...'}
              </div>
            </div>

            {/* Task Checklist for this agent */}
            <div className="space-y-2">
              <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase font-bold tracking-wider block">
                Subtasks Progress
              </span>
              <div className="space-y-1.5">
                {tasks.map((t) => {
                  const isDone = t.status === 'COMPLETED';
                  const isRun = t.status === 'RUNNING';
                  return (
                    <div
                      key={t.id}
                      className="p-2 rounded-lg bg-slate-50 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] flex items-center justify-between text-[11px] shadow-sm"
                    >
                      <div className="flex items-center gap-2 truncate mr-2">
                        {isDone ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                        ) : isRun ? (
                          <div className="w-3.5 h-3.5 rounded-full border-2 border-blue-600 dark:border-blue-400 border-t-transparent animate-spin flex-shrink-0" />
                        ) : (
                          <div className="w-3.5 h-3.5 rounded-full border border-slate-300 dark:border-slate-600 flex-shrink-0" />
                        )}
                        <span className={`truncate ${isDone ? 'text-slate-400 dark:text-slate-400 line-through' : 'text-slate-800 dark:text-slate-200'}`}>
                          {t.title}
                        </span>
                      </div>
                      <span className="font-mono text-[9px] text-slate-500 uppercase">{t.status}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Recent Tool Calls list preview */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500 uppercase font-bold tracking-wider">
                <span>Recent Tool Calls</span>
                <button onClick={() => setActiveTab('tools')} className="text-blue-600 dark:text-blue-400 hover:underline">
                  View all
                </button>
              </div>

              {agentTools.slice(0, 3).map((t, idx) => (
                <div
                  key={idx}
                  className="p-2 rounded-lg bg-slate-50 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] flex items-center justify-between text-[11px] font-mono shadow-sm"
                >
                  <div className="flex items-center gap-2 truncate">
                    <Wrench className="w-3 h-3 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                    <span className="text-slate-800 dark:text-slate-200 truncate">{t.tool_name}</span>
                  </div>
                  <span className="text-emerald-600 dark:text-emerald-400 text-[10px]">✓</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 2. TOOL CALLS TAB */}
        {activeTab === 'tools' && (
          <div className="space-y-2">
            {agentTools.length === 0 ? (
              <div className="p-4 text-center text-slate-400 dark:text-slate-500 font-mono text-[11px]">
                No tool calls recorded yet for this agent.
              </div>
            ) : (
              agentTools.map((tc, idx) => {
                const isExp = expandedToolIndex === idx;
                return (
                  <div
                    key={idx}
                    className="rounded-xl bg-slate-50 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] overflow-hidden text-[11px] font-mono shadow-sm"
                  >
                    <div
                      onClick={() => setExpandedToolIndex(isExp ? null : idx)}
                      className="p-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100 dark:hover:bg-[#111C31] transition-colors"
                    >
                      <div className="flex items-center gap-2 truncate">
                        <Wrench className="w-3 h-3 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                        <span className="font-semibold text-slate-800 dark:text-slate-200 truncate">{tc.tool_name}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-emerald-600 dark:text-emerald-400">✓</span>
                        <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${isExp ? 'rotate-180' : ''}`} />
                      </div>
                    </div>

                    {isExp && (
                      <div className="p-2.5 border-t border-slate-200 dark:border-[#1D2B43] bg-white dark:bg-[#070D1D] space-y-2 text-[10px]">
                        {tc.arguments && (
                          <div>
                            <span className="text-slate-400 dark:text-slate-500 font-bold uppercase block mb-1">Arguments:</span>
                            <pre className="p-2 rounded bg-slate-50 dark:bg-[#091124] text-slate-800 dark:text-slate-300 overflow-x-auto border border-slate-200 dark:border-transparent">
                              {JSON.stringify(tc.arguments, null, 2)}
                            </pre>
                          </div>
                        )}
                        {tc.result_summary && (
                          <div>
                            <span className="text-slate-400 dark:text-slate-500 font-bold uppercase block mb-1">Result Summary:</span>
                            <pre className="p-2 rounded bg-slate-50 dark:bg-[#091124] text-slate-800 dark:text-slate-300 overflow-x-auto border border-slate-200 dark:border-transparent">
                              {typeof tc.result_summary === 'string'
                                ? tc.result_summary
                                : JSON.stringify(tc.result_summary, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* 3. CONTEXT TAB */}
        {activeTab === 'context' && (
          <div className="space-y-3">
            <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] space-y-2 text-xs shadow-sm">
              <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase font-bold tracking-wider block">
                Assigned Scope & Instructions
              </span>
              <p className="text-slate-700 dark:text-slate-300 leading-relaxed font-sans text-[11px]">
                {agent.acceptance_criteria ||
                  'Investigate the repository using tree-sitter AST, symbol exploration, and code inspection.'}
              </p>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] space-y-2 text-xs shadow-sm">
              <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase font-bold tracking-wider block">
                Retrieved File Evidence ({agentFindings.length} files)
              </span>
              <div className="space-y-1">
                {agentFindings.map((f) => (
                  <div key={f.id} className="font-mono text-[11px] text-blue-600 dark:text-blue-400 flex items-center justify-between">
                    <span className="truncate">{f.file_path}</span>
                    {f.line_start && <span className="text-slate-400 dark:text-slate-500">L{f.line_start}</span>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 4. FINDINGS TAB */}
        {activeTab === 'findings' && (
          <div className="space-y-2">
            {agentFindings.length === 0 ? (
              <div className="p-4 text-center text-slate-400 dark:text-slate-500 font-mono text-[11px]">
                No findings verified yet for this agent.
              </div>
            ) : (
              agentFindings.map((f) => (
                <div
                  key={f.id}
                  className="p-3 rounded-xl bg-slate-50 dark:bg-[#0D162A] border border-slate-200 dark:border-[#1D2B43] space-y-2 text-xs shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                      {f.summary}
                    </span>
                  </div>

                  <div className="font-mono text-[10px] text-slate-500 dark:text-slate-400 flex items-center justify-between">
                    <span className="text-blue-600 dark:text-blue-400 truncate">{f.file_path}</span>
                    {f.line_start && <span>L{f.line_start}-{f.line_end}</span>}
                  </div>

                  {f.code_excerpt && (
                    <pre className="p-2 rounded bg-white dark:bg-[#091124] border border-slate-200 dark:border-[#1D2B43]/50 text-emerald-800 dark:text-emerald-300 text-[10px] font-mono overflow-x-auto">
                      {f.code_excerpt}
                    </pre>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
