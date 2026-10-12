'use client';

import React, { useState } from 'react';
import {
  Clock,
  CheckCircle2,
  Wrench,
  Search,
  FileCode2,
  ExternalLink,
  ChevronDown,
  AlertCircle,
  Eye,
  Layers,
  Sparkles
} from 'lucide-react';
import { TimelineEvent, FindingItem } from '@/types/investigation';

interface TimelineProps {
  events: TimelineEvent[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  onOpenFinding?: (finding: FindingItem) => void;
}

export const InvestigationTimeline: React.FC<TimelineProps> = ({
  events,
  selectedAgentId,
  onSelectAgent,
  onOpenFinding,
}) => {
  const [expandedEvents, setExpandedEvents] = useState<Record<string, boolean>>({});

  const toggleExpand = (id: string) => {
    setExpandedEvents((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  if (events.length === 0) {
    return (
      <div className="p-8 text-center text-slate-400 dark:text-slate-500 font-mono text-xs flex flex-col items-center justify-center space-y-2">
        <Clock className="w-5 h-5 text-slate-400 dark:text-slate-600 animate-spin" />
        <span>Awaiting agent execution events...</span>
      </div>
    );
  }

  return (
    <div className="relative pl-6 space-y-4 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-px before:bg-slate-200 dark:before:bg-[#1D2B43]">
      {events.map((ev) => {
        const isToolCall = ev.type === 'tool-call';
        const isFinding = ev.type === 'finding-saved';
        const isExpanded = !!expandedEvents[ev.id];
        const isPlanner = ev.agent_id === 'planner-main' || ev.agent_id?.includes('planner');

        return (
          <div key={ev.id} className="relative group text-xs font-sans">
            {/* Timeline rail bullet point */}
            <div
              className={`absolute -left-6 top-1.5 w-3 h-3 rounded-full border-2 bg-white dark:bg-[#070D1D] transition-colors ${
                isFinding
                  ? 'border-emerald-500 bg-emerald-100 dark:bg-emerald-950'
                  : isToolCall
                  ? 'border-blue-500 bg-blue-100 dark:bg-blue-950'
                  : isPlanner
                  ? 'border-purple-500 bg-purple-100 dark:bg-purple-950'
                  : 'border-slate-400 dark:border-slate-500'
              }`}
            />

            {/* Event card */}
            <div className="space-y-1.5">
              {/* Event Header row */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-[10px] text-slate-400 dark:text-slate-500">
                  {ev.formatted_time}
                </span>

                {ev.agent_id && (
                  <button
                    onClick={() => onSelectAgent(ev.agent_id!)}
                    className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border transition-colors ${
                      isPlanner
                        ? 'bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800/40 hover:border-purple-400'
                        : 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/40 hover:border-emerald-400'
                    }`}
                  >
                    <span>{ev.agent_id}</span>
                  </button>
                )}

                <span className="text-slate-800 dark:text-slate-200 font-medium">
                  {ev.title}
                </span>

                {/* Status indicator badge */}
                {isToolCall && (
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border flex items-center gap-1 ${
                    ev.status === 'running'
                      ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800/40'
                      : ev.status === 'failed' || ev.success === false
                      ? 'bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-800/40'
                      : 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/40'
                  }`}>
                    {ev.status === 'running' ? (
                      <Clock className="w-2.5 h-2.5 animate-spin" />
                    ) : ev.status === 'failed' || ev.success === false ? (
                      <AlertCircle className="w-2.5 h-2.5" />
                    ) : (
                      <CheckCircle2 className="w-2.5 h-2.5" />
                    )}
                    <span>{ev.status === 'running' ? 'Running' : (ev.status === 'failed' || ev.success === false) ? 'Failed' : 'Completed'}</span>
                  </span>
                )}

                {ev.duration_s !== undefined && (
                  <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500 ml-auto flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-emerald-500 dark:text-emerald-400" />
                    {ev.duration_s}s
                  </span>
                )}
              </div>

              {/* Tool call box or Tool response box (expandable code / JSON / query viewer) */}
              {(isToolCall || ev.type === 'tool-response') && (
                <div className="rounded-xl bg-white dark:bg-[#0B1426] border border-slate-200 dark:border-[#1D2B43] overflow-hidden text-xs font-mono shadow-sm">
                  <div
                    onClick={() => toggleExpand(ev.id)}
                    className="px-3 py-2 bg-slate-50 dark:bg-[#0D162A] flex items-center justify-between cursor-pointer hover:bg-slate-100 dark:hover:bg-[#111C31] transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500 dark:text-slate-400 text-[11px]">
                        Tool Invocation
                      </span>
                      <span className="text-blue-600 dark:text-blue-400 font-semibold">{ev.tool_name}</span>
                      {ev.result_summary && !isExpanded && (
                        <span className="text-slate-400 dark:text-slate-500 text-[10px] font-normal truncate max-w-[200px]">
                          ({typeof ev.result_summary === 'string' ? ev.result_summary : Array.isArray(ev.result_summary) ? `${ev.result_summary.length} items` : 'Object'})
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <ChevronDown
                        className={`w-3.5 h-3.5 text-slate-400 transition-transform ${
                          isExpanded ? 'transform rotate-180' : ''
                        }`}
                      />
                    </div>
                  </div>

                  {/* Arguments and output preview */}
                  {isExpanded && (
                    <div className="p-3 space-y-2.5 border-t border-slate-200 dark:border-[#1D2B43]/80 bg-slate-50 dark:bg-[#070D1D] text-[11px]">
                      {/* Tool Call Parameters: Show clean file name, start/end lines, query */}
                      {ev.arguments && Object.keys(ev.arguments).length > 0 && (
                        <div>
                          <div className="text-[10px] text-slate-500 uppercase font-bold mb-1.5 flex items-center justify-between">
                            <span>Requested Parameters:</span>
                            {ev.arguments.path || ev.arguments.file || ev.arguments.file_path ? (
                              <span className="font-mono text-blue-600 dark:text-blue-400 normal-case">
                                {ev.arguments.path || ev.arguments.file || ev.arguments.file_path}
                              </span>
                            ) : null}
                          </div>
                          <div className="p-2.5 rounded-lg bg-white dark:bg-[#091124] border border-slate-200 dark:border-[#1D2B43]/60 space-y-1 text-slate-700 dark:text-slate-300 font-mono text-[11px]">
                            {(ev.arguments.path || ev.arguments.file || ev.arguments.file_path) && (
                              <div className="flex items-center gap-2">
                                <span className="text-slate-400 text-[10px] uppercase font-sans">File Name:</span>
                                <span className="text-blue-600 dark:text-blue-400 font-semibold">{ev.arguments.path || ev.arguments.file || ev.arguments.file_path}</span>
                              </div>
                            )}
                            {ev.arguments.start_line !== undefined && (
                              <div className="flex items-center gap-2">
                                <span className="text-slate-400 text-[10px] uppercase font-sans">Start Line:</span>
                                <span className="font-semibold">{ev.arguments.start_line}</span>
                              </div>
                            )}
                            {ev.arguments.end_line !== undefined && ev.arguments.end_line !== null && (
                              <div className="flex items-center gap-2">
                                <span className="text-slate-400 text-[10px] uppercase font-sans">End Line:</span>
                                <span className="font-semibold">{ev.arguments.end_line}</span>
                              </div>
                            )}
                            {ev.arguments.query && (
                              <div className="flex items-center gap-2">
                                <span className="text-slate-400 text-[10px] uppercase font-sans">Query:</span>
                                <span className="font-semibold text-emerald-600 dark:text-emerald-400">"{ev.arguments.query}"</span>
                              </div>
                            )}
                            {ev.arguments.entity_name && (
                              <div className="flex items-center gap-2">
                                <span className="text-slate-400 text-[10px] uppercase font-sans">Entity:</span>
                                <span className="font-semibold text-purple-600 dark:text-purple-400">{ev.arguments.entity_name}</span>
                              </div>
                            )}
                            {/* Render any other extra arguments cleanly if not path/lines/query */}
                            {Object.entries(ev.arguments)
                              .filter(([k]) => !['path', 'file', 'file_path', 'start_line', 'end_line', 'query', 'entity_name'].includes(k))
                              .map(([k, v]) => (
                                <div key={k} className="flex items-center gap-2 text-[10px]">
                                  <span className="text-slate-400 uppercase font-sans">{k}:</span>
                                  <span>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                                </div>
                              ))}
                          </div>
                        </div>
                      )}

                      {/* Explicit Error Display */}
                      {ev.error && (
                        <div>
                          <div className="text-[10px] text-rose-500 uppercase font-bold mb-1 flex items-center gap-1">
                            <AlertCircle className="w-3 h-3" />
                            <span>Tool Error:</span>
                          </div>
                          <div className="p-2.5 rounded-lg bg-rose-50/60 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 text-rose-700 dark:text-rose-300 font-mono text-[11px] whitespace-pre-wrap">
                            {typeof ev.error === 'object' ? (ev.error.message || JSON.stringify(ev.error, null, 2)) : String(ev.error)}
                          </div>
                        </div>
                      )}

                      {/* Code excerpt if tool was read_file */}
                      {ev.code_excerpt && (
                        <div>
                          <div className="text-[10px] text-slate-500 uppercase font-bold mb-1 flex items-center justify-between">
                            <span>
                              File Excerpt
                              {(ev.file_path || ev.arguments?.path || ev.arguments?.file || ev.arguments?.file_path)
                                ? ` (${ev.file_path || ev.arguments?.path || ev.arguments?.file || ev.arguments?.file_path})`
                                : ''}:
                            </span>
                            {(ev.line_start || ev.arguments?.start_line) && (
                              <span>Lines {ev.line_start || ev.arguments?.start_line}-{ev.line_end || ev.arguments?.end_line}</span>
                            )}
                          </div>
                          <pre className="p-2.5 rounded-lg bg-white dark:bg-[#091124] border border-slate-200 dark:border-[#1D2B43]/60 text-emerald-700 dark:text-emerald-300 overflow-x-auto text-[11px] leading-relaxed font-mono max-h-72">
                            {ev.code_excerpt}
                          </pre>
                        </div>
                      )}

                      {/* Simplified User-Friendly Output (Clean response instead of raw JSON dump) */}
                      {ev.result_summary && !ev.code_excerpt && (
                        <div>
                          <div className="text-[10px] text-slate-500 uppercase font-bold mb-1">
                            Response:
                          </div>
                          <div className="p-2.5 rounded-lg bg-white dark:bg-[#091124] border border-slate-200 dark:border-[#1D2B43]/60 text-slate-800 dark:text-slate-300 text-[11px] leading-relaxed max-h-72 overflow-y-auto">
                            {(() => {
                              const res = ev.result_summary;
                              // If string with code or message
                              if (typeof res === 'string') {
                                return <pre className="font-mono whitespace-pre-wrap">{res}</pre>;
                              }
                              // If search matches array
                              if (Array.isArray(res)) {
                                if (res.length === 0) {
                                  return <div className="text-slate-400 italic">No matches found.</div>;
                                }
                                return (
                                  <div className="space-y-1.5">
                                    <div className="text-xs font-semibold text-slate-600 dark:text-slate-400">
                                      Found {res.length} matches:
                                    </div>
                                    {res.slice(0, 15).map((match: any, idx: number) => {
                                      const p = match.path || match.file || match.file_path || '';
                                      const l = match.line || match.start_line;
                                      const snip = match.snippet || match.text || match.summary || match.name || '';
                                      return (
                                        <div key={idx} className="p-1.5 rounded bg-slate-50 dark:bg-[#070D1D] border border-slate-200/60 dark:border-[#1D2B43]/40 flex flex-col gap-0.5 font-mono text-[10px]">
                                          <div className="flex items-center justify-between text-blue-600 dark:text-blue-400 font-semibold">
                                            <span>{p}</span>
                                            {l !== undefined && <span>Line {l}</span>}
                                          </div>
                                          {snip && <div className="text-slate-600 dark:text-slate-300 truncate">{snip}</div>}
                                        </div>
                                      );
                                    })}
                                    {res.length > 15 && (
                                      <div className="text-[10px] text-slate-400 italic">
                                        + {res.length - 15} more matches
                                      </div>
                                    )}
                                  </div>
                                );
                              }
                              // If object with content / outline / relationships
                              if (typeof res === 'object' && res !== null) {
                                if (res.content) {
                                  return <pre className="font-mono whitespace-pre-wrap">{res.content}</pre>;
                                }
                                // Handle get_code_relationships results:
                                if (res.found === false) {
                                  return (
                                    <div className="space-y-1.5 p-2 rounded bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-900/40 text-amber-800 dark:text-amber-300">
                                      <div className="font-semibold flex items-center gap-1.5">
                                        <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                                        <span>
                                          {res.resolution === 'ENTITY_NOT_FOUND'
                                            ? 'Entity not found in repository index'
                                            : res.resolution === 'NO_STATIC_EDGE_FOUND'
                                            ? 'No static graph relationships found'
                                            : 'No relationships resolved'}
                                        </span>
                                      </div>
                                      <div className="text-[10px] leading-relaxed text-slate-600 dark:text-slate-300">
                                        {res.message}
                                      </div>
                                      {res.fallback && (
                                        <div className="text-[10px] text-slate-500 dark:text-slate-400 font-mono">
                                          Suggested alternative: use <span className="font-semibold text-blue-500">{res.fallback.tool}</span> for "{res.fallback.query}"
                                        </div>
                                      )}
                                    </div>
                                  );
                                }
                                if (res.found === true && Array.isArray(res.related)) {
                                  return (
                                    <div className="space-y-1.5">
                                      <div className="font-semibold text-slate-700 dark:text-slate-300 flex items-center justify-between">
                                        <span>Resolved {res.related.length} Relationships:</span>
                                        {res.direction && <span className="text-[10px] font-mono text-purple-500 uppercase">{res.direction}</span>}
                                      </div>
                                      {res.message && (
                                        <div className="text-[10px] text-slate-500 dark:text-slate-400 mb-1">
                                          {res.message}
                                        </div>
                                      )}
                                      <div className="space-y-1 font-mono text-[10px]">
                                        {res.related.map((rel: any, idx: number) => (
                                          <div key={idx} className="p-1.5 rounded bg-slate-50 dark:bg-[#070D1D] border border-slate-200/60 dark:border-slate-800 flex items-center justify-between">
                                            <span className="font-semibold text-purple-600 dark:text-purple-400">{rel.name}</span>
                                            <span className="text-slate-400">{rel.relationship_role || rel.entity_type}</span>
                                            {rel.location && <span className="text-blue-500 truncate max-w-[150px]">{rel.location}</span>}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  );
                                }
                                if (res.symbols && Array.isArray(res.symbols)) {
                                  return (
                                    <div className="space-y-1">
                                      <div className="font-semibold text-slate-600 dark:text-slate-400 mb-1">
                                        Outline Symbols ({res.symbols.length}):
                                      </div>
                                      <div className="flex flex-wrap gap-1 font-mono text-[10px]">
                                        {res.symbols.map((s: any, idx: number) => (
                                          <span key={idx} className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-[#070D1D] border border-slate-200 dark:border-slate-800 text-purple-600 dark:text-purple-400">
                                            {s.name || s.symbol || String(s)}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  );
                                }
                                if (res.relationships && Array.isArray(res.relationships)) {
                                  return (
                                    <div className="space-y-1">
                                      <div className="font-semibold text-slate-600 dark:text-slate-400 mb-1">
                                        Relationships ({res.relationships.length}):
                                      </div>
                                      <div className="space-y-1 font-mono text-[10px]">
                                        {res.relationships.slice(0, 10).map((r: any, idx: number) => (
                                          <div key={idx} className="p-1 rounded bg-slate-50 dark:bg-[#070D1D] border border-slate-200/60 dark:border-slate-800">
                                            {r.source || r.from} &rarr; <span className="text-blue-500">{r.type}</span> &rarr; {r.target || r.to}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  );
                                }
                                if (res.message) {
                                  return <div>{res.message}</div>;
                                }
                                if (res.error) {
                                  return <div className="text-rose-500 font-semibold">{typeof res.error === 'object' ? (res.error.message || JSON.stringify(res.error)) : res.error}</div>;
                                }
                                // Fallback for simple message / status
                                return (
                                  <pre className="font-mono text-[10px] whitespace-pre-wrap">
                                    {JSON.stringify(res, null, 2)}
                                  </pre>
                                );
                              }
                              return String(res);
                            })()}
                          </div>
                        </div>
                      )}

                      {!ev.result_summary && !ev.arguments && !ev.code_excerpt && !ev.error && (
                        <div className="text-slate-400 dark:text-slate-500 italic text-[10px]">
                          {ev.status === 'running' ? 'Executing tool...' : 'No additional payload recorded.'}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Finding Box if finding-saved */}
              {isFinding && ev.finding && (
                <div className="p-2.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/40 text-xs space-y-1.5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-emerald-800 dark:text-emerald-300 flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                      {ev.finding.summary}
                    </span>
                    {onOpenFinding && (
                      <button
                        onClick={() => onOpenFinding(ev.finding!)}
                        className="text-[10px] text-emerald-600 dark:text-emerald-400 hover:underline flex items-center gap-1 font-mono"
                      >
                        Inspect Evidence
                        <ExternalLink className="w-2.5 h-2.5" />
                      </button>
                    )}
                  </div>
                  <div className="text-[11px] font-mono text-slate-500 dark:text-slate-400 flex items-center gap-2">
                    <span className="text-blue-600 dark:text-blue-400">{ev.finding.file_path}</span>
                    {ev.finding.line_start && (
                      <span>L{ev.finding.line_start}-{ev.finding.line_end}</span>
                    )}
                  </div>
                </div>
              )}
              {/* Memory Update Box if worker returns findings/memory to orchestrator */}
              {ev.type === 'memory-update' && (
                <div className="p-3 rounded-xl bg-purple-50 dark:bg-purple-950/20 border border-purple-200 dark:border-purple-800/40 text-xs space-y-2 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-purple-900 dark:text-purple-300 flex items-center gap-1.5">
                      <Layers className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                      {ev.title}
                    </span>
                    <button
                      onClick={() => toggleExpand(ev.id)}
                      className="text-[10px] text-purple-600 dark:text-purple-400 hover:underline font-mono"
                    >
                      {isExpanded ? 'Hide Details' : 'View Memory'}
                    </button>
                  </div>
                  {isExpanded && ev.result_summary && (
                    <div className="pt-2 border-t border-purple-200/60 dark:border-purple-800/40 space-y-2 font-mono text-[10px]">
                      {ev.result_summary.findings_returned?.length > 0 && (
                        <div>
                          <span className="text-slate-500 font-bold uppercase block mb-1">Returned Findings:</span>
                          <div className="space-y-1">
                            {ev.result_summary.findings_returned.map((f: any, fIdx: number) => (
                              <div key={fIdx} className="p-1.5 rounded bg-white dark:bg-[#070D1D] border border-purple-100 dark:border-purple-900/40 text-slate-700 dark:text-slate-300">
                                <span className="font-semibold text-blue-600 dark:text-blue-400">{f.file_path}</span>: {f.summary}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {ev.result_summary.files_read?.length > 0 && (
                        <div>
                          <span className="text-slate-500 font-bold uppercase block mb-1">Inspected Files:</span>
                          <div className="flex flex-wrap gap-1">
                            {ev.result_summary.files_read.map((fileStr: string, idx: number) => (
                              <span key={idx} className="px-1.5 py-0.5 rounded bg-white dark:bg-[#070D1D] border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300">
                                {fileStr}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {ev.result_summary.coverage_gaps?.length > 0 && (
                        <div>
                          <span className="text-amber-600 dark:text-amber-400 font-bold uppercase block mb-1">Unresolved Gaps:</span>
                          <ul className="list-disc list-inside text-amber-700 dark:text-amber-300 space-y-0.5">
                            {ev.result_summary.coverage_gaps.map((gap: string, gIdx: number) => (
                              <li key={gIdx}>{gap}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
