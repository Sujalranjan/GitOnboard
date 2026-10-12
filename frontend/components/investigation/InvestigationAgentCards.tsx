'use client';

import React from 'react';
import { Bot, Cpu, CheckCircle2, AlertCircle, Clock, ArrowRight, Layers } from 'lucide-react';
import { AgentInfo } from '@/types/investigation';

interface AgentOverviewProps {
  agents: AgentInfo[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  completedTasksCount: number;
  totalTasksCount: number;
}

export const InvestigationAgentCards: React.FC<AgentOverviewProps> = ({
  agents,
  selectedAgentId,
  onSelectAgent,
  completedTasksCount,
  totalTasksCount,
}) => {
  if (agents.length === 0) {
    return (
      <div className="p-4 rounded-xl bg-white dark:bg-[#0D162A]/60 border border-slate-200 dark:border-[#1D2B43] flex items-center justify-center text-xs text-slate-500 font-mono">
        Agents will appear here as the planner spawns them...
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 overflow-x-auto pb-1 select-none">
      {agents.map((agent, index) => {
        const isSelected = agent.agent_id === selectedAgentId;
        const isPlanner = agent.agent_id === 'planner-main' || agent.role.toLowerCase().includes('planner');
        const isCompleted = agent.status === 'completed';
        const isRunning = agent.status === 'running';

        return (
          <React.Fragment key={agent.agent_id}>
            <button
              onClick={() => onSelectAgent(agent.agent_id)}
              className={`flex-1 min-w-[210px] max-w-[260px] p-3 rounded-xl border text-left transition-all relative ${
                isSelected
                  ? 'bg-blue-50 dark:bg-[#0E1A33] border-blue-500 dark:border-[#2165FF] ring-1 ring-blue-500 dark:ring-[#2165FF] shadow-lg shadow-blue-500/10'
                  : 'bg-white dark:bg-[#0D162A] border-slate-200 dark:border-[#1D2B43] hover:border-blue-400 dark:hover:border-[#2165FF]/50 hover:bg-slate-50 dark:hover:bg-[#111C31]'
              }`}
            >
              {/* Header: Icon + Name + Status badge */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      isPlanner
                        ? 'bg-purple-100 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 border border-purple-200 dark:border-purple-800/40'
                        : 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/40'
                    }`}
                  >
                    {isPlanner ? <Cpu className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-slate-900 dark:text-white truncate font-mono">
                      {agent.agent_id}
                    </div>
                    <div className="text-[10px] text-slate-500 dark:text-slate-400 truncate">
                      {agent.role}
                    </div>
                  </div>
                </div>

                {/* Status pill */}
                <div
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase tracking-wider ${
                    isCompleted
                      ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-800/50'
                      : isRunning
                      ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400 border border-blue-300 dark:border-blue-800/50 animate-pulse'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700'
                  }`}
                >
                  {agent.status}
                </div>
              </div>

              {/* Model & Host info pills */}
              <div className="mt-2.5 flex items-center gap-1.5 flex-wrap text-[10px] font-mono">
                <span className="text-slate-500 dark:text-slate-400 flex items-center gap-1">
                  <Cpu className="w-2.5 h-2.5 text-slate-400 dark:text-slate-500" />
                  {agent.model}
                </span>

                <span
                  className={`px-1 rounded text-[9px] uppercase font-bold ${
                    agent.is_local
                      ? 'bg-amber-100 dark:bg-amber-950/70 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-800/40'
                      : 'bg-indigo-100 dark:bg-indigo-950/70 text-indigo-800 dark:text-indigo-300 border border-indigo-300 dark:border-indigo-800/40'
                  }`}
                >
                  {agent.is_local ? 'LOCAL OLLAMA' : 'HOSTED CLOUD'}
                </span>
              </div>

              {/* Bottom Progress track */}
              <div className="mt-3 pt-2 border-t border-slate-200 dark:border-[#1D2B43]/60 flex items-center justify-between text-[10px] text-slate-500 dark:text-slate-400 font-mono">
                <div className="flex-1 mr-2 bg-slate-200 dark:bg-[#15233E] rounded-full h-1 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      isCompleted ? 'bg-emerald-500' : 'bg-blue-600 dark:bg-[#2165FF]'
                    }`}
                    style={{
                      width: isCompleted ? '100%' : isRunning ? '65%' : '15%',
                    }}
                  />
                </div>
                <span>
                  {isCompleted
                    ? 'done'
                    : isPlanner
                    ? `${completedTasksCount}/${totalTasksCount || 1}`
                    : `${agent.tool_calls_count || 0} steps`}
                </span>
              </div>
            </button>

            {/* Subtle flow connector arrow between agents */}
            {index < agents.length - 1 && (
              <ArrowRight className="w-4 h-4 text-slate-400 dark:text-slate-600 flex-shrink-0" />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};
