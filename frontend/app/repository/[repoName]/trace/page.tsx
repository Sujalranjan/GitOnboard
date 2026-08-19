"use client";

import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { Card, CardHeader } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { GitMerge, Search, Loader2, Sparkles, ArrowDown, Maximize2, X, RotateCcw, HelpCircle } from 'lucide-react';

function FeatureTracingContent(props: any) {
  const [repoName, setRepoName] = useState<string>('');
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get('q') || '';
  
  const [query, setQuery] = useState(initialQuery);
  const [isTracing, setIsTracing] = useState(false);
  const [traceResult, setTraceResult] = useState<any>(null);
  const [contextPack, setContextPack] = useState<any>(null);
  
  const [isExplaining, setIsExplaining] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explainMeta, setExplainMeta] = useState<{ provider?: string; ai_generated?: boolean } | null>(null);
  const [lastSearchedQuery, setLastSearchedQuery] = useState<string>("");
  const [isExpanded, setIsExpanded] = useState(false);
  const [showRegenConfirm, setShowRegenConfirm] = useState(false);

  // Cache helper key generator
  const getCacheKey = (repo: string, feat: string) => `trace_explain_${repo}_${feat.trim().toLowerCase()}`;

  useEffect(() => {
    Promise.resolve(props.params).then((params) => {
      setRepoName(params.repoName);
    });
  }, [props.params]);

  useEffect(() => {
    if (repoName && initialQuery) {
      handleTraceSubmit(initialQuery);
    }
  }, [repoName, initialQuery]);

  const handleTraceSubmit = async (searchFeature: string) => {
    const trimmed = searchFeature.trim();
    if (!trimmed) return;

    // If searching the same query and we already have results, keep the existing explanation
    if (trimmed === lastSearchedQuery && traceResult) {
      return;
    }

    setIsTracing(true);
    
    // Check cached explanation for this repo & feature query
    if (repoName) {
      try {
        const cached = localStorage.getItem(getCacheKey(repoName, trimmed));
        if (cached) {
          const parsed = JSON.parse(cached);
          setExplanation(parsed.explanation);
          setExplainMeta({
            provider: parsed.provider,
            ai_generated: parsed.ai_generated,
          });
        } else if (trimmed !== lastSearchedQuery) {
          setExplanation(null);
          setExplainMeta(null);
          setTraceResult(null);
        }
      } catch {
        if (trimmed !== lastSearchedQuery) {
          setExplanation(null);
          setExplainMeta(null);
          setTraceResult(null);
        }
      }
    }
    
    try {
      const res = await fetch(`/api/repos/${repoName}/trace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feature_query: trimmed })
      });
      
      if (res.ok) {
        const data = await res.json();
        setTraceResult(data);
        setLastSearchedQuery(trimmed);
        fetchContextPack(trimmed);
      } else {
        alert("Failed to trace feature.");
      }
    } catch (err) {
      console.error(err);
      alert("Error tracing feature.");
    } finally {
      setIsTracing(false);
    }
  };

  const fetchContextPack = async (searchFeature: string) => {
    try {
      const res = await fetch(`/api/repos/${repoName}/context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchFeature })
      });
      if (res.ok) {
        const data = await res.json();
        setContextPack(data.context_pack);
      }
    } catch (err) {
      console.error("Failed to fetch context pack", err);
    }
  };

  const handleTrace = (e: React.FormEvent) => {
    e.preventDefault();
    handleTraceSubmit(query);
  };

  const handleExplain = async (forceRegenerate = false) => {
    if (!traceResult) return;

    // Check cache first unless explicitly regenerating
    if (!forceRegenerate && repoName && query) {
      try {
        const cached = localStorage.getItem(getCacheKey(repoName, query));
        if (cached) {
          const parsed = JSON.parse(cached);
          setExplanation(parsed.explanation);
          setExplainMeta({
            provider: parsed.provider,
            ai_generated: parsed.ai_generated,
          });
          return;
        }
      } catch {
        // Continue to fetch
      }
    }

    setIsExplaining(true);
    setShowRegenConfirm(false);
    try {
      const res = await fetch(`/api/repos/${repoName}/trace/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          feature_query: query,
          trace_data: traceResult
        })
      });
      if (res.ok) {
        const data = await res.json();
        setExplanation(data.explanation);
        setExplainMeta({
          provider: data.provider,
          ai_generated: data.ai_generated
        });

        // Persist to cache for next time
        if (repoName && query) {
          try {
            localStorage.setItem(
              getCacheKey(repoName, query),
              JSON.stringify({
                explanation: data.explanation,
                provider: data.provider,
                ai_generated: data.ai_generated,
                timestamp: Date.now(),
              })
            );
          } catch {
            // Storage quota exceeded or disabled
          }
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        alert(errData.detail || "Failed to explain trace.");
      }
    } catch (err) {
      console.error(err);
      alert("Error fetching explanation.");
    } finally {
      setIsExplaining(false);
    }
  };

  return (
    <div className="p-8 w-full max-w-5xl mx-auto flex flex-col h-full overflow-y-auto text-slate-900 dark:text-slate-100 transition-colors">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100 tracking-tight flex items-center gap-3">
          <GitMerge className="w-8 h-8 text-blue-600 dark:text-blue-400" />
          Feature Tracing
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-2">
          Deterministically reconstruct the implementation flow of a feature across the repository.
        </p>
      </div>

      <Card className="mb-8">
        <div className="p-6">
          <form onSubmit={handleTrace} className="flex gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400 dark:text-slate-500" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Enter a feature name (e.g., Authentication, Login, Payment)"
                className="w-full pl-10 pr-4 py-3 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
                disabled={isTracing}
              />
            </div>
            <Button 
              type="submit" 
              variant="primary" 
              disabled={isTracing || !query.trim()}
              className="px-6"
            >
              {isTracing ? <Loader2 className="w-5 h-5 animate-spin" /> : "Trace Feature"}
            </Button>
          </form>
        </div>
      </Card>

      {traceResult && traceResult.flow && traceResult.flow.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100">Implementation Path</h2>
              <Badge variant="info">{traceResult.flow.length} Nodes</Badge>
            </div>
            
            <div className="space-y-2 relative">
              <div className="absolute left-6 top-6 bottom-6 w-0.5 bg-blue-100 dark:bg-blue-900/60"></div>
              
              {traceResult.flow.map((node: any, idx: number) => (
                <div key={node.id} className="relative z-10 flex flex-col items-center">
                  <div className="w-full flex items-start gap-4 group">
                    <div className="w-12 h-12 rounded-full bg-blue-50 dark:bg-blue-950/80 border-4 border-white dark:border-slate-900 shadow-sm flex items-center justify-center flex-shrink-0 z-10 text-blue-600 dark:text-blue-400 font-bold">
                      {idx + 1}
                    </div>
                    <Card className="flex-1 hover:shadow-md transition-shadow cursor-pointer">
                      <div className="p-4">
                        <div className="flex justify-between items-start mb-2">
                          <h3 className="font-bold text-slate-800 dark:text-slate-100 text-lg">{node.name}</h3>
                          <Badge variant="neutral">{node.type}</Badge>
                        </div>
                        <p className="text-sm text-slate-500 dark:text-slate-400 font-mono truncate">{node.file_id}</p>
                      </div>
                    </Card>
                  </div>
                  {idx < traceResult.flow.length - 1 && (
                    <div className="py-2 text-blue-300 dark:text-blue-500">
                      <ArrowDown className="w-6 h-6" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
          
          <div className="lg:col-span-1">
            <div className="sticky top-8 space-y-6">
              <Card>
                <CardHeader title="Graph-Aware Context" />
                <div className="p-6 space-y-4">
                  {contextPack ? (
                    <>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3">
                          <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">Features</p>
                          <p className="text-lg font-bold text-slate-900 dark:text-slate-100">{contextPack.repository?.feature_count ?? 0}</p>
                        </div>
                        <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3">
                          <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">Symbols</p>
                          <p className="text-lg font-bold text-slate-900 dark:text-slate-100">{contextPack.repository?.symbol_count ?? 0}</p>
                        </div>
                      </div>

                      <div>
                        <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">Top Features</p>
                        <div className="space-y-2">
                          {(contextPack.features || []).slice(0, 3).map((feature: any) => (
                            <div key={feature.id} className="rounded-lg bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 p-3">
                              <div className="flex items-center justify-between gap-3">
                                <div>
                                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{feature.name}</p>
                                  <p className="text-xs text-slate-500 dark:text-slate-400">{feature.member_count} members</p>
                                </div>
                                <Badge variant="neutral">{Math.round((feature.confidence || 0) * 100)}%</Badge>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {(contextPack.matched_symbols || []).length > 0 && (
                        <div>
                          <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">Matched Symbols</p>
                          <div className="space-y-2">
                            {contextPack.matched_symbols.slice(0, 3).map((symbol: any) => (
                              <div key={symbol.id} className="rounded-lg border border-slate-200 dark:border-slate-800 p-3">
                                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{symbol.name}</p>
                                <p className="text-xs text-slate-500 dark:text-slate-400 font-mono truncate">{symbol.file}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-center py-6">
                      <Sparkles className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                      <p className="text-slate-500 dark:text-slate-400 text-sm">Build a context pack to summarize features, symbols, and graph neighbors.</p>
                    </div>
                  )}
                </div>
              </Card>

              <Card>
                <CardHeader title="AI Explanation" />
                <div className="p-6">
                  {!explanation ? (
                    <div className="text-center py-8">
                      <Sparkles className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                      <p className="text-slate-500 dark:text-slate-400 mb-6 text-sm">
                        Understand how these components work together to implement the feature.
                      </p>
                      <Button 
                        variant="secondary" 
                        onClick={handleExplain}
                        disabled={isExplaining || !traceResult}
                        className="w-full"
                      >
                        {isExplaining ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Sparkles className="w-4 h-4 mr-2" />}
                        Explain Trace
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
                        {explainMeta ? (
                          <Badge variant={explainMeta.ai_generated ? "success" : "warning"}>
                            {explainMeta.ai_generated
                              ? `AI Generated (${explainMeta.provider || "ollama"})`
                              : "Deterministic fallback — No AI used"}
                          </Badge>
                        ) : <span className="text-xs text-slate-500">AI Explanation</span>}

                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setShowRegenConfirm(true)}
                            disabled={isExplaining}
                            className="flex items-center gap-1 p-1 text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 rounded transition-colors cursor-pointer"
                            title="Regenerate Explanation"
                          >
                            <RotateCcw className={`w-3.5 h-3.5 ${isExplaining ? 'animate-spin' : ''}`} />
                          </button>
                          <button
                            onClick={() => setIsExpanded(true)}
                            className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium transition-colors cursor-pointer"
                            title="Expand Full Explanation"
                          >
                            <Maximize2 className="w-3.5 h-3.5" />
                            Expand
                          </button>
                        </div>
                      </div>

                      {/* Normal Size Preview Container with Click-to-Expand */}
                      <div 
                        onClick={() => setIsExpanded(true)}
                        className="relative max-h-[320px] overflow-hidden bg-blue-50/40 dark:bg-blue-950/30 border border-blue-100/80 dark:border-blue-900/40 p-4 rounded-lg text-slate-800 dark:text-slate-200 text-sm leading-relaxed cursor-pointer hover:border-blue-300 dark:hover:border-blue-700 transition-all group"
                      >
                        <ReactMarkdown
                          components={{
                            h1: ({ node, ...props }) => <h1 className="text-sm font-bold text-blue-950 dark:text-blue-200 mb-1.5" {...props} />,
                            h2: ({ node, ...props }) => <h2 className="text-xs font-bold text-blue-900 dark:text-blue-300 mt-2 mb-1" {...props} />,
                            h3: ({ node, ...props }) => <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-300 mt-1.5 mb-1 uppercase tracking-wide" {...props} />,
                            p: ({ node, ...props }) => <p className="mb-1.5 text-xs leading-relaxed text-slate-700 dark:text-slate-300" {...props} />,
                            ul: ({ node, ...props }) => <ul className="list-disc list-inside space-y-0.5 mb-1.5 text-xs text-slate-700 dark:text-slate-300" {...props} />,
                            li: ({ node, ...props }) => <li className="leading-relaxed" {...props} />,
                            code: ({ node, className, children, ...props }) => (
                              <code className="bg-slate-200/70 dark:bg-slate-800 px-1 py-0.5 rounded font-mono text-[11px] text-blue-800 dark:text-blue-300" {...props}>
                                {children}
                              </code>
                            ),
                          }}
                        >
                          {explanation}
                        </ReactMarkdown>

                        {/* Fade-out gradient indicator with click prompt */}
                        <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-slate-50 dark:from-slate-900 to-transparent flex items-end justify-center pb-2">
                          <span className="text-[11px] font-medium text-blue-600 dark:text-blue-400 bg-white/90 dark:bg-slate-800/90 px-3 py-1 rounded-full shadow-sm border border-blue-200/50 dark:border-blue-800/50 group-hover:scale-105 transition-transform">
                            Click to expand full explanation
                          </span>
                        </div>
                      </div>

                      <Button 
                        variant="ghost" 
                        onClick={() => setShowRegenConfirm(true)}
                        disabled={isExplaining}
                        className="w-full mt-2 text-xs flex items-center justify-center gap-1.5"
                      >
                        <RotateCcw className="w-3 h-3" />
                        Regenerate
                      </Button>
                    </div>
                  )}
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}
      
      {traceResult && (!traceResult.flow || traceResult.flow.length === 0) && (
        <div className="text-center py-20 text-slate-500 dark:text-slate-400">
          <p>No deterministic trace could be constructed for this feature.</p>
        </div>
      )}

      {/* Expanded Modal Overlay with Cross Button */}
      {isExpanded && explanation && (
        <div 
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 md:p-10 animate-in fade-in duration-200"
          onClick={() => setIsExpanded(false)}
        >
          <div 
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/50">
              <div className="flex items-center gap-3">
                <Sparkles className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                <h3 className="font-bold text-slate-900 dark:text-slate-100 text-lg">
                  Feature Walkthrough: {query}
                </h3>
                {explainMeta && (
                  <Badge variant={explainMeta.ai_generated ? "success" : "warning"}>
                    {explainMeta.ai_generated
                      ? `AI Generated (${explainMeta.provider || "ollama"})`
                      : "Deterministic fallback — No AI used"}
                  </Badge>
                )}
              </div>
              <button
                onClick={() => setIsExpanded(false)}
                className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
                title="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Scrollable Content */}
            <div className="p-6 md:p-8 overflow-y-auto space-y-4 text-slate-800 dark:text-slate-200 leading-relaxed">
              <ReactMarkdown
                components={{
                  h1: ({ node, ...props }) => <h1 className="text-xl font-bold text-blue-950 dark:text-blue-200 mb-3 border-b border-blue-100 dark:border-blue-900 pb-2" {...props} />,
                  h2: ({ node, ...props }) => <h2 className="text-base font-bold text-blue-900 dark:text-blue-300 mt-5 mb-2" {...props} />,
                  h3: ({ node, ...props }) => <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mt-4 mb-1.5 uppercase tracking-wide" {...props} />,
                  p: ({ node, ...props }) => <p className="mb-3 text-sm leading-relaxed text-slate-700 dark:text-slate-300" {...props} />,
                  ul: ({ node, ...props }) => <ul className="list-disc list-inside space-y-1.5 mb-3 text-sm text-slate-700 dark:text-slate-300 pl-2" {...props} />,
                  li: ({ node, ...props }) => <li className="leading-relaxed" {...props} />,
                  code: ({ node, className, children, ...props }) => (
                    <code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono text-xs text-blue-700 dark:text-blue-300 border border-slate-200 dark:border-slate-700" {...props}>
                      {children}
                    </code>
                  ),
                }}
              >
                {explanation}
              </ReactMarkdown>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between px-6 py-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/50">
              <Button 
                variant="ghost" 
                onClick={() => {
                  setIsExpanded(false);
                  setShowRegenConfirm(true);
                }}
                className="text-xs flex items-center gap-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Regenerate Explanation
              </Button>
              <Button variant="secondary" onClick={() => setIsExpanded(false)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal Before Regenerating */}
      {showRegenConfirm && (
        <div 
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150"
          onClick={() => setShowRegenConfirm(false)}
        >
          <div 
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-full bg-blue-50 dark:bg-blue-950/80 border border-blue-200 dark:border-blue-800 flex items-center justify-center flex-shrink-0 text-blue-600 dark:text-blue-400">
                <HelpCircle className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h4 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  Regenerate Explanation?
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                  This will query the AI model again and replace the current cached walkthrough for <strong>"{query}"</strong>.
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button 
                variant="ghost" 
                onClick={() => setShowRegenConfirm(false)}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button 
                variant="primary" 
                onClick={() => handleExplain(true)}
                disabled={isExplaining}
                className="text-xs flex items-center gap-1.5"
              >
                {isExplaining ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                Yes, Regenerate
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


export default function FeatureTracingPage(props: any) {
  return (
    <React.Suspense fallback={<div className="p-6 text-slate-500">Loading trace...</div>}>
      <FeatureTracingContent {...props} />
    </React.Suspense>
  );
}
