"use client";

import React, { useState, useEffect, useCallback, useRef } from 'react';
import dynamic from 'next/dynamic';
import {
  Share2,
  Search,
  Sparkles,
  Zap,
  Box,
  Route,
  Globe,
  Layers,
  X,
  Info,
  FolderOpen,
  ChevronRight,
} from 'lucide-react';
import { buildInitialGraph, injectExpansionData } from './graphModel';

// Dynamic import for WebGL Sigma canvas to prevent SSR window/WebGL errors
const SigmaKnowledgeGraphCanvas = dynamic(
  () => import('./SigmaKnowledgeGraphCanvas'),
  {
    ssr: false,
    loading: () => (
      <div className="w-full h-full flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-950 gap-3">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-slate-500 dark:text-slate-400 font-mono">Initializing WebGL Graph Renderer...</p>
      </div>
    ),
  }
);

// ──────────────────────────────────────────────────────────────────────────
// BADGE STYLES FOR DRAWER INSPECTION
// ──────────────────────────────────────────────────────────────────────────

const typeBadgeStyles: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  FUNCTION: {
    bg: 'bg-emerald-50 dark:bg-emerald-950/70',
    border: 'border-emerald-300 dark:border-emerald-700',
    text: 'text-emerald-700 dark:text-emerald-300',
    icon: '⚡',
  },
  METHOD: {
    bg: 'bg-teal-50 dark:bg-teal-950/70',
    border: 'border-teal-300 dark:border-teal-700',
    text: 'text-teal-700 dark:text-teal-300',
    icon: '⚡',
  },
  CLASS: {
    bg: 'bg-purple-50 dark:bg-purple-950/70',
    border: 'border-purple-300 dark:border-purple-700',
    text: 'text-purple-700 dark:text-purple-300',
    icon: '🧩',
  },
  FILE: {
    bg: 'bg-blue-50 dark:bg-blue-950/70',
    border: 'border-blue-300 dark:border-blue-700',
    text: 'text-blue-700 dark:text-blue-300',
    icon: '📄',
  },
  DIRECTORY: {
    bg: 'bg-orange-50 dark:bg-orange-950/70',
    border: 'border-orange-300 dark:border-orange-700',
    text: 'text-orange-700 dark:text-orange-300',
    icon: '📁',
  },
  ROUTE: {
    bg: 'bg-amber-50 dark:bg-amber-950/70',
    border: 'border-amber-300 dark:border-amber-700',
    text: 'text-amber-700 dark:text-amber-300',
    icon: '🛣️',
  },
  DATABASE_OBJECT: {
    bg: 'bg-cyan-50 dark:bg-cyan-950/70',
    border: 'border-cyan-300 dark:border-cyan-700',
    text: 'text-cyan-700 dark:text-cyan-300',
    icon: '🗄️',
  },
  CAPABILITY: {
    bg: 'bg-rose-50 dark:bg-rose-950/70',
    border: 'border-rose-300 dark:border-rose-700',
    text: 'text-rose-700 dark:text-rose-300',
    icon: '✨',
  },
};

const edgeColorMap: Record<string, string> = {
  CALLS: '#10b981',
  IMPORTS: '#6366f1',
  INHERITS: '#a855f7',
  ROUTE_HANDLER: '#f59e0b',
  DATABASE_ACCESS: '#06b6d4',
  CAPABILITY_MEMBER: '#f43f5e',
  DECLARES: '#64748b',
  CONTAINS: '#f97316',
  USES: '#64748b',
  REFERENCES: '#38bdf8',
  GENERIC: '#64748b',
};

// ──────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ──────────────────────────────────────────────────────────────────────────

interface KnowledgeGraphViewProps {
  repoName: string;
}

