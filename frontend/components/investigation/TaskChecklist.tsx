'use client';

import React from 'react';
import { TaskItem, FindingItem } from '@/types/investigation';
import { CheckCircle2, Clock, AlertCircle, ArrowRight, ShieldCheck, FileCode } from 'lucide-react';

interface TaskChecklistProps {
  tasks: TaskItem[];
  findings: FindingItem[];
  onSelectTask?: (taskId: string) => void;
}

export const TaskChecklist: React.FC<TaskChecklistProps> = ({
  tasks,
  findings,
  onSelectTask,
}) => {
  if (tasks.length === 0) {
    return (
      <div className="p-4 rounded-xl border border-dashed border-slate-200 dark:border-slate-800 text-center text-xs text-slate-500">
        No investigation tasks generated yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {tasks.map((task, idx) => {
        const taskFindings = findings.filter((f) => f.task_id === task.id);
        const isRunning = task.status === 'RUNNING';
        const isCompleted = task.status === 'COMPLETED';

        return (
          <div
            key={task.id}
            onClick={() => onSelectTask && onSelectTask(task.id)}
            className={`p-3.5 rounded-xl border transition-all ${
              isRunning
                ? 'bg-blue-50/50 dark:bg-blue-950/20 border-blue-400 dark:border-blue-600 shadow-sm'
                : isCompleted
                ? 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800'
                : 'bg-slate-50 dark:bg-slate-950/60 border-slate-200 dark:border-slate-800 opacity-80'
            }`}
          >
            {/* Header: Status Icon & Title */}
            <div className="flex items-start justify-between gap-3 mb-1.5">
              <div className="flex items-start gap-2.5">
                <div className="mt-0.5">
                  {isCompleted ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                  ) : isRunning ? (
                    <Clock className="w-4 h-4 text-blue-500 animate-spin" />
                  ) : (
                    <div className="w-4 h-4 rounded-full border-2 border-slate-300 dark:border-slate-600" />
                  )}
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                    <span>{task.title}</span>
                    <span className="text-[10px] text-slate-400 font-mono font-normal">
                      ({task.id})
                    </span>
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    {task.description}
                  </p>
                </div>
              </div>

              {/* Status Badge */}
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider shrink-0 ${
                  isCompleted
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                    : isRunning
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 animate-pulse'
                    : 'bg-slate-100 text-slate-500 dark:bg-slate-800'
                }`}
              >
                {task.status}
              </span>
            </div>

            {/* Criteria & Findings Count */}
            <div className="mt-2.5 pt-2 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
              <div className="flex items-center gap-3">
                {task.assigned_agent && (
                  <span className="font-mono text-slate-600 dark:text-slate-300">
                    Agent: {task.assigned_agent}
                  </span>
                )}
                {taskFindings.length > 0 && (
                  <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    {taskFindings.length} verified finding{taskFindings.length > 1 ? 's' : ''}
                  </span>
                )}
              </div>

              {task.dependencies && task.dependencies.length > 0 && (
                <span className="text-[10px] text-slate-400">
                  Depends on: {task.dependencies.join(', ')}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
