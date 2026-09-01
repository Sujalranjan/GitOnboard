'use client';

import React, { useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { compareRimVsBaseline, RIMComparisonResponse } from '@/services/rimComparisonApi';
import { Card, CardHeader } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { Collapsible } from '@/components/common/Collapsible';
import { ArrowRight, Loader2 } from 'lucide-react';

interface ComparisonRun {
  question: string;
  result: RIMComparisonResponse;
  timestamp: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  userEvaluation?: any;
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
      const result = await compareRimVsBaseline(repoName, question);
      const newRun: ComparisonRun = {
        question,
        result,
        timestamp: Date.now(),
        userEvaluation: {}
      };
      setRuns([newRun, ...runs]);
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

          {/* Repository Info */}
          <div className="mt-4 grid grid-cols-4 gap-4 text-sm">
            <div>
              <span className="font-semibold text-slate-700 dark:text-slate-300">Repository</span>
              <p className="text-slate-600 dark:text-slate-400">{repoName}</p>
            </div>
            {runs.length > 0 && (
              <>
                <div>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">Branch</span>
                  <p className="text-slate-600 dark:text-slate-400">{runs[0].result.branch || '—'}</p>
                </div>
                <div>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">Commit</span>
                  <p className="text-slate-600 dark:text-slate-400">{runs[0].result.commit?.slice(0, 8) || '—'}</p>
                </div>
                <div>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">Analysis ID</span>
                  <p className="text-slate-600 dark:text-slate-400">{runs[0].result.analysis_id || '—'}</p>
                </div>
              </>
            )}
          </div>
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
              className="w-full px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4"
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
                  'Compare'
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
            onEvalChange={(side: string, field: string, value: string) => {
              const newRuns = [...runs];
              if (!newRuns[idx].userEvaluation) newRuns[idx].userEvaluation = {};
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const eval_ = newRuns[idx].userEvaluation as any;
              if (!eval_[side]) {
                eval_[side] = {};
              }
              eval_[side][field] = value;
              setRuns(newRuns);
            }}
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
  onEvalChange: (side: string, field: string, value: string) => void;
}

function ComparisonResult({ run, index, onEvalChange }: ComparisonResultProps) {
  const { result } = run;

  return (
    <div className="mb-12">
      {/* Test Header */}
      <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">
        Test {index + 1}: {run.question}
      </h2>

      {/* Two Panels */}
      <div className="grid grid-cols-2 gap-6 mb-8">
        <SidePanel side="without_rim" label="WITHOUT RIM" result={result} run={run} onEvalChange={onEvalChange} />
        <SidePanel side="with_rim" label="WITH RIM" result={result} run={run} onEvalChange={onEvalChange} showRimContribution={true} />
      </div>

      {/* Context Difference */}
      <Card className="mb-6">
        <CardHeader title="Context Difference" />
        <div className="p-6">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="font-semibold text-slate-700 dark:text-slate-300">Only in WITHOUT RIM</span>
              <div className="mt-2 space-y-1">
                {result.context_diff.files_only_without_rim.length > 0 ? (
                  result.context_diff.files_only_without_rim.slice(0, 5).map((f) => (
                    <code key={f} className="text-xs text-slate-600 dark:text-slate-400 block truncate">{f}</code>
                  ))
                ) : (
                  <span className="text-slate-500">—</span>
                )}
                {result.context_diff.files_only_without_rim.length > 5 && (
                  <span className="text-xs text-slate-500">+{result.context_diff.files_only_without_rim.length - 5} more</span>
                )}
              </div>
            </div>
            <div>
              <span className="font-semibold text-slate-700 dark:text-slate-300">Shared</span>
              <div className="mt-2 space-y-1">
                {result.context_diff.shared_files.length > 0 ? (
                  result.context_diff.shared_files.slice(0, 5).map((f) => (
                    <code key={f} className="text-xs text-slate-600 dark:text-slate-400 block truncate">{f}</code>
                  ))
                ) : (
                  <span className="text-slate-500">—</span>
                )}
                {result.context_diff.shared_files.length > 5 && (
                  <span className="text-xs text-slate-500">+{result.context_diff.shared_files.length - 5} more</span>
                )}
              </div>
            </div>
            <div>
              <span className="font-semibold text-slate-700 dark:text-slate-300">Only in WITH RIM</span>
              <div className="mt-2 space-y-1">
                {result.context_diff.files_only_with_rim.length > 0 ? (
                  result.context_diff.files_only_with_rim.slice(0, 5).map((f) => (
                    <code key={f} className="text-xs text-slate-600 dark:text-slate-400 block truncate">{f}</code>
                  ))
                ) : (
                  <span className="text-slate-500">—</span>
                )}
                {result.context_diff.files_only_with_rim.length > 5 && (
                  <span className="text-xs text-slate-500">+{result.context_diff.files_only_with_rim.length - 5} more</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Comparison Summary Table */}
      <Card className="mb-6">
        <CardHeader title="Comparison Summary" />
        <div className="p-6 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700">
                <th className="text-left py-2 px-3 font-semibold text-slate-700 dark:text-slate-300">Metric</th>
                <th className="text-right py-2 px-3 font-semibold text-slate-700 dark:text-slate-300">WITHOUT RIM</th>
                <th className="text-right py-2 px-3 font-semibold text-slate-700 dark:text-slate-300">WITH RIM</th>
                <th className="text-right py-2 px-3 font-semibold text-slate-700 dark:text-slate-300">Difference</th>
              </tr>
            </thead>
            <tbody>
              <MetricRow
                label="Files Retrieved"
                without={result.without_rim.retrieval_metrics.files_retrieved}
                with={result.with_rim.retrieval_metrics.files_retrieved}
              />
              <MetricRow
                label="Symbols Retrieved"
                without={result.without_rim.retrieval_metrics.symbols_retrieved}
                with={result.with_rim.retrieval_metrics.symbols_retrieved}
              />
              <MetricRow
                label="RIM Relationships"
                without={0}
                with={result.with_rim.retrieval_metrics.rim_relationships_count || 0}
              />
              <MetricRow
                label="Input Tokens"
                without={result.without_rim.llm_efficiency_metrics.input_tokens}
                with={result.with_rim.llm_efficiency_metrics.input_tokens}
              />
              <MetricRow
                label="Output Tokens"
                without={result.without_rim.llm_efficiency_metrics.output_tokens}
                with={result.with_rim.llm_efficiency_metrics.output_tokens}
              />
              <MetricRow
                label="Total Tokens"
                without={result.without_rim.llm_efficiency_metrics.total_tokens}
                with={result.with_rim.llm_efficiency_metrics.total_tokens}
              />
              <MetricRow
                label="Total Latency (ms)"
                without={result.without_rim.llm_efficiency_metrics.total_latency_ms.toFixed(0)}
                with={result.with_rim.llm_efficiency_metrics.total_latency_ms.toFixed(0)}
              />
            </tbody>
          </table>
        </div>
      </Card>

      {/* Research Summary */}
      <ResearchSummary result={result} />
    </div>
  );
}

interface SidePanelProps {
  side: 'without_rim' | 'with_rim';
  label: string;
  result: RIMComparisonResponse;
  run: ComparisonRun;
  onEvalChange: (side: string, field: string, value: string) => void;
  showRimContribution?: boolean;
}

function SidePanel({
  side,
  label,
  result,
  run,
  onEvalChange,
  showRimContribution = false
}: SidePanelProps) {
  const sideData = result[side];
  const traceData = result.trace;

  return (
    <Card>
      <CardHeader title={label} subtitle={side === 'with_rim' ? 'RIM-Enhanced Retrieval' : 'Standard Retrieval'} />
      <div className="p-6 space-y-4">
        {/* Answer */}
        <div>
          <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-2">Answer</h4>
          <p className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed whitespace-pre-wrap">
            {sideData.answer}
          </p>
        </div>

        {/* Retrieval Metrics */}
        <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
          <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-3 text-sm">Retrieval Metrics</h4>
          <div className="grid grid-cols-2 gap-2 text-xs text-slate-700 dark:text-slate-300">
            <div>
              <span className="text-slate-500 dark:text-slate-400">Files:</span>
              <span className="ml-2 font-mono">{sideData.retrieval_metrics.files_retrieved}</span>
            </div>
            <div>
              <span className="text-slate-500 dark:text-slate-400">Symbols:</span>
              <span className="ml-2 font-mono">{sideData.retrieval_metrics.symbols_retrieved}</span>
            </div>
            <div>
              <span className="text-slate-500 dark:text-slate-400">Retrieval:</span>
              <span className="ml-2 font-mono">{sideData.retrieval_metrics.retrieval_latency_ms.toFixed(0)}ms</span>
            </div>
            {showRimContribution && (
              <div>
                <span className="text-slate-500 dark:text-slate-400">RIM rels:</span>
                <span className="ml-2 font-mono">{sideData.retrieval_metrics.rim_relationships_count || 0}</span>
              </div>
            )}
          </div>
        </div>

        {/* LLM Efficiency */}
        <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
          <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-3 text-sm">LLM Efficiency</h4>
          <div className="space-y-1 text-xs text-slate-700 dark:text-slate-300">
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">Input Tokens:</span>
              <span className="font-mono">{sideData.llm_efficiency_metrics.input_tokens !== null ? sideData.llm_efficiency_metrics.input_tokens : 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">Output Tokens:</span>
              <span className="font-mono">{sideData.llm_efficiency_metrics.output_tokens !== null ? sideData.llm_efficiency_metrics.output_tokens : 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">Total:</span>
              <span className="font-mono">{sideData.llm_efficiency_metrics.total_tokens !== null ? sideData.llm_efficiency_metrics.total_tokens : 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">LLM Time:</span>
              <span className="font-mono">{sideData.llm_efficiency_metrics.llm_latency_ms.toFixed(0)}ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">Total Time:</span>
              <span className="font-mono font-bold">{sideData.llm_efficiency_metrics.total_latency_ms.toFixed(0)}ms</span>
            </div>
          </div>
        </div>

        {/* Retrieved Context */}
        <Collapsible title="Retrieved Context" defaultOpen={false}>
          <div className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
            {sideData.retrieved_files.length > 0 ? (
              <div>
                <span className="font-semibold text-slate-700 dark:text-slate-300">Files:</span>
                <div className="mt-1 space-y-1 ml-2">
                  {sideData.retrieved_files.map((f) => (
                    <code key={f} className="block text-slate-600 dark:text-slate-400 truncate">{f}</code>
                  ))}
                </div>
              </div>
            ) : (
              <span className="text-slate-500">No files retrieved</span>
            )}
            {sideData.retrieved_symbols.length > 0 && (
              <div className="mt-3">
                <span className="font-semibold text-slate-700 dark:text-slate-300">Symbols:</span>
                <div className="mt-1 space-y-1 ml-2">
                  {sideData.retrieved_symbols.map((s) => (
                    <code key={s} className="block text-slate-600 dark:text-slate-400 truncate">{s}</code>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Collapsible>

        {/* View LLM Context */}
        <Collapsible title="View LLM Context" defaultOpen={false}>
          <div className="space-y-3 text-xs text-slate-700 dark:text-slate-300">
            <div>
              <span className="font-semibold block mb-2 text-slate-700 dark:text-slate-300">Context Block ({sideData.context_block.length} chars):</span>
              <pre className="bg-slate-900 text-slate-100 p-3 rounded overflow-x-auto text-xs max-h-48 overflow-y-auto">
                {sideData.context_block}
              </pre>
            </div>
          </div>
        </Collapsible>

        {/* What Did RIM Add? */}
        {showRimContribution && (
          <Collapsible title="What Did RIM Add?" defaultOpen={true}>
            <div className="space-y-3 text-xs text-slate-700 dark:text-slate-300">
              {traceData.rim_seed_entities.length > 0 ? (
                <>
                  <div>
                    <span className="font-semibold block mb-2">Seed Entities ({traceData.rim_seed_entities.length}):</span>
                    <div className="ml-2 space-y-1">
                      {traceData.rim_seed_entities.slice(0, 5).map((e, i) => (
                        <div key={i} className="text-slate-600 dark:text-slate-400">
                          <code className="bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded">{e.name}</code>
                          <span className="ml-2 text-slate-500">→ {e.file_path}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <span className="font-semibold block mb-2">Relationships Traversed ({traceData.rim_relationships_traversed.length}):</span>
                    <div className="ml-2 space-y-1">
                      {traceData.rim_relationships_traversed.slice(0, 5).map((r, i) => (
                        <div key={i} className="text-slate-600 dark:text-slate-400">
                          <Badge variant="info" className="text-xs">{r.rel_type}</Badge>
                          <span className="ml-2">{r.expansion_reason}</span>
                        </div>
                      ))}
                      {traceData.rim_relationships_traversed.length > 5 && (
                        <span className="text-slate-500 text-xs">+{traceData.rim_relationships_traversed.length - 5} more relationships</span>
                      )}
                    </div>
                  </div>

                  {traceData.files_added_by_rim.length > 0 && (
                    <div>
                      <span className="font-semibold block mb-2">Files Added by RIM ({traceData.files_added_by_rim.length}):</span>
                      <div className="ml-2 space-y-1">
                        {traceData.files_added_by_rim.slice(0, 5).map((f) => (
                          <code key={f} className="block text-slate-600 dark:text-slate-400 truncate">
                            + {f}
                          </code>
                        ))}
                        {traceData.files_added_by_rim.length > 5 && (
                          <span className="text-slate-500 text-xs">+{traceData.files_added_by_rim.length - 5} more files</span>
                        )}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <span className="text-slate-500">RIM did not add any entities.</span>
              )}
            </div>
          </Collapsible>
        )}

        {/* Quality Evaluation */}
        <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
          <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-3 text-sm">Evaluate Answer</h4>
          <div className="space-y-3">
            <EvaluationControl
              label="Correctness"
              options={['Correct', 'Partially Correct', 'Incorrect']}
              value={run.userEvaluation?.[side]?.correctness}
              onChange={(v) => onEvalChange(side, 'correctness', v)}
            />
            <EvaluationControl
              label="Grounding"
              options={['Grounded', 'Partially Grounded', 'Hallucinated']}
              value={run.userEvaluation?.[side]?.grounding}
              onChange={(v) => onEvalChange(side, 'grounding', v)}
            />
            <div>
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1 block">Notes</label>
              <textarea
                value={run.userEvaluation?.[side]?.notes || ''}
                onChange={(e) => onEvalChange(side, 'notes', e.target.value)}
                placeholder="Any additional observations..."
                className="w-full px-2 py-1 text-xs rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100"
                rows={2}
              />
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}

interface EvaluationControlProps {
  label: string;
  options: string[];
  value?: string;
  onChange: (value: string) => void;
}

function EvaluationControl({ label, options, value, onChange }: EvaluationControlProps) {
  return (
    <div>
      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2 block">{label}</label>
      <div className="space-y-1">
        {options.map((option) => (
          <label key={option} className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name={label}
              value={option}
              checked={value === option}
              onChange={(e) => onChange(e.target.value)}
              className="w-4 h-4"
            />
            <span className="text-sm text-slate-700 dark:text-slate-300">{option}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

interface MetricRowProps {
  label: string;
  without: any;
  with: any;
}

function MetricRow({ label, without, with: withVal }: MetricRowProps) {
  const withoutStr = withoutVal(without);
  const withStr = withoutVal(withVal);

  function withoutVal(v: any): string {
    if (v === null || v === undefined) return 'N/A';
    if (typeof v === 'number' && v !== Math.floor(v)) return v.toFixed(1);
    return String(v);
  }

  let diff = '';
  if (typeof without === 'number' && typeof withVal === 'number') {
    const delta = withVal - without;
    const pct = without !== 0 ? ((delta / without) * 100).toFixed(1) : '—';
    diff = delta >= 0 ? `+${delta} (${pct}%)` : `${delta} (${pct}%)`;
  }

  return (
    <tr className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800">
      <td className="py-2 px-3 text-slate-900 dark:text-slate-100">{label}</td>
      <td className="py-2 px-3 text-right text-slate-600 dark:text-slate-400 font-mono">{withoutStr}</td>
      <td className="py-2 px-3 text-right text-slate-600 dark:text-slate-400 font-mono">{withStr}</td>
      <td className="py-2 px-3 text-right text-slate-600 dark:text-slate-400 font-mono text-xs">{diff}</td>
    </tr>
  );
}

function ResearchSummary({ result }: { result: RIMComparisonResponse }) {
  const { trace, without_rim, with_rim } = result;

  const rimAddedFiles = trace.files_added_by_rim.length;
  const rimRels = trace.rim_relationships_traversed.length;

  const tokenDiff = without_rim.llm_efficiency_metrics.total_tokens && with_rim.llm_efficiency_metrics.total_tokens
    ? with_rim.llm_efficiency_metrics.total_tokens - without_rim.llm_efficiency_metrics.total_tokens
    : null;

  const latencyDiff = with_rim.llm_efficiency_metrics.total_latency_ms - without_rim.llm_efficiency_metrics.total_latency_ms;

  return (
    <Card>
      <CardHeader title="Research Summary" />
      <div className="p-6 space-y-3 text-sm text-slate-700 dark:text-slate-300">
        <div className="flex items-start gap-2">
          <ArrowRight className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
          <span>
            {rimAddedFiles > 0
              ? `RIM discovered ${rimAddedFiles} additional file(s) through ${rimRels} relationship(s).`
              : 'RIM did not discover additional files for this query.'}
          </span>
        </div>

        {tokenDiff !== null && (
          <div className="flex items-start gap-2">
            <ArrowRight className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
            <span>
              {tokenDiff < 0
                ? `RIM reduced total tokens by ${Math.abs(tokenDiff)} (${((tokenDiff / (without_rim.llm_efficiency_metrics.total_tokens || 1)) * 100).toFixed(1)}%).`
                : tokenDiff > 0
                  ? `RIM increased total tokens by ${tokenDiff} (${((tokenDiff / (without_rim.llm_efficiency_metrics.total_tokens || 1)) * 100).toFixed(1)}%).`
                  : 'Token counts were identical.'}
            </span>
          </div>
        )}

        <div className="flex items-start gap-2">
          <ArrowRight className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
          <span>
            {latencyDiff < 0
              ? `WITH RIM was ${Math.abs(latencyDiff).toFixed(0)}ms faster.`
              : latencyDiff > 0
                ? `WITH RIM was ${latencyDiff.toFixed(0)}ms slower.`
                : 'Total latency was identical.'}
          </span>
        </div>

        <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-950 rounded-lg border border-blue-200 dark:border-blue-800">
          <p className="text-xs text-blue-900 dark:text-blue-100">
            <span className="font-semibold">Research Note:</span> Manual evaluation of answer quality (Correct/Partially Correct/Incorrect, Grounded/Partially Grounded/Hallucinated) is required to draw conclusions about whether RIM improves answer accuracy.
          </p>
        </div>
      </div>
    </Card>
  );
}
