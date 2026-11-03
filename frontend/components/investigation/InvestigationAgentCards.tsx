'use client';

import React, { useState } from 'react';
import { Bot, Cpu, CheckCircle2, ChevronDown, ChevronUp } from 'lucide-react';
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
  const [expanded, setExpanded] = useState(false);

  if (agents.length === 0) {
    return (
      <div className="py-2.5 px-3 rounded-lg glass-panel-subtle border border-slate-200/70 dark:border-slate-800/70 flex items-center justify-center text-xs text-slate-500 font-mono">
        Agents will appear here as the planner spawns them...
      </div>
    );
  }

  const visibleAgents = expanded ? agents : agents.slice(0, 4);

  return (
    <div className="space-y-1.5 select-none">
      <div className="space-y-1">
        {visibleAgents.map((agent) => {
          const isSelected = agent.agent_id === selectedAgentId;
          const isPlanner = agent.agent_id === 'planner-main' || agent.role.toLowerCase().includes('planner');
          const isCompleted = agent.status === 'completed';
          const isRunning = agent.status === 'running';

          return (
            <button
              key={agent.agent_id}
              onClick={() => onSelectAgent(agent.agent_id)}
              className={`w-full px-3 py-1.5 rounded-lg border text-left transition-all flex items-center justify-between gap-3 ${
                isSelected
                  ? 'bg-indigo-50/90 dark:bg-indigo-950/50 border-indigo-500 dark:border-indigo-500 ring-1 ring-indigo-500 shadow-sm'
                  : 'glass-panel-subtle border-slate-200/60 dark:border-slate-800/60 hover:border-indigo-400/50 dark:hover:border-indigo-400/50 hover:bg-slate-100/60 dark:hover:bg-slate-800/40'
              }`}
            >
              {/* Left: Icon + Name & Role */}
              <div className="flex items-center gap-2.5 min-w-0">
                <div
                  className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 ${
                    isPlanner
                      ? 'bg-purple-100 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 border border-purple-200 dark:border-purple-800/40'
                      : 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/40'
                  }`}
                >
                  {isPlanner ? <Cpu className="w-3 h-3" /> : <Bot className="w-3 h-3" />}
                </div>
                <div className="min-w-0 flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-900 dark:text-white font-mono truncate max-w-[140px]">
                    {agent.agent_id}
                  </span>
                  <span className="text-[11px] text-slate-500 dark:text-slate-400 truncate hidden sm:inline max-w-[180px]">
                    {agent.role}
                  </span>
                </div>
              </div>

              {/* Right: Progress Track + Status Badge */}
              <div className="flex items-center gap-3 flex-shrink-0">
                {/* Compact Progress */}
                <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-500 dark:text-slate-400">
                  <div className="w-14 bg-slate-200 dark:bg-slate-800 rounded-full h-1 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-300 ${
                        isCompleted ? 'bg-emerald-500' : 'bg-indigo-600 dark:bg-indigo-400'
                      }`}
                      style={{
                        width: isCompleted ? '100%' : isRunning ? '65%' : '20%',
                      }}
                    />
                  </div>
                  <span className="min-w-[28px] text-right">
                    {isCompleted
                      ? 'done'
                      : isPlanner
                      ? `${completedTasksCount}/${totalTasksCount || 1}`
                      : `${agent.tool_calls_count || 0}s`}
                  </span>
                </div>

                {/* Status pill */}
                <span
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase tracking-wider ${
                    isCompleted
                      ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-800/50'
                      : isRunning
                      ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400 border border-blue-300 dark:border-blue-800/50 animate-pulse'
                      : agent.status === 'failed' || agent.status === 'timed_out'
                      ? 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-400 border border-red-300 dark:border-red-800/50'
                      : agent.status === 'blocked' || agent.status === 'skipped'
                      ? 'bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border border-amber-300 dark:border-amber-800/50'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700'
                  }`}
                >
                  {agent.status}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* View All / Collapse toggle button when agents > 4 */}
      {agents.length > 4 && (
        <div className="flex justify-end pt-0.5">
          <button
            onClick={() => setExpanded((prev) => !prev)}
            className="text-[11px] font-mono font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 dark:hover:text-indigo-300 flex items-center gap-1 transition-colors px-1 py-0.5"
          >
            {expanded ? (
              <>
                <span>Collapse to 4 agents</span>
                <ChevronUp className="w-3.5 h-3.5" />
              </>
            ) : (
              <>
                <span>View all {agents.length} agents</span>
                <ChevronDown className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
};
