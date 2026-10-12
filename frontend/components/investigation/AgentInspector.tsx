'use client';

import React from 'react';
import { AgentInfo, ToolActivityItem, FindingItem } from '@/types/investigation';
import { X, Bot, Cpu, ShieldCheck, Wrench, CheckCircle2, AlertCircle, FileText, ArrowRight } from 'lucide-react';

interface AgentInspectorProps {
  agent: AgentInfo | null;
  toolActivity: ToolActivityItem[];
  findings: FindingItem[];
  onClose: () => void;
}

export const AgentInspector: React.FC<AgentInspectorProps> = ({
  agent,
  toolActivity,
  findings,
  onClose,
}) => {
  if (!agent) return null;

  // Filter tool activity and findings for this agent/task
  const relevantTools = toolActivity.filter(
    (t) => t.agent_id === agent.agent_id || (agent.task_id && t.task_id === agent.task_id)
  );
  const relevantFindings = findings.filter(
    (f) => agent.task_id && f.task_id === agent.task_id
  );

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60">
        <div className="flex items-center gap-3">
          <div
            className={`p-2 rounded-xl ${
              agent.is_local
                ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400'
                : 'bg-indigo-100 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
            }`}
          >
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 font-mono">
              {agent.agent_id}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">{agent.role}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="p-4 space-y-4 overflow-y-auto flex-1 text-xs">
        {/* Model Spec */}
        <div className="grid grid-cols-2 gap-2 bg-slate-50 dark:bg-slate-950/40 p-3 rounded-xl border border-slate-100 dark:border-slate-800">
          <div>
            <span className="text-slate-400 font-semibold uppercase text-[10px] block">Model</span>
            <span className="font-mono text-slate-800 dark:text-slate-200 font-medium">
              {agent.model}
            </span>
          </div>
          <div>
            <span className="text-slate-400 font-semibold uppercase text-[10px] block">Inference</span>
            <span
              className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${
                agent.is_local
                  ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                  : 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300'
              }`}
            >
              {agent.is_local ? 'Local (0 TPM Cost)' : 'Hosted Cloud'}
            </span>
          </div>
        </div>

        {/* Task & Criteria */}
        <div className="space-y-1.5">
          <span className="text-slate-400 font-semibold uppercase text-[10px] block">Current Task</span>
          <div className="bg-slate-50 dark:bg-slate-950/60 p-3 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200">
            {agent.current_task || 'Idle'}
          </div>
          {agent.acceptance_criteria && (
            <div className="mt-1 bg-amber-50 dark:bg-amber-950/20 p-2.5 rounded-xl border border-amber-200/60 dark:border-amber-900/40 text-amber-800 dark:text-amber-300">
              <span className="font-semibold block mb-0.5 text-[10px] uppercase">Acceptance Criteria</span>
              {agent.acceptance_criteria}
            </div>
          )}
        </div>

        {/* Tool Activity Logs */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-slate-400 font-semibold uppercase text-[10px]">
              Tool Calls ({relevantTools.length})
            </span>
          </div>
          {relevantTools.length === 0 ? (
            <div className="text-slate-400 italic bg-slate-50 dark:bg-slate-950/40 p-2.5 rounded-xl border border-slate-100 dark:border-slate-800 text-center">
              No tool executions recorded for this agent.
            </div>
          ) : (
            <div className="space-y-2">
              {relevantTools.map((tc, idx) => (
                <div
                  key={idx}
                  className="bg-slate-50 dark:bg-slate-950/80 p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 font-mono"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-blue-600 dark:text-blue-400 font-bold">
                      {tc.tool_name}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      {tc.success ? '✓ success' : 'pending/run'}
                    </span>
                  </div>
                  {tc.arguments && Object.keys(tc.arguments).length > 0 && (
                    <div className="text-[11px] text-slate-600 dark:text-slate-400 break-all bg-white dark:bg-slate-900 p-1.5 rounded border border-slate-100 dark:border-slate-800">
                      {JSON.stringify(tc.arguments)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Verified Findings */}
        <div className="space-y-2">
          <span className="text-slate-400 font-semibold uppercase text-[10px] block">
            Verified Findings ({relevantFindings.length})
          </span>
          {relevantFindings.length === 0 ? (
            <div className="text-slate-400 italic bg-slate-50 dark:bg-slate-950/40 p-2.5 rounded-xl border border-slate-100 dark:border-slate-800 text-center">
              No findings saved for this agent yet.
            </div>
          ) : (
            <div className="space-y-2">
              {relevantFindings.map((f) => (
                <div
                  key={f.id}
                  className="bg-emerald-50/50 dark:bg-emerald-950/20 p-2.5 rounded-xl border border-emerald-200/60 dark:border-emerald-800/40"
                >
                  <div className="font-semibold text-emerald-800 dark:text-emerald-300 mb-0.5">
                    {f.file_path} {f.line_start && f.line_end ? `(lines ${f.line_start}-${f.line_end})` : ''}
                  </div>
                  <div className="text-slate-700 dark:text-slate-300">{f.summary}</div>
                  {f.code_excerpt && (
                    <pre className="mt-1.5 p-2 bg-slate-900 text-slate-200 rounded text-[10px] overflow-x-auto">
                      {f.code_excerpt}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
