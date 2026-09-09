'use client';

import React, { useState, useCallback, useEffect } from 'react';
import { useParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { compareRimVsBaseline, RIMComparisonResponse } from '@/services/rimComparisonApi';
import { Card, CardHeader } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Loader2, Send } from 'lucide-react';

interface ComparisonRun {
  question: string;
  result: RIMComparisonResponse;
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
      // Create run with loading states
      const newRun: ComparisonRun = {
        question,
        result: null as any,
        timestamp: Date.now(),
        loadingWithoutRim: true,
        loadingWithRim: true,
      };
      setRuns([newRun, ...runs]);

      // Call comparison endpoint (runs both in parallel on backend)
      const result = await compareRimVsBaseline(repoName, question);

      // Update run with result and show WITHOUT RIM first
      setRuns((prevRuns) => {
        const updated = [...prevRuns];
        updated[0] = {
          ...updated[0],
          result,
          loadingWithoutRim: false,
        };
        return updated;
      });

      // Simulate delay before showing WITH RIM (visual flow)
      setTimeout(() => {
        setRuns((prevRuns) => {
          const updated = [...prevRuns];
          updated[0] = {
            ...updated[0],
            loadingWithRim: false,
          };
          return updated;
        });
      }, 500);

      setQuestion('');
    } catch (err: any) {
      setError(err.message || 'Comparison failed. Please try again.');
      console.error('Comparison error:', err);
      // Remove the failed run
      setRuns((prevRuns) => prevRuns.slice(1));
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

interface ComparisonResultProps {
  run: ComparisonRun;
  index: number;
}

function ComparisonResult({ run, index }: ComparisonResultProps) {
  const { result, loadingWithoutRim, loadingWithRim } = run;

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
          ) : (
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
                    {result.without_rim.answer}
                  </ReactMarkdown>
                </div>
              </div>

              {/* Metrics Summary */}
              <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
                <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-2 text-sm">Key Metrics</h4>
                <div className="space-y-1 text-xs text-slate-700 dark:text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Tool Calls:</span>
                    <span className="font-mono">{result.without_rim.retrieval_metrics.tool_call_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Files Retrieved:</span>
                    <span className="font-mono">{result.without_rim.retrieval_metrics.files_retrieved}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Total Latency:</span>
                    <span className="font-mono">{(result.without_rim.llm_efficiency_metrics.total_latency_ms ?? 0).toFixed(0)}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Input Tokens:</span>
                    <span className="font-mono">{result.without_rim.llm_efficiency_metrics.actual_prompt_tokens}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
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
          ) : (
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
                    {result.with_rim.answer}
                  </ReactMarkdown>
                </div>
              </div>

              {/* Metrics Summary */}
              <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
                <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-2 text-sm">Key Metrics</h4>
                <div className="space-y-1 text-xs text-slate-700 dark:text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Tool Calls:</span>
                    <span className="font-mono">{result.with_rim.retrieval_metrics.tool_call_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Files Retrieved:</span>
                    <span className="font-mono">{result.with_rim.retrieval_metrics.files_retrieved}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">RIM Entities:</span>
                    <span className="font-mono">{result.with_rim.retrieval_metrics.rim_entities_accessed_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Total Latency:</span>
                    <span className="font-mono">{(result.with_rim.llm_efficiency_metrics.total_latency_ms ?? 0).toFixed(0)}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 dark:text-slate-400">Input Tokens:</span>
                    <span className="font-mono">{result.with_rim.llm_efficiency_metrics.actual_prompt_tokens}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
