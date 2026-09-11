'use client';

import React, { useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { streamRimComparison, ComparisonSide } from '@/services/rimComparisonApi';
import { Card, CardHeader } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Loader2, Send, ArrowUp, ArrowDown, Minus, ChevronDown } from 'lucide-react';

interface ComparisonRun {
  question: string;
  withoutRim: ComparisonSide | null;
  withRim: ComparisonSide | null;
  metricsDiff: Record<string, any>;
  timestamp: number;
  loadingWithoutRim: boolean;
  loadingWithRim: boolean;
}

const renderMetricDiff = (label: string, value: any, pctKey?: string) => {
  const pct = pctKey ? value[pctKey] : null;
  let icon = null;
  let color = 'text-slate-600 dark:text-slate-400';

  if (typeof value === 'number') {
    if (value > 0) {
      icon = <ArrowUp className="w-4 h-4 text-red-500" />;
      color = 'text-red-600 dark:text-red-400';
    } else if (value < 0) {
      icon = <ArrowDown className="w-4 h-4 text-green-500" />;
      color = 'text-green-600 dark:text-green-400';
    } else {
      icon = <Minus className="w-4 h-4 text-slate-400" />;
    }
  }

  return (
    <div key={label} className="flex items-center justify-between text-xs">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <div className="flex items-center gap-1">
        {icon}
        <span className={`font-mono ${color}`}>
          {typeof value === 'number' ? (value > 0 ? '+' : '') + value : value}
          {pct !== null && pct !== undefined ? ` (${pct > 0 ? '+' : ''}${pct}%)` : ''}
        </span>
      </div>
    </div>
  );
};

