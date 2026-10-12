'use client';

import React from 'react';
import { AgentInfo } from '@/types/investigation';
import { Bot, Cpu, CheckCircle2, AlertCircle, Clock, ShieldCheck, Zap } from 'lucide-react';

interface AgentCardGridProps {
  agents: AgentInfo[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
}

export const AgentCardGrid: React.FC<AgentCardGridProps> = ({
  agents,
  selectedAgentId,
  onSelectAgent,
}) => {
  if (agents.length === 0) {
    return (
      <div className="p-4 rounded-xl border border-dashed border-slate-200 dark:border-slate-800 text-center text-xs text-slate-500">
        No active agents spawned yet. Start an inquiry above.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {agents.map((agent) => {
        const isSelected = agent.agent_id === selectedAgentId;
        return (
          <button
            key={agent.agent_id}
            onClick={() => onSelectAgent(agent.agent_id)}
            className={`text-left p-3.5 rounded-xl border transition-all flex flex-col justify-between gap-3 ${
              isSelected
                ? 'bg-blue-50/80 dark:bg-blue-950/40 border-blue-500 shadow-sm ring-1 ring-blue-500/50'
                : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
            }`}
          >
            {/* Header: Agent Role & Status Badge */}
            <div className="flex items-start justify-between gap-2 w-full">
              <div className="flex items-center gap-2">
                <div
                  className={`p-1.5 rounded-lg ${
                    agent.is_local
                      ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400'
                      : 'bg-indigo-100 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
                  }`}
                >
                  <Bot className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-900 dark:text-slate-100 font-mono">
                    {agent.agent_id}
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
                    {agent.role}
                  </div>
                </div>
              </div>

              {/* Status Indicator */}
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                  agent.status === 'completed'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                    : agent.status === 'running'
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 animate-pulse'
                    : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                }`}
              >
                {agent.status}
              </span>
            </div>

            {/* Model & Local/Hosted badge */}
            <div className="flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-300">
              <Cpu className="w-3.5 h-3.5 text-slate-400" />
              <span className="font-mono truncate">{agent.model}</span>
              <span
                className={`px-1.5 py-0.2 rounded text-[9px] font-semibold uppercase ${
                  agent.is_local
                    ? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'
                    : 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300'
                }`}
              >
                {agent.is_local ? 'Local Ollama' : 'Hosted Cloud'}
              </span>
            </div>

            {/* Current Task description */}
            <div className="text-xs text-slate-700 dark:text-slate-300 line-clamp-2 bg-slate-50 dark:bg-slate-950/60 p-2 rounded-lg border border-slate-100 dark:border-slate-800/80">
              <span className="text-slate-400 text-[10px] uppercase font-semibold block mb-0.5">Task</span>
              {agent.current_task || agent.summary || 'Ready'}
            </div>
          </button>
        );
      })}
    </div>
  );
};
