'use client';

import React, { useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { streamRimComparison, ComparisonSide } from '@/services/rimComparisonApi';
import { Card, CardHeader } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Loader2, Send, ArrowUp, ArrowDown, Minus } from 'lucide-react';

interface ComparisonRun {
  question: string;
  withoutRim: ComparisonSide | null;
  withRim: ComparisonSide | null;
  metricsDiff: Record<string, any>;
  timestamp: number;
  loadingWithoutRim: boolean;
  loadingWithRim: boolean;
}

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

interface ComparisonResultProps {
  run: ComparisonRun;
  index: number;
}

function ComparisonResult({ run, index }: ComparisonResultProps) {
  const { withoutRim, withRim, metricsDiff, loadingWithoutRim, loadingWithRim } = run;

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
                <div className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed prose dark:prose-invert prose-sm max-w-none">
                  <ReactMarkdown
                    components={{
                      p: (props) => <p className="mb-3" {...props} />,
                      h1: (props) => <h1 className="text-lg font-bold mb-2" {...props} />,
                      h2: (props) => <h2 className="text-base font-bold mb-2" {...props} />,
                      h3: (props) => <h3 className="text-sm font-bold mb-2" {...props} />,
                      ul: (props) => <ul className="list-disc list-inside mb-3 space-y-1" {...props} />,
                      ol: (props) => <ol className="list-decimal list-inside mb-3 space-y-1" {...props} />,
                      li: (props) => <li className="mb-1" {...props} />,
                      code: (props: any) => props.inline
                        ? <code className="bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded text-xs font-mono" {...props} />
                        : <code className="bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded text-xs font-mono block mb-2 overflow-x-auto" {...props} />,
                      pre: (props) => <pre className="bg-slate-900 text-slate-100 p-3 rounded mb-3 overflow-x-auto text-xs" {...props} />,
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
                <div className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed prose dark:prose-invert prose-sm max-w-none">
                  <ReactMarkdown
                    components={{
                      p: (props) => <p className="mb-3" {...props} />,
                      h1: (props) => <h1 className="text-lg font-bold mb-2" {...props} />,
                      h2: (props) => <h2 className="text-base font-bold mb-2" {...props} />,
                      h3: (props) => <h3 className="text-sm font-bold mb-2" {...props} />,
                      ul: (props) => <ul className="list-disc list-inside mb-3 space-y-1" {...props} />,
                      ol: (props) => <ol className="list-decimal list-inside mb-3 space-y-1" {...props} />,
                      li: (props) => <li className="mb-1" {...props} />,
                      code: (props: any) => props.inline
                        ? <code className="bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded text-xs font-mono" {...props} />
                        : <code className="bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded text-xs font-mono block mb-2 overflow-x-auto" {...props} />,
                      pre: (props) => <pre className="bg-slate-900 text-slate-100 p-3 rounded mb-3 overflow-x-auto text-xs" {...props} />,
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
            </div>
          ) : null}
        </Card>
      </div>

      {/* Metrics Comparison */}
      {withoutRim && withRim && Object.keys(metricsDiff).length > 0 && (
        <Card>
          <CardHeader title="Metrics Comparison (WITH RIM vs WITHOUT RIM)" />
          <div className="p-6">
            <div className="space-y-3">
              {renderMetricDiff('Tool Calls', metricsDiff.tool_calls_diff, 'tool_calls_pct')}
              {renderMetricDiff('Files Retrieved', metricsDiff.files_diff)}
              {renderMetricDiff('Total Tokens', metricsDiff.tokens_diff, 'tokens_pct')}
              {renderMetricDiff('Latency (ms)', metricsDiff.latency_diff_ms?.toFixed(0))}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
