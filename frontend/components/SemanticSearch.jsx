"use client";

import React, { useState, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { useTaskStatus } from '../hooks/useTaskStatus';

export default function SemanticSearch({ repoName }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  
  const [indexState, setIndexState] = useState('checking');
  const [indexMessage, setIndexMessage] = useState("");
  const taskStatus = useTaskStatus(repoName, 'semantic_index');
  
  // Selected symbol for explanation drawer
  const [selectedItem, setSelectedItem] = useState(null);
  const [explanationData, setExplanationData] = useState(null);
  const [isExplaining, setIsExplaining] = useState(false);
  const [explainError, setExplainError] = useState(null);
  const [explanationCache, setExplanationCache] = useState({});

  useEffect(() => {
    if (taskStatus === 'processing') {
      setIndexState((prev) => (prev === 'ready' ? 'ready' : 'building'));
      setIndexMessage('Building the semantic index... This may take a moment.');
    } else if (taskStatus === 'completed') {
      setIndexState('ready');
      setIndexMessage('Semantic index up to date.');
      setTimeout(() => setIndexMessage(''), 4000);
    } else if (taskStatus === 'failed') {
      setIndexState('ready');
      setError('Semantic index build failed or unavailable.');
    }
  }, [taskStatus]);
  
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    
    const buildIndex = async () => {
      setError(null);
      
      try {
        const statusRes = await fetch(`/api/repos/${repoName}/semantic-status`);
        if (!statusRes.ok) throw new Error("Failed to check index status");
        const statusData = await statusRes.json();
        
        if (isMounted) {
          if (statusData.has_index) {
            setIndexState('ready');
          } else {
            setIndexState('building');
            setIndexMessage("Building the semantic index for the first time. This may take a moment.");
          }
        }
        
        const res = await fetch(`/api/repos/${repoName}/semantic-index`, {
          method: 'POST'
        });
        
        if (!res.ok) {
          throw new Error("Failed to build semantic index");
        }

        const data = await res.json();
        if (data.status === 'completed' || data.status === 'idle') {
          if (isMounted) {
            setIndexState('ready');
          }
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message);
          setIndexState('ready');
        }
      }
    };
    
    buildIndex();
    
    // Safety fallback: ensure UI does not get stuck in full-page loading spinner
    const timer = setTimeout(() => {
      if (isMounted) {
        setIndexState((curr) => (curr !== 'ready' ? 'ready' : curr));
      }
    }, 4000);

    return () => {
      isMounted = false;
      clearTimeout(timer);
    };
  }, [repoName]);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setError(null);
    setHasSearched(true);

    try {
      const res = await fetch(`/api/repos/${repoName}/semantic-search?q=${encodeURIComponent(query)}`);
      if (!res.ok) {
        throw new Error("Semantic search failed");
      }
      const data = await res.json();
      setResults(data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSearching(false);
    }
  };

  const fetchExplanation = useCallback(async (item, forceRegenerate = false) => {
    const cacheKey = item.symbol_id || `${item.file_path}:${item.match_name}`;
    
    // Instant cache retrieval if available in local state and not forcing regeneration
    if (!forceRegenerate && explanationCache[cacheKey]) {
      setExplanationData(explanationCache[cacheKey]);
      return;
    }

    setIsExplaining(true);
    setExplainError(null);

    try {
      const res = await fetch(`/api/repos/${repoName}/symbols/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol_id: item.symbol_id || null,
          name: item.match_name || item.name || null,
          file_path: item.file_path || null,
          match_type: item.match_type || item.type || null,
          regenerate: forceRegenerate
        })
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Failed to explain symbol (${res.status})`);
      }

      const data = await res.json();
      setExplanationData(data);
      setExplanationCache((prev) => ({
        ...prev,
        [cacheKey]: data,
        [data.symbol_id]: data
      }));
    } catch (err) {
      console.error("Explanation error:", err);
      setExplainError(err.message || "Failed to generate symbol explanation");
    } finally {
      setIsExplaining(false);
    }
  }, [repoName, explanationCache]);

  const handleSelectSymbol = (item) => {
    setSelectedItem(item);
    setExplainError(null);
    const cacheKey = item.symbol_id || `${item.file_path}:${item.match_name}`;
    if (explanationCache[cacheKey]) {
      setExplanationData(explanationCache[cacheKey]);
    } else {
      setExplanationData(null);
      fetchExplanation(item, false);
    }
  };

  const handleCloseDrawer = () => {
    setSelectedItem(null);
    setExplanationData(null);
    setExplainError(null);
  };

  // Keyboard shortcut to close drawer with Esc
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && selectedItem) {
        handleCloseDrawer();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedItem]);

  const getTypeBadgeColor = (type) => {
    const t = (type || '').toLowerCase();
    if (t.includes('route')) return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800';
    if (t.includes('class') || t.includes('struct') || t.includes('interface')) return 'bg-blue-100 text-blue-800 dark:bg-blue-950/80 dark:text-blue-300 border-blue-200 dark:border-blue-800';
    if (t.includes('table') || t.includes('database') || t.includes('model')) return 'bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300 border-amber-200 dark:border-amber-800';
    return 'bg-purple-100 text-purple-800 dark:bg-purple-950/80 dark:text-purple-300 border-purple-200 dark:border-purple-800';
  };

  if (indexState === 'checking' || indexState === 'building' || indexState === 'updating') {
    return (
      <div className="h-full flex flex-col items-center justify-center text-gray-500 dark:text-slate-400 bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-gray-200 dark:border-slate-800 p-8">
        <svg className="animate-spin h-10 w-10 text-purple-500 dark:text-purple-400 mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <p className="font-semibold text-lg text-slate-900 dark:text-slate-100">
          {indexState === 'checking' && "Checking Index Status..."}
          {indexState === 'building' && "Building Semantic Index"}
          {indexState === 'updating' && "Updating Changed Files"}
        </p>
        <p className="text-sm mt-2 max-w-sm text-center text-slate-500 dark:text-slate-400">{indexMessage}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-purple-50/30 dark:bg-slate-950 rounded-lg shadow-sm border border-purple-100 dark:border-slate-800 overflow-hidden relative text-slate-900 dark:text-slate-100">
      
      {/* Status Toast */}
      {indexMessage && (
        <div className="absolute top-4 right-4 z-50 bg-green-50 dark:bg-green-950/80 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-300 px-4 py-3 rounded shadow-sm text-sm font-medium animate-fade-in-down">
          <div className="flex items-center gap-2">
            <span className="text-green-500 dark:text-green-400">✓</span>
            {indexMessage}
          </div>
        </div>
      )}
      
      {/* Search Header */}
      <div className="p-6 bg-white dark:bg-slate-900 border-b border-purple-100 dark:border-slate-800 shadow-sm z-10">
        <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-2 flex items-center gap-2">
          <span className="text-2xl">✨</span> Semantic Search
        </h2>
        <p className="text-sm text-gray-500 dark:text-slate-400 mb-4">Search by concepts and natural language. Click any result to view how it works.</p>
        
        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="relative flex-grow">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <span className="text-purple-400 dark:text-purple-400 font-bold font-mono">?</span>
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="block w-full pl-10 pr-3 py-3 border border-purple-200 dark:border-slate-700 rounded-md leading-5 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:placeholder-gray-300 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 sm:text-sm transition duration-150 ease-in-out shadow-inner"
              placeholder="e.g. 'handle user login', 'JWT authentication', or 'database transaction'"
            />
          </div>
          <button
            type="submit"
            disabled={isSearching || !query.trim()}
            className="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-purple-600 dark:bg-purple-600 hover:bg-purple-700 dark:hover:bg-purple-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:bg-purple-400 transition duration-150 ease-in-out cursor-pointer"
          >
            {isSearching ? 'Searching...' : 'Ask AI'}
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>
      
      {/* Search Results & Slide-over Drawer Area */}
      <div className="flex-grow overflow-hidden flex relative">
        
        {/* Results List */}
        <div className={`flex-grow overflow-y-auto p-6 transition-all duration-200 ${selectedItem ? 'w-full lg:w-1/2 pr-3' : 'w-full'}`}>
          <div className="absolute inset-0 pointer-events-none flex items-center justify-center opacity-[0.03] dark:opacity-[0.05]">
            <svg className="w-96 h-96" viewBox="0 0 100 100" fill="currentColor">
              <path d="M50 0L60.9789 39.0211L100 50L60.9789 60.9789L50 100L39.0211 60.9789L0 50L39.0211 39.0211L50 0Z" />
            </svg>
          </div>

          {!hasSearched ? (
            <div className="text-center py-12 relative z-10">
              <div className="mx-auto h-12 w-12 text-purple-200 dark:text-purple-400 text-5xl mb-4">🧠</div>
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-slate-200">Semantic AI Search</h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">Enter a concept to discover related code using hybrid AST & vector embeddings.</p>
            </div>
          ) : results.length === 0 ? (
            <div className="text-center py-12 bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-800 relative z-10">
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-slate-200">No results found</h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">Try rephrasing your concept or searching for a general topic.</p>
            </div>
          ) : (
            <div className="space-y-4 relative z-10">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-gray-500 dark:text-slate-400">
                  Found {results.length} semantic matche{results.length === 1 ? '' : 's'}
                </h3>
                <span className="text-xs text-purple-600 dark:text-purple-400 font-medium">
                  Click any card to explain
                </span>
              </div>
              <ul className="space-y-3">
                {results.map((result, idx) => {
                  const isSelected = selectedItem && (
                    (selectedItem.symbol_id && selectedItem.symbol_id === result.symbol_id) ||
                    (selectedItem.match_name === result.match_name && selectedItem.file_path === result.file_path)
                  );
                  return (
                    <li
                      key={result.symbol_id || idx}
                      onClick={() => handleSelectSymbol(result)}
                      className={`px-4 py-4 sm:px-6 rounded-lg shadow-sm border transition-all duration-150 relative overflow-hidden group cursor-pointer ${
                        isSelected
                          ? 'bg-purple-50/80 dark:bg-purple-950/40 border-purple-500 dark:border-purple-400 ring-2 ring-purple-500/20'
                          : 'bg-white dark:bg-slate-900 border-purple-100 dark:border-slate-800 hover:border-purple-300 dark:hover:border-purple-500 hover:shadow-md'
                      }`}
                    >
                      <div
                        className="absolute bottom-0 left-0 h-1 bg-purple-500 transition-all duration-300"
                        style={{ width: `${Math.max(15, 100 - ((result.distance || 0) * 50))}%` }}
                      ></div>
                      
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-medium text-slate-500 dark:text-slate-400 truncate font-mono flex items-center gap-1.5">
                          <span>📄</span>
                          <span>
                            {result.file_path || 'Repository root'}
                            {result.line_start ? `:${result.line_start}${result.line_end ? `-${result.line_end}` : ''}` : ''}
                          </span>
                        </p>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wider border ${getTypeBadgeColor(result.match_type)}`}>
                          {result.match_type || 'SYMBOL'}
                        </span>
                      </div>
                      
                      <div className="mt-2 flex items-center justify-between">
                        <p className="text-base text-gray-900 dark:text-slate-100 font-bold font-mono group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">
                          {result.match_name}
                          {!result.match_name?.includes('(') && !result.match_name?.includes(' ') && (result.match_type === 'function' || result.match_type === 'method') ? '()' : ''}
                        </p>
                        <span className="text-xs text-purple-500 dark:text-purple-400 opacity-0 group-hover:opacity-100 transition-opacity font-medium flex items-center gap-0.5">
                          Explain <span>→</span>
                        </span>
                      </div>

                      {result.route && (
                        <div className="mt-2 flex items-center gap-2">
                          <span className="text-xs px-2 py-0.5 bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 rounded font-mono border border-emerald-200 dark:border-emerald-900">
                            {result.route}
                          </span>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>

        {/* Explanation Side Panel / Drawer */}
        {selectedItem && (
          <div className="w-full lg:w-1/2 border-l border-purple-100 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full z-20 shadow-xl overflow-hidden animate-fade-in">
            
            {/* Drawer Header */}
            <div className="p-5 border-b border-purple-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/90 flex items-start justify-between gap-3">
              <div className="flex-grow min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wider border ${getTypeBadgeColor(selectedItem.match_type)}`}>
                    {selectedItem.match_type || 'SYMBOL'}
                  </span>
                  {explanationData?.cached && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-950/80 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                      Cached in Fact Store
                    </span>
                  )}
                  {explanationData && !explanationData.cached && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-purple-50 text-purple-700 dark:bg-purple-950/80 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
                      ✨ Fresh AI Generation
                    </span>
                  )}
                </div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-slate-100 font-mono truncate">
                  {selectedItem.match_name}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 font-mono truncate mt-0.5">
                  {selectedItem.file_path || 'Repository root'}
                  {selectedItem.line_start ? `:${selectedItem.line_start}${selectedItem.line_end ? `-${selectedItem.line_end}` : ''}` : ''}
                </p>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  type="button"
                  onClick={() => fetchExplanation(selectedItem, true)}
                  disabled={isExplaining}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-purple-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-slate-700 focus:outline-none transition-colors disabled:opacity-50 cursor-pointer shadow-sm"
                  title="Force re-generation with LLM"
                >
                  <svg className={`h-3.5 w-3.5 ${isExplaining ? 'animate-spin' : ''}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <span>{isExplaining ? 'Generating...' : 'Regenerate'}</span>
                </button>
                
                <button
                  type="button"
                  onClick={handleCloseDrawer}
                  className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                  title="Close (Esc)"
                >
                  <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Drawer Body */}
            <div className="flex-grow overflow-y-auto p-6 space-y-6">
              
              {/* Loading Skeleton */}
              {isExplaining && !explanationData && (
                <div className="space-y-4 animate-pulse">
                  <div className="h-4 bg-purple-100 dark:bg-slate-800 rounded w-1/3"></div>
                  <div className="h-20 bg-purple-50 dark:bg-slate-800/60 rounded"></div>
                  <div className="h-4 bg-purple-100 dark:bg-slate-800 rounded w-1/4"></div>
                  <div className="h-28 bg-purple-50 dark:bg-slate-800/60 rounded"></div>
                  <div className="h-4 bg-purple-100 dark:bg-slate-800 rounded w-1/2"></div>
                  <div className="h-16 bg-purple-50 dark:bg-slate-800/60 rounded"></div>
                  <p className="text-xs text-center text-purple-600 dark:text-purple-400 font-mono mt-4">
                    Analyzing AST facts & synthesizing explanation...
                  </p>
                </div>
              )}

              {/* Error State */}
              {explainError && (
                <div className="p-4 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300 space-y-2">
                  <p className="font-semibold flex items-center gap-1.5">
                    <span>⚠️</span> Failed to generate explanation
                  </p>
                  <p className="text-xs opacity-90">{explainError}</p>
                  <button
                    type="button"
                    onClick={() => fetchExplanation(selectedItem, true)}
                    className="inline-flex items-center px-3 py-1 bg-red-600 text-white rounded text-xs font-medium hover:bg-red-700 transition cursor-pointer"
                  >
                    Retry
                  </button>
                </div>
              )}

              {/* Explanation Content */}
              {explanationData && (
                <div className="space-y-6">
                  
                  {/* AST Relational Badges (if present) */}
                  {(explanationData.outgoing_calls?.length > 0 ||
                    explanationData.incoming_calls?.length > 0 ||
                    explanationData.routes?.length > 0 ||
                    explanationData.database_ops?.length > 0) && (
                    <div className="p-3.5 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-200/80 dark:border-slate-800 space-y-2 text-xs font-mono">
                      <p className="font-semibold text-slate-700 dark:text-slate-300 uppercase text-[10px] tracking-wider">
                        AST Relational Context
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {explanationData.outgoing_calls?.map((c, i) => (
                          <span key={i} className="px-2 py-0.5 bg-purple-50 dark:bg-purple-950/50 text-purple-700 dark:text-purple-300 rounded border border-purple-200/60 dark:border-purple-800/60">
                            Calls: {c}
                          </span>
                        ))}
                        {explanationData.incoming_calls?.map((c, i) => (
                          <span key={i} className="px-2 py-0.5 bg-blue-50 dark:bg-blue-950/50 text-blue-700 dark:text-blue-300 rounded border border-blue-200/60 dark:border-blue-800/60">
                            Called by: {c}
                          </span>
                        ))}
                        {explanationData.routes?.map((r, i) => (
                          <span key={i} className="px-2 py-0.5 bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 rounded border border-emerald-200/60 dark:border-emerald-800/60">
                            Route: {r}
                          </span>
                        ))}
                        {explanationData.database_ops?.map((d, i) => (
                          <span key={i} className="px-2 py-0.5 bg-amber-50 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300 rounded border border-amber-200/60 dark:border-amber-800/60">
                            DB: {d}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Markdown Explanation Body */}
                  <div className="prose prose-sm dark:prose-invert max-w-none text-slate-800 dark:text-slate-200 prose-headings:font-bold prose-headings:text-slate-900 dark:prose-headings:text-slate-100 prose-h3:text-sm prose-h3:border-b prose-h3:border-slate-200 dark:prose-h3:border-slate-800 prose-h3:pb-1 prose-h3:mt-5 prose-h3:mb-2 prose-p:text-xs prose-p:leading-relaxed prose-li:text-xs prose-code:font-mono prose-code:text-[11px] prose-code:bg-slate-100 dark:prose-code:bg-slate-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded">
                    <ReactMarkdown>{explanationData.explanation}</ReactMarkdown>
                  </div>

                  {/* Footer metadata */}
                  {explanationData.generated_at && (
                    <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-[11px] text-slate-400 font-mono">
                      <span>Hash: {explanationData.signature_hash}</span>
                      <span>Generated: {new Date(explanationData.generated_at).toLocaleDateString()} {new Date(explanationData.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