export default function KnowledgeGraphView({ repoName }: KnowledgeGraphViewProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Overview-level stats (returned by knowledge-graph endpoint)
  const [overviewStats, setOverviewStats] = useState<any>(null);

  // The mutable Graphology graph (shared with canvas via ref — never replaced during expansion)
  // typed as any to avoid graphology-types resolution issues in TSC; graph methods are validated at runtime
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null);

  // Bump graphVersion to trigger local refresh (expansion)
  const [graphVersion, setGraphVersion] = useState(0);
  // Bump sigmaKey to fully remount Sigma when the graph is replaced
  const [sigmaKey, setSigmaKey] = useState(0);

  // Controls
  const [currentView, setCurrentView] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeRelFilters, setActiveRelFilters] = useState<Set<string>>(new Set());

  // Node selection & inspection
  const [selectedNode, setSelectedNode] = useState<any | null>(null);
  const [nodeDetails, setNodeDetails] = useState<any | null>(null);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);

  // Expansion tracking (for breadcrumb / UI state)
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());
  const [isExpanding, setIsExpanding] = useState(false);

  // Track current theme for graph building
  const [isDark, setIsDark] = useState(true);
  useEffect(() => {
    const checkTheme = () => {
      setIsDark(document.documentElement.classList.contains('dark') ||
        window.matchMedia('(prefers-color-scheme: dark)').matches);
    };
    checkTheme();
    const observer = new MutationObserver(checkTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  // ── Fetch full bulk knowledge graph ──
  const fetchFullGraph = useCallback(async (view = currentView) => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('view', view);
      params.set('limit', '500');
      const res = await fetch(`/api/repos/${encodeURIComponent(repoName)}/knowledge-graph?${params.toString()}`);
      if (!res.ok) {
        if (res.status === 404) {
          throw new Error(`No analyzed knowledge graph found for "${repoName}". Complete repository ingestion first.`);
        }
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `HTTP ${res.status}: Failed to fetch knowledge graph`);
      }
      const data = await res.json();
      setOverviewStats(data.stats);

      const newGraph = buildInitialGraph(data.nodes || [], data.edges || [], isDark, activeRelFilters);
      graphRef.current = newGraph;
      setSigmaKey((k) => k + 1); // full remount: new graph instance
      setGraphVersion((v) => v + 1);
      setExpandedNodeIds(new Set());
    } catch (err: any) {
      setError(err.message || 'Error loading knowledge graph');
    } finally {
      setIsLoading(false);
    }
  }, [repoName, currentView, isDark, activeRelFilters]);

  // Initial load — always load full graph
  useEffect(() => {
    if (repoName) {
      fetchFullGraph();
    }
  }, [repoName]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 3. Expand a node: fetch its children and inject into the existing graph ──
  const handleExpandNode = useCallback(async (nodeId: string) => {
    if (expandedNodeIds.has(nodeId) || isExpanding) return;

    setIsExpanding(true);
    try {
      const res = await fetch(
        `/api/repos/${encodeURIComponent(repoName)}/knowledge-graph/expand/${encodeURIComponent(nodeId)}`
      );
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        console.error('[EXPAND] Failed:', errJson.detail || `HTTP ${res.status}`);
        return;
      }
      const data = await res.json();

      // Imperatively inject new nodes/edges into the shared mutable graph
      injectExpansionData(
        graphRef.current,
        nodeId,
        data.new_nodes || [],
        data.new_edges || [],
        isDark,
        activeRelFilters
      );

      setExpandedNodeIds((prev) => new Set([...prev, nodeId]));
      setGraphVersion((v) => v + 1);
    } catch (err: any) {
      console.error('[EXPAND] Error:', err);
    } finally {
      setIsExpanding(false);
    }
  }, [repoName, expandedNodeIds, isExpanding, isDark, activeRelFilters]);

  // ── 4. Fetch individual node details on click ──
  const handleSelectNode = useCallback(async (nodeId: string | null) => {
    if (!nodeId) {
      setSelectedNode(null);
      setNodeDetails(null);
      return;
    }

    // Get node data from the live graph
    const graph = graphRef.current;
    if (graph.hasNode(nodeId)) {
      const rawNode = graph.getNodeAttribute(nodeId, 'rawNode');
      setSelectedNode(rawNode || { id: nodeId, name: nodeId });
    } else {
      setSelectedNode({ id: nodeId, name: nodeId });
    }

    setIsLoadingDetails(true);
    try {
      // Directory nodes don't have a fact store entry — skip detail fetch
      if (nodeId.startsWith('dir:')) {
        setNodeDetails(null);
        return;
      }
      const res = await fetch(`/api/repos/${encodeURIComponent(repoName)}/knowledge-graph/node/${encodeURIComponent(nodeId)}`);
      if (res.ok) {
        const details = await res.json();
        setNodeDetails(details);
      } else {
        setNodeDetails(null);
      }
    } catch {
      setNodeDetails(null);
    } finally {
      setIsLoadingDetails(false);
    }
  }, [repoName]);

  // ── 5. View mode switcher ──
  const handleViewChange = (newView: string) => {
    setCurrentView(newView);
    setSelectedNode(null);
    setNodeDetails(null);
    setFocusNodeId(null);
    fetchFullGraph(newView);
  };

  // ── 6. Search ──
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setFocusNodeId(null);
      return;
    }

    const query = searchQuery.trim().toLowerCase();
    const graph = graphRef.current;
    let matchedId: string | null = null;
    if (graph) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      graph.forEachNode((id: string, attr: any) => {
        if (!matchedId) {
          const label = (attr.label || '').toLowerCase();
          const rawNode = attr.rawNode || {};
          if (
            label.includes(query) ||
            (rawNode.file || '').toLowerCase().includes(query) ||
            (rawNode.full_name || '').toLowerCase().includes(query) ||
            id.toLowerCase().includes(query)
          ) {
            matchedId = id;
          }
        }
      });
    }

    if (matchedId) {
      setFocusNodeId(matchedId);
      handleSelectNode(matchedId);
    }
  };

  // ── 7. Toggle relationship filter ──
  const toggleRelFilter = (relType: string) => {
    setActiveRelFilters((prev) => {
      const next = new Set(prev);
      if (next.has(relType)) next.delete(relType);
      else next.add(relType);
      return next;
    });
  };

  // Derive edge counts from live graph for filter chips
  const edgeCounts: Record<string, number> = {};
  if (graphRef.current) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    graphRef.current.forEachEdge((_: string, attr: any) => {
      const rt = attr.relType || 'GENERIC';
      edgeCounts[rt] = (edgeCounts[rt] || 0) + 1;
    });
  }
  const nodeCount = graphRef.current?.order ?? 0;
  const edgeCount = graphRef.current?.size ?? 0;

  const selectedNodeType = selectedNode?.type?.toUpperCase() || '';
  const isSelectedExpandable = selectedNode &&
    graphRef.current?.hasNode(selectedNode.id) &&
    graphRef.current?.getNodeAttribute(selectedNode.id, 'expandable');

  return (
    <div className="w-full h-full flex flex-col bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-100 overflow-hidden font-sans transition-colors duration-200">
      {/* ── TOP CONTROLS & HEADER BAR ── */}
      <div className="flex-shrink-0 border-b border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-950/80 backdrop-blur-md px-5 py-3.5 z-10 transition-colors">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Title & Stats Summary */}
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-blue-500/10 dark:bg-blue-600/20 border border-blue-400/20 dark:border-blue-500/30 text-blue-600 dark:text-blue-400">
              <Share2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-slate-900 dark:text-slate-100 tracking-tight">Repository Knowledge Graph</h1>
                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20 font-mono">
                  {repoName}
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Layer 4 Fact Store semantic relationships, call hierarchies, and architectural links
              </p>
            </div>
          </div>

          {/* View mode tabs & Search */}
          <div className="flex items-center gap-3">
            {/* View filter tabs */}
            <div className="flex items-center bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg p-1 text-xs">
              {[
                { id: 'all', label: 'All', icon: Globe },
                { id: 'calls', label: 'Calls', icon: Zap },
                { id: 'imports', label: 'Imports', icon: Box },
                { id: 'routes', label: 'Routes', icon: Route },
                { id: 'capabilities', label: 'Capabilities', icon: Sparkles },
                { id: 'structure', label: 'Structure', icon: Layers },
              ].map((v) => {
                const Icon = v.icon;
                const isActive = currentView === v.id;
                return (
                  <button
                    key={v.id}
                    onClick={() => handleViewChange(v.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-sm'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-200/60 dark:hover:bg-slate-800'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {v.label}
                  </button>
                );
              })}
            </div>

            {/* Search Input Bar */}
            <div className="flex items-center gap-2">
              <form onSubmit={handleSearchSubmit} className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    const val = e.target.value;
                    setSearchQuery(val);
                    if (!val.trim()) {
                      setFocusNodeId(null);
                    }
                  }}
                  placeholder="Search symbol or file..."
                  className="pl-8 pr-7 py-1.5 text-xs bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg text-slate-800 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-blue-500 w-48 md:w-64 transition-colors"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchQuery('');
                      setFocusNodeId(null);
                    }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                    title="Clear search"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </form>
            </div>
          </div>
        </div>

        {/* Filter Pills & Metric Counters */}
        <div className="flex flex-wrap items-center gap-2 mt-3 pt-2.5 border-t border-slate-200 dark:border-slate-800/80 text-xs">
          <span className="text-slate-500 dark:text-slate-400 font-medium text-[11px] uppercase tracking-wider mr-1">
            Graph:
          </span>

          <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-mono text-[11px]">
            {nodeCount} nodes
          </span>
          <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-mono text-[11px]">
            {edgeCount} edges
          </span>

          {overviewStats && (
            <>
              <span className="h-3 w-[1px] bg-slate-200 dark:bg-slate-700 mx-1" />
              <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 font-mono text-[11px]">
                {overviewStats.total_files || overviewStats.raw_total_files || 0} files total
              </span>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 font-mono text-[11px]">
                {overviewStats.total_symbols || overviewStats.raw_total_symbols || 0} symbols total
              </span>
            </>
          )}

          {isExpanding && (
            <>
              <span className="h-3 w-[1px] bg-slate-200 dark:bg-slate-700 mx-1" />
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-orange-100 dark:bg-orange-500/20 text-orange-700 dark:text-orange-300 font-mono text-[11px]">
                <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
                Expanding...
              </span>
            </>
          )}

          {Object.keys(edgeCounts).length > 0 && (
            <>
              <span className="h-3 w-[1px] bg-slate-200 dark:bg-slate-700 mx-1" />
              {/* Relationship Type Filter Chips */}
              {Object.entries(edgeCounts).map(([relType, count]) => {
                const isFiltered = activeRelFilters.has(relType);
                const color = edgeColorMap[relType] || '#94a3b8';
                return (
                  <button
                    key={relType}
                    onClick={() => toggleRelFilter(relType)}
                    className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono border transition-all ${
                      isFiltered
                        ? 'bg-blue-100 dark:bg-blue-950/80 text-blue-700 dark:text-blue-300 border-blue-400 dark:border-blue-500 shadow-sm'
                        : 'bg-white dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 hover:text-slate-900 dark:hover:text-slate-300'
                    }`}
                    title={`Filter edges of type ${relType}`}
                  >
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                    <span>{relType}</span>
                    <span className="text-[10px] opacity-70">({count})</span>
                  </button>
                );
              })}
            </>
          )}
        </div>
      </div>

      {/* ── CANVAS & INSPECTOR CONTAINER ── */}
      <div className="flex-grow flex relative overflow-hidden">
        {/* Sigma WebGL Canvas Area */}
        <div className="flex-grow h-full w-full relative bg-slate-50 dark:bg-slate-950 transition-colors">
          {isLoading && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-sm gap-3">
              <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">
                Extracting Fact Store Knowledge Graph...
              </p>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center p-6 text-center">
              <div className="p-3 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-500 dark:text-red-400 mb-3">
                <Info className="w-8 h-8" />
              </div>
              <h2 className="text-base font-semibold text-slate-800 dark:text-slate-200 mb-1">Knowledge Graph Unavailable</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mb-4">{error}</p>
              <button
                onClick={() => fetchFullGraph()}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
              >
                Retry
              </button>
            </div>
          )}

          <SigmaKnowledgeGraphCanvas
            key={sigmaKey}
            graphRef={graphRef}
            graphVersion={graphVersion}
            selectedNodeId={selectedNode ? selectedNode.id : null}
            onSelectNode={handleSelectNode}
            onExpandNode={handleExpandNode}
            activeRelFilters={activeRelFilters}
            focusNodeId={focusNodeId}
            searchQuery={searchQuery}
          />
        </div>

        {/* ── NODE INSPECTION SIDEBAR DRAWER ── */}
        {selectedNode && (
          <div className="w-80 md:w-96 flex-shrink-0 border-l border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md flex flex-col h-full shadow-2xl z-20 transition-colors">
            {/* Header */}
            <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-lg">
                  {typeBadgeStyles[selectedNodeType]?.icon || '📌'}
                </span>
                <div>
                  <h3 className="text-xs font-bold text-slate-900 dark:text-slate-100 truncate max-w-[200px]" title={selectedNode.name}>
                    {selectedNode.name}
                  </h3>
                  <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase">
                    {selectedNode.type}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1">
                {/* Expand button for expandable nodes */}
                {isSelectedExpandable && (
                  <button
                    onClick={() => handleExpandNode(selectedNode.id)}
                    disabled={isExpanding || expandedNodeIds.has(selectedNode.id)}
                    className="px-2 py-1 rounded bg-orange-50 dark:bg-orange-600/20 hover:bg-orange-100 dark:hover:bg-orange-600/30 text-orange-600 dark:text-orange-400 border border-orange-200 dark:border-orange-500/30 text-[11px] font-medium flex items-center gap-1 transition-colors disabled:opacity-50"
                    title="Expand this node to see its children"
                  >
                    <ChevronRight className="w-3 h-3" /> Expand
                  </button>
                )}
                <button
                  onClick={() => setSelectedNode(null)}
                  className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Details Content */}
            <div className="flex-grow overflow-y-auto p-4 space-y-4 text-xs">
              {/* Directory node: show folder info */}
              {selectedNodeType === 'DIRECTORY' && (
                <div className="p-2.5 rounded-lg bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-500/20">
                  <div className="text-[10px] uppercase font-semibold text-orange-600 dark:text-orange-400 mb-1">Directory</div>
                  <div className="font-mono text-[11px] text-slate-700 dark:text-slate-300">{selectedNode.full_name || selectedNode.name}/</div>
                  {selectedNode.file_count !== undefined && (
                    <div className="text-[10px] text-slate-500 mt-1">
                      {selectedNode.file_count} files · {selectedNode.symbol_count || 0} symbols
                    </div>
                  )}
                  <div className="mt-2 text-[10px] text-orange-600 dark:text-orange-400 font-medium">
                    {expandedNodeIds.has(selectedNode.id)
                      ? '✓ Expanded — children visible in graph'
                      : 'Double-click or press Expand to see contents'}
                  </div>
                </div>
              )}

              {/* Location info (for file/symbol nodes) */}
              {selectedNode.file && selectedNodeType !== 'DIRECTORY' && (
                <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800/80">
                  <div className="text-[10px] uppercase font-semibold text-slate-500 mb-1">Declared In</div>
                  <div className="font-mono text-[11px] text-slate-700 dark:text-slate-300 break-all">{selectedNode.file}</div>
                  {selectedNode.line_start && (
                    <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">
                      Lines {selectedNode.line_start} – {selectedNode.line_end || selectedNode.line_start}
                    </div>
                  )}
                </div>
              )}

              {/* In & Out degree badges */}
              {selectedNodeType !== 'DIRECTORY' && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800/80 text-center">
                    <div className="text-[10px] uppercase text-slate-500 font-semibold">Incoming Links</div>
                    <div className="text-base font-bold font-mono text-emerald-600 dark:text-emerald-400">
                      {nodeDetails?.incoming?.length ?? selectedNode.in_degree ?? 0}
                    </div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800/80 text-center">
                    <div className="text-[10px] uppercase text-slate-500 font-semibold">Outgoing Links</div>
                    <div className="text-base font-bold font-mono text-blue-600 dark:text-blue-400">
                      {nodeDetails?.outgoing?.length ?? selectedNode.out_degree ?? 0}
                    </div>
                  </div>
                </div>
              )}

              {isLoadingDetails && (
                <div className="flex items-center justify-center py-4 text-slate-500 text-xs">
                  <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mr-2" />
                  Resolving relationships...
                </div>
              )}

              {/* Incoming Connections */}
              {nodeDetails?.incoming?.length > 0 && (
                <div>
                  <h4 className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400" />
                    Called / Referenced By ({nodeDetails.incoming.length})
                  </h4>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto">
                    {nodeDetails.incoming.map((inc: any) => (
                      <div
                        key={inc.id}
                        onClick={() => {
                          handleSelectNode(inc.source.id);
                          setFocusNodeId(inc.source.id);
                        }}
                        className="p-2 rounded-lg bg-slate-50 dark:bg-slate-950/40 border border-slate-200 dark:border-slate-800/70 hover:border-emerald-500/50 hover:bg-slate-100 dark:hover:bg-slate-800/50 cursor-pointer transition-colors"
                      >
                        <div className="flex items-center justify-between gap-1">
                          <span className="font-mono text-xs text-slate-800 dark:text-slate-200 truncate">{inc.source.name}</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-emerald-700 dark:text-emerald-400">
                            {inc.rel_type}
                          </span>
                        </div>
                        {inc.source.file && (
                          <div className="text-[10px] text-slate-500 truncate mt-0.5">{inc.source.file}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Outgoing Connections */}
              {nodeDetails?.outgoing?.length > 0 && (
                <div>
                  <h4 className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500 dark:bg-blue-400" />
                    Calls / Imports ({nodeDetails.outgoing.length})
                  </h4>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto">
                    {nodeDetails.outgoing.map((outg: any) => (
                      <div
                        key={outg.id}
                        onClick={() => {
                          handleSelectNode(outg.target.id);
                          setFocusNodeId(outg.target.id);
                        }}
                        className="p-2 rounded-lg bg-slate-50 dark:bg-slate-950/40 border border-slate-200 dark:border-slate-800/70 hover:border-blue-500/50 hover:bg-slate-100 dark:hover:bg-slate-800/50 cursor-pointer transition-colors"
                      >
                        <div className="flex items-center justify-between gap-1">
                          <span className="font-mono text-xs text-slate-800 dark:text-slate-200 truncate">{outg.target.name}</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-blue-700 dark:text-blue-400">
                            {outg.rel_type}
                          </span>
                        </div>
                        {outg.target.file && (
                          <div className="text-[10px] text-slate-500 truncate mt-0.5">{outg.target.file}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Capabilities */}
              {nodeDetails?.capabilities?.length > 0 && (
                <div>
                  <h4 className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-rose-500 dark:text-rose-400" />
                    Capabilities ({nodeDetails.capabilities.length})
                  </h4>
                  <div className="space-y-1.5">
                    {nodeDetails.capabilities.map((cap: any) => (
                      <div key={cap.id} className="p-2 rounded-lg bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-500/20">
                        <div className="font-semibold text-rose-700 dark:text-rose-300">{cap.name}</div>
                        {cap.summary && <div className="text-[10px] text-slate-600 dark:text-slate-400 mt-1">{cap.summary}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