export default function RIMComparisonPage() {
  const params = useParams();
  const repoName = params?.repoName as string;

  const [question, setQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [runs, setRuns] = useState<ComparisonRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleCompare = useCallback(async () => {
    if (!question.trim()) {
      setError('Please enter a question');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const newRun: ComparisonRun = {
        question,
        withoutRim: null,
        withRim: null,
        metricsDiff: {},
        timestamp: Date.now(),
        loadingWithoutRim: true,
        loadingWithRim: true,
      };
      setRuns([newRun, ...runs]);

      await streamRimComparison(
        repoName,
        question,
        (withoutRimResult: ComparisonSide) => {
          setRuns((prevRuns) => {
            const updated = [...prevRuns];
            updated[0] = {
              ...updated[0],
              withoutRim: withoutRimResult,
              loadingWithoutRim: false,
            };
            return updated;
          });
        },
        (withRimResult: ComparisonSide, metricsDiff: Record<string, any>) => {
          setRuns((prevRuns) => {
            const updated = [...prevRuns];
            updated[0] = {
              ...updated[0],
              withRim: withRimResult,
              metricsDiff,
              loadingWithRim: false,
            };
            return updated;
          });
        },
        (errorMsg: string) => {
          setError(errorMsg);
          setRuns((prevRuns) => prevRuns.slice(1));
        }
      );

      setQuestion('');
    } catch (err: any) {
      setError(err.message || 'Comparison failed. Please try again.');
      console.error('Comparison error:', err);
    } finally {
      setIsLoading(false);
    }
  }, [question, repoName, runs]);

  const handleNewComparison = useCallback(() => {
    setQuestion('');
    setError(null);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      handleCompare();
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-white dark:bg-slate-950 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-slate-900 dark:text-slate-100 mb-2">RIM Comparison</h1>
          <p className="text-slate-600 dark:text-slate-400">
            Compare repository-aware answers with and without Repository Intelligence Model (RIM).
          </p>
        </div>

        {/* Query Input */}
        <Card className="mb-8">
          <div className="p-6">
            <label className="block text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">
              Research Question
            </label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about this repository..."
              disabled={isLoading}
              className="w-full px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4 disabled:opacity-50"
              rows={3}
            />

            <div className="flex items-center justify-between">
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Tip: Ctrl+Enter to submit
              </div>
              <Button
                onClick={handleCompare}
                disabled={isLoading || !question.trim()}
                className="flex items-center gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Comparing...
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    Compare
                  </>
                )}
              </Button>
            </div>
          </div>
        </Card>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-50 dark:bg-red-950 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-800">
            {error}
          </div>
        )}

        {/* Results */}
        {runs.map((run, idx) => (
          <ComparisonResult
            key={run.timestamp}
            run={run}
            index={idx}
          />
        ))}

        {/* New Comparison Button */}
        {runs.length > 0 && (
          <div className="mt-8 text-center">
            <Button onClick={handleNewComparison} variant="secondary">
              + New Comparison
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

interface MetricComparisonRowProps {
  label: string;
  withoutValue: any;
  withValue: any;
  diff: any;
  pct?: number;
  lowerIsBetter?: boolean;
}

const MetricComparisonRow = ({
  label,
  withoutValue,
  withValue,
  diff,
  pct,
  lowerIsBetter = false,
}: MetricComparisonRowProps) => {
  let winner = '';
  let winnerColor = '';

  if (typeof diff === 'number' && diff !== 0) {
    if (lowerIsBetter) {
      winner = diff < 0 ? 'WITH RIM Wins ✓' : 'WITHOUT RIM Better';
      winnerColor = diff < 0 ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400';
    } else {
      winner = diff > 0 ? 'WITH RIM Wins ✓' : 'WITHOUT RIM Better';
      winnerColor = diff > 0 ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400';
    }
  }

  return (
    <tr className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800">
      <td className="py-2 px-3 font-semibold text-slate-900 dark:text-slate-100">{label}</td>
      <td className="py-2 px-3 text-right text-slate-600 dark:text-slate-400 font-mono">{withoutValue}</td>
      <td className="py-2 px-3 text-right text-slate-600 dark:text-slate-400 font-mono">{withValue}</td>
      <td className="py-2 px-3 text-right">
        <div className="flex flex-col items-end gap-0.5">
          <span className="font-mono text-slate-600 dark:text-slate-400">
            {typeof diff === 'string' ? diff : (diff > 0 ? '+' : '') + diff}
            {pct !== null && pct !== undefined ? ` (${pct > 0 ? '+' : ''}${pct}%)` : ''}
          </span>
          {winner && <span className={`text-xs font-semibold ${winnerColor}`}>{winner}</span>}
        </div>
      </td>
    </tr>
  );
};

interface ComparisonResultProps {
  run: ComparisonRun;
  index: number;
}

function ComparisonResult({ run, index }: ComparisonResultProps) {
  const { withoutRim, withRim, metricsDiff, loadingWithoutRim, loadingWithRim } = run;
  const [expandWithoutRimTools, setExpandWithoutRimTools] = useState(false);
  const [expandWithRimTools, setExpandWithRimTools] = useState(false);

  return (
    <div className="mb-12">
      {/* Test Header */}
      <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">
        Test {index + 1}: {run.question}
      </h2>

      {/* Two Panels */}
      <div className="grid grid-cols-2 gap-6 mb-8">
        {/* WITHOUT RIM Panel */}
        <Card>
          <CardHeader title="WITHOUT RIM" subtitle="Standard Retrieval" />
          {loadingWithoutRim ? (
            <div className="p-12">
              <div className="flex flex-col items-center justify-center">
                <Loader2 className="w-12 h-12 animate-spin text-blue-600 dark:text-blue-400 mb-4" />
                <p className="text-slate-600 dark:text-slate-400">Processing...</p>
              </div>
            </div>
          ) : withoutRim ? (
            <div className="p-6 space-y-4">
              <div>
                <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-2">Answer</h4>
                <div className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed">
                  <ReactMarkdown
                    components={{
                      p: (props) => <p className="mb-3" {...props} />,
                      h1: (props) => <h1 className="text-lg font-bold mb-2" {...props} />,
                      h2: (props) => <h2 className="text-base font-bold mb-2" {...props} />,
                      h3: (props) => <h3 className="text-sm font-bold mb-2" {...props} />,
                      ul: (props) => <ul className="list-disc list-outside mb-3 space-y-1 ml-6" {...props} />,
                      ol: (props) => <ol className="list-decimal list-outside mb-3 space-y-1 ml-6" {...props} />,
                      li: (props) => <li className="mb-1" {...props} />,
                      code: (props: any) => (
                        <code className="!inline bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded text-xs font-mono" {...props} />
                      ),
                      pre: (props) => (
                        <pre className="bg-slate-900 text-slate-100 p-3 rounded mb-3 overflow-x-auto text-xs">
                          {props.children}
                        </pre>
                      ),
                      blockquote: (props) => <blockquote className="border-l-4 border-slate-300 dark:border-slate-600 pl-3 italic text-slate-600 dark:text-slate-400 mb-3" {...props} />,
                      a: (props) => <a className="text-blue-600 dark:text-blue-400 underline" {...props} />,
                    }}
                  >
                    {withoutRim.answer}
                  </ReactMarkdown>
                </div>
              </div>

              {/* Metrics */}
              <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
                <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-3 text-sm">Metrics</h4>
                <div className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Tool Calls:</span>
                    <span className="font-mono">{withoutRim.retrieval_metrics.tool_call_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Files Retrieved:</span>
                    <span className="font-mono">{withoutRim.retrieval_metrics.files_retrieved}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Input Tokens:</span>
                    <span className="font-mono">{withoutRim.llm_efficiency_metrics.actual_prompt_tokens}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Total Latency:</span>
                    <span className="font-mono">{(withoutRim.llm_efficiency_metrics.total_latency_ms ?? 0).toFixed(0)}ms</span>
                  </div>
                </div>
              </div>

              {/* Tool Calls */}
              {withoutRim.tool_call_transcript && withoutRim.tool_call_transcript.length > 0 && (
                <div>
                  <button
                    onClick={() => setExpandWithoutRimTools(!expandWithoutRimTools)}
                    className="flex items-center gap-2 font-semibold text-slate-900 dark:text-slate-100 text-sm hover:opacity-75 transition-opacity mb-2"
                  >
                    <ChevronDown
                      className={`w-4 h-4 transition-transform ${expandWithoutRimTools ? 'rotate-180' : ''}`}
                    />
                    Tool Calls ({withoutRim.tool_call_transcript.length})
                  </button>
                  {expandWithoutRimTools && (
                    <div className="space-y-2 text-xs">
                      {withoutRim.tool_call_transcript.map((call, idx) => (
                        <div key={idx} className="bg-slate-100 dark:bg-slate-700/50 rounded p-3 border border-slate-200 dark:border-slate-600">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-semibold text-slate-900 dark:text-slate-100">
                              [{call.turn}] {call.tool_name}
                            </span>
                          </div>
                          {call.arguments && Object.keys(call.arguments).length > 0 && (
                            <div className="bg-slate-900 dark:bg-slate-900 text-slate-100 p-2 rounded text-xs font-mono mb-2 overflow-x-auto max-h-24 overflow-y-auto">
                              <pre>{JSON.stringify(call.arguments, null, 2)}</pre>
                            </div>
                          )}
                          {call.observation_summary && (
                            <div className="text-slate-700 dark:text-slate-300 italic">
                              Result: {call.observation_summary.substring(0, 200)}
                              {call.observation_summary.length > 200 ? '...' : ''}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </Card>

        {/* WITH RIM Panel */}
        <Card>
          <CardHeader title="WITH RIM" subtitle="RIM-Enhanced Retrieval" />
          {loadingWithRim ? (
            <div className="p-12">
              <div className="flex flex-col items-center justify-center">
                <Loader2 className="w-12 h-12 animate-spin text-blue-600 dark:text-blue-400 mb-4" />
                <p className="text-slate-600 dark:text-slate-400">Processing...</p>
              </div>
            </div>
          ) : withRim ? (
            <div className="p-6 space-y-4">
              <div>
                <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-2">Answer</h4>
                <div className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed">
                  <ReactMarkdown
                    components={{
                      p: (props) => <p className="mb-3" {...props} />,
                      h1: (props) => <h1 className="text-lg font-bold mb-2" {...props} />,
                      h2: (props) => <h2 className="text-base font-bold mb-2" {...props} />,
                      h3: (props) => <h3 className="text-sm font-bold mb-2" {...props} />,
                      ul: (props) => <ul className="list-disc list-outside mb-3 space-y-1 ml-6" {...props} />,
                      ol: (props) => <ol className="list-decimal list-outside mb-3 space-y-1 ml-6" {...props} />,
                      li: (props) => <li className="mb-1" {...props} />,
                      code: (props: any) => (
                        <code className="!inline bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded text-xs font-mono" {...props} />
                      ),
                      pre: (props) => (
                        <pre className="bg-slate-900 text-slate-100 p-3 rounded mb-3 overflow-x-auto text-xs">
                          {props.children}
                        </pre>
                      ),
                      blockquote: (props) => <blockquote className="border-l-4 border-slate-300 dark:border-slate-600 pl-3 italic text-slate-600 dark:text-slate-400 mb-3" {...props} />,
                      a: (props) => <a className="text-blue-600 dark:text-blue-400 underline" {...props} />,
                    }}
                  >
                    {withRim.answer}
                  </ReactMarkdown>
                </div>
              </div>

              {/* Metrics with Comparison */}
              <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
                <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-3 text-sm">Metrics</h4>
                <div className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Tool Calls:</span>
                    <span className="font-mono">{withRim.retrieval_metrics.tool_call_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Files Retrieved:</span>
                    <span className="font-mono">{withRim.retrieval_metrics.files_retrieved}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">RIM Entities:</span>
                    <span className="font-mono">{withRim.retrieval_metrics.rim_entities_accessed_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Input Tokens:</span>
                    <span className="font-mono">{withRim.llm_efficiency_metrics.actual_prompt_tokens}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Total Latency:</span>
                    <span className="font-mono">{(withRim.llm_efficiency_metrics.total_latency_ms ?? 0).toFixed(0)}ms</span>
                  </div>
                </div>
              </div>

              {/* Tool Calls */}
              {withRim.tool_call_transcript && withRim.tool_call_transcript.length > 0 && (
                <div>
                  <button
                    onClick={() => setExpandWithRimTools(!expandWithRimTools)}
                    className="flex items-center gap-2 font-semibold text-slate-900 dark:text-slate-100 text-sm hover:opacity-75 transition-opacity mb-2"
                  >
                    <ChevronDown
                      className={`w-4 h-4 transition-transform ${expandWithRimTools ? 'rotate-180' : ''}`}
                    />
                    Tool Calls ({withRim.tool_call_transcript.length})
                  </button>
                  {expandWithRimTools && (
                    <div className="space-y-2 text-xs">
                      {withRim.tool_call_transcript.map((call, idx) => (
                        <div key={idx} className="bg-slate-100 dark:bg-slate-700/50 rounded p-3 border border-slate-200 dark:border-slate-600">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-semibold text-slate-900 dark:text-slate-100">
                              [{call.turn}] {call.tool_name}
                            </span>
                          </div>
                          {call.arguments && Object.keys(call.arguments).length > 0 && (
                            <div className="bg-slate-900 dark:bg-slate-900 text-slate-100 p-2 rounded text-xs font-mono mb-2 overflow-x-auto max-h-24 overflow-y-auto">
                              <pre>{JSON.stringify(call.arguments, null, 2)}</pre>
                            </div>
                          )}
                          {call.observation_summary && (
                            <div className="text-slate-700 dark:text-slate-300 italic">
                              Result: {call.observation_summary.substring(0, 200)}
                              {call.observation_summary.length > 200 ? '...' : ''}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </Card>
      </div>

      {/* Metrics Comparison */}
      {withoutRim && withRim && (
        <Card>
          <CardHeader title="Metrics Comparison" />
          <div className="p-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700">
                  <th className="text-left py-2 px-3 font-semibold text-slate-700 dark:text-slate-300">Metric</th>
                  <th className="text-right py-2 px-3 font-semibold text-slate-700 dark:text-slate-300">WITHOUT RIM</th>
                  <th className="text-right py-2 px-3 font-semibold text-slate-700 dark:text-slate-300">WITH RIM</th>
                  <th className="text-right py-2 px-3 font-semibold text-slate-700 dark:text-slate-300">Difference / Winner</th>
                </tr>
              </thead>
              <tbody>
                <MetricComparisonRow
                  label="Tool Calls"
                  withoutValue={withoutRim.retrieval_metrics.tool_call_count}
                  withValue={withRim.retrieval_metrics.tool_call_count}
                  diff={metricsDiff.tool_calls_diff}
                  pct={metricsDiff.tool_calls_pct}
                  lowerIsBetter={true}
                />
                <MetricComparisonRow
                  label="Files Retrieved"
                  withoutValue={withoutRim.retrieval_metrics.files_retrieved}
                  withValue={withRim.retrieval_metrics.files_retrieved}
                  diff={metricsDiff.files_diff}
                  lowerIsBetter={false}
                />
                <MetricComparisonRow
                  label="Input Tokens"
                  withoutValue={withoutRim.llm_efficiency_metrics.actual_prompt_tokens}
                  withValue={withRim.llm_efficiency_metrics.actual_prompt_tokens}
                  diff={metricsDiff.tokens_diff}
                  pct={metricsDiff.tokens_pct}
                  lowerIsBetter={true}
                />
                <MetricComparisonRow
                  label="Total Latency (ms)"
                  withoutValue={(withoutRim.llm_efficiency_metrics.total_latency_ms ?? 0).toFixed(0)}
                  withValue={(withRim.llm_efficiency_metrics.total_latency_ms ?? 0).toFixed(0)}
                  diff={metricsDiff.latency_diff_ms?.toFixed(0)}
                  lowerIsBetter={true}
                />
                <MetricComparisonRow
                  label="RIM Entities Accessed"
                  withoutValue={0}
                  withValue={withRim.retrieval_metrics.rim_entities_accessed_count}
                  diff="-"
                  lowerIsBetter={false}
                />
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
