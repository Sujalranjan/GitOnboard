"use client";

import React, { useState, useEffect, useCallback, useRef, useMemo, memo } from 'react';
import ReactFlow, {
  Controls,
  ControlButton,
  Background,
  applyNodeChanges,
  applyEdgeChanges,
  MarkerType,
  Panel,
  Handle,
  Position,
  BaseEdge,
  getBezierPath,
  EdgeLabelRenderer,
  MiniMap
} from 'reactflow';
import 'reactflow/dist/style.css';
import { layoutGraph, applyLocalRelaxation } from '@/utils/layout';
import { buildVFS, buildNodePathMap, calculateVisualComplexity, getAutoExpandedPaths } from '@/utils/vfs';
import { buildVisibleGraph } from '@/utils/graphBuilder';

import { PythonIcon, JavascriptIcon, TypescriptIcon, ReactIcon, JavaIcon } from './common/LanguageIcons';

// Language configuration map with curated colors & icons
const getLanguageConfig = (lang) => {
  const normalized = (lang || '').toLowerCase();
  switch (normalized) {
    case 'python':
      return { label: 'Python', color: '#6366f1', Icon: PythonIcon };
    case 'javascript':
    case 'js':
      return { label: 'JavaScript', color: '#d97706', Icon: JavascriptIcon };
    case 'typescript':
    case 'ts':
      return { label: 'TypeScript', color: '#2563eb', Icon: TypescriptIcon };
    case 'react':
    case 'jsx':
    case 'tsx':
      return { label: 'React', color: '#0891b2', Icon: ReactIcon };
    case 'java':
      return { label: 'Java', color: '#dc2626', Icon: JavaIcon };
    case 'go':
    case 'golang':
      return { label: 'Go', color: '#0d9488', Icon: null };
    default:
      return { label: lang || 'File', color: '#64748b', Icon: null };
  }
};

// Sleek Custom Node for Files
const CustomNode = memo(({ data, selected }) => {
  const config = getLanguageConfig(data.language);
  const Icon = config.Icon;
  const isDimmed = data.isDimmed;
  const role = data.highlightRole; // 'inbound' | 'outbound' | 'selected' | null

  // Dynamic border & shadow based on selection / highlight state
  let borderStyle = `2px solid ${config.color}`;
  let shadowStyle = '0 4px 12px -2px rgba(0, 0, 0, 0.08)';
  let bgStyle = '#ffffff';

  if (selected || role === 'selected') {
    borderStyle = `2px solid ${config.color}`;
    shadowStyle = `0 0 0 4px ${config.color}33, 0 8px 20px -4px ${config.color}44`;
  } else if (role === 'inbound') {
    borderStyle = '2px solid #10b981'; // Emerald Green for inbound callers
    shadowStyle = '0 0 0 3px #10b98133, 0 6px 16px -2px #10b98144';
    bgStyle = '#f0fdf4';
  } else if (role === 'outbound') {
    borderStyle = '2px solid #8b5cf6'; // Violet/Purple for outbound dependencies
    shadowStyle = '0 0 0 3px #8b5cf633, 0 6px 16px -2px #8b5cf644';
    bgStyle = '#f5f3ff';
  }

  return (
    <div
      className={`transition-all duration-200 cursor-pointer select-none rounded-xl px-3.5 py-2 flex items-center gap-2.5 min-w-[150px] max-w-[250px] ${
        isDimmed ? 'opacity-25 filter blur-[0.3px]' : 'opacity-100'
      }`}
      style={{
        background: bgStyle,
        border: borderStyle,
        boxShadow: shadowStyle,
      }}
    >
      {/* Handles for both LR and TB flow */}
      <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
      <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
      <Handle type="target" position={Position.Top} id="top" style={{ visibility: 'hidden' }} />
      <Handle type="source" position={Position.Bottom} id="bottom" style={{ visibility: 'hidden' }} />

      {/* Language Icon */}
      <div 
        className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
        style={{ backgroundColor: `${config.color}15` }}
      >
        {Icon ? <Icon className="w-4 h-4" /> : <span className="text-xs font-bold" style={{ color: config.color }}>📄</span>}
      </div>

      {/* File Details */}
      <div className="flex flex-col min-w-0 flex-1">
        <div className="text-xs font-semibold text-gray-800 truncate" title={data.label}>
          {data.label}
        </div>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="text-[10px] font-medium px-1.5 py-0.2 rounded border bg-slate-50 text-slate-600 border-slate-200">
            {data.language || 'Code'}
          </span>
          {data.degreeInfo && (
            <span className="text-[9px] text-gray-400 font-mono">
              in:{data.degreeInfo.inbound} out:{data.degreeInfo.outbound}
            </span>
          )}
        </div>
      </div>
    </div>
  );
});

// Sleek Custom Node for Folders
const FolderNode = memo(({ data, selected }) => {
  const isDimmed = data.isDimmed;

  return (
    <div
      className={`transition-all duration-200 cursor-pointer select-none rounded-xl px-3.5 py-2.5 flex items-center gap-2.5 min-w-[170px] bg-slate-900/90 text-white backdrop-blur-md border border-slate-700/80 shadow-lg hover:border-indigo-400 ${
        selected ? 'ring-2 ring-indigo-500 shadow-indigo-500/20' : ''
      } ${isDimmed ? 'opacity-25' : 'opacity-100'}`}
    >
      <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
      <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
      <Handle type="target" position={Position.Top} id="top" style={{ visibility: 'hidden' }} />
      <Handle type="source" position={Position.Bottom} id="bottom" style={{ visibility: 'hidden' }} />

      <div className="w-7 h-7 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center shrink-0 font-bold text-sm">
        📁
      </div>

      <div className="flex flex-col min-w-0 flex-1">
        <div className="text-xs font-bold text-slate-100 truncate" title={data.label}>
          {data.label}
        </div>
        <div className="text-[10px] text-indigo-300 font-medium flex items-center gap-1 mt-0.5">
          <span>{data.descendants || 0} files inside</span>
          <span className="text-slate-400">• click to expand</span>
        </div>
      </div>
    </div>
  );
});

// Custom Edge for Aggregated Folder Imports
const AggregateEdge = memo(({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, style, markerEnd }) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={{ ...style, pointerEvents: 'none' }} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            background: '#ffffff',
            padding: '2px 8px',
            borderRadius: '10px',
            fontSize: '10px',
            fontWeight: 700,
            color: '#475569',
            border: '1px solid #cbd5e1',
            boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
        >
          {data.count} imports
        </div>
      </EdgeLabelRenderer>
    </>
  );
});

const nodeTypes = {
  custom: CustomNode,
  folderNode: FolderNode
};

const edgeTypes = {
  aggregateEdge: AggregateEdge
};

export default function DependencyGraph({ repoName }) {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Controls & Display Options
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [languageFilter, setLanguageFilter] = useState('ALL');
  const [layoutDirection, setLayoutDirection] = useState('LR'); // 'LR' or 'TB'
  const [showMinimap, setShowMinimap] = useState(true);
  const [showInspector, setShowInspector] = useState(true);

  // Architecture States
  const [vfsRoot, setVfsRoot] = useState(null);
  const [rawGraphData, setRawGraphData] = useState(null);
  const [expandedPaths, setExpandedPaths] = useState(new Set());

  const containerRef = useRef(null);
  const rfInstance = useRef(null);
  const expandAnchorIdRef = useRef(null);

  // History State for Undo/Redo
  const [history, setHistory] = useState([]);
  const [currentStep, setCurrentStep] = useState(-1);
  const isRestoringHistory = useRef(false);

  const saveHistory = useCallback((currentExpandedPaths, currentNodes) => {
    setHistory(prev => {
      const newHistory = prev.slice(0, currentStep + 1);
      const snapshot = {
        expandedPaths: new Set(currentExpandedPaths),
        nodes: currentNodes.map(n => ({...n, position: {...n.position}}))
      };
      return [...newHistory, snapshot];
    });
    setCurrentStep(prev => prev + 1);
  }, [currentStep]);

  // Fetch graph on mount or repoName change
  useEffect(() => {
    let isMounted = true;
    
    const fetchGraph = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/repos/${repoName}/dependencies`);
        if (!res.ok) {
          throw new Error("Failed to load dependency graph.");
        }
        const data = await res.json();
        if (!isMounted) return;

        const validNodes = data.nodes.filter(n => n.full_path);
        const root = buildVFS(validNodes);
        const nodePathMap = buildNodePathMap(validNodes);
        
        const nodeIds = new Set(validNodes.map(n => n.id));
        const validEdges = data.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));

        calculateVisualComplexity(root, validEdges, nodePathMap);
        const initialExpanded = getAutoExpandedPaths(root);

        setVfsRoot(root);
        setRawGraphData({ nodes: validNodes, edges: validEdges, nodePathMap });
        setExpandedPaths(initialExpanded);

      } catch (err) {
        if (isMounted) setError(err.message);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchGraph();
    
    return () => {
      isMounted = false;
    };
  }, [repoName]);

  // Rebuild graph layout when expansion or layout direction changes
  useEffect(() => {
    if (!vfsRoot || !rawGraphData) return;

    if (isRestoringHistory.current) {
      const { edges: newEdges } = buildVisibleGraph(
        vfsRoot, 
        rawGraphData.nodes, 
        rawGraphData.edges, 
        rawGraphData.nodePathMap, 
        expandedPaths,
        nodes 
      );
      setEdges(newEdges);
      isRestoringHistory.current = false;
      return;
    }

    const { nodes: newNodes, edges: newEdges } = buildVisibleGraph(
      vfsRoot, 
      rawGraphData.nodes, 
      rawGraphData.edges, 
      rawGraphData.nodePathMap, 
      expandedPaths,
      nodes
    );

    let positionedNodes = newNodes;

    if (expandAnchorIdRef.current) {
      positionedNodes = applyLocalRelaxation(positionedNodes, expandAnchorIdRef.current, true);
      expandAnchorIdRef.current = null;
    } else {
      positionedNodes = layoutGraph(positionedNodes, newEdges, { direction: layoutDirection });
    }

    setNodes(positionedNodes);
    setEdges(newEdges);

    saveHistory(expandedPaths, positionedNodes);

    if (nodes.length === 0) {
      setTimeout(() => {
        if (rfInstance.current) {
          rfInstance.current.fitView({ padding: 0.2, duration: 600 });
        }
      }, 100);
    }
  }, [vfsRoot, rawGraphData, expandedPaths, layoutDirection]);

  // Unique list of available languages for filtering
  const availableLanguages = useMemo(() => {
    if (!rawGraphData) return [];
    const langs = new Set(rawGraphData.nodes.map(n => n.language).filter(Boolean));
    return Array.from(langs);
  }, [rawGraphData]);

  // Degree calculation map for each node (inbound vs outbound count)
  const nodeDegrees = useMemo(() => {
    const map = new Map();
    if (!rawGraphData) return map;

    rawGraphData.nodes.forEach(n => map.set(n.id, { inbound: 0, outbound: 0 }));
    rawGraphData.edges.forEach(e => {
      if (map.has(e.source)) map.get(e.source).outbound += 1;
      if (map.has(e.target)) map.get(e.target).inbound += 1;
    });
    return map;
  }, [rawGraphData]);

  // Compute selected node details for Inspector
  const selectedNodeDetails = useMemo(() => {
    if (!selectedNodeId || !rawGraphData) return null;
    const rawNode = rawGraphData.nodes.find(n => n.id === selectedNodeId);
    if (!rawNode) return null;

    // Incoming files (files importing this selected file)
    const inboundEdges = rawGraphData.edges.filter(e => e.target === selectedNodeId);
    const inboundFiles = inboundEdges.map(e => rawGraphData.nodes.find(n => n.id === e.source)).filter(Boolean);

    // Outgoing files (files imported by this selected file)
    const outboundEdges = rawGraphData.edges.filter(e => e.source === selectedNodeId);
    const outboundFiles = outboundEdges.map(e => rawGraphData.nodes.find(n => n.id === e.target)).filter(Boolean);

    return {
      node: rawNode,
      inboundFiles,
      outboundFiles,
      degrees: nodeDegrees.get(selectedNodeId) || { inbound: 0, outbound: 0 }
    };
  }, [selectedNodeId, rawGraphData, nodeDegrees]);

  // Compute active node & edge visual states (highlighting & sub-graph dimming)
  const { renderedNodes, renderedEdges } = useMemo(() => {
    // 1. Identify highlighted nodes & edges when a node is selected
    const inboundSources = new Set();
    const outboundTargets = new Set();

    if (selectedNodeId && rawGraphData) {
      edges.forEach(e => {
        if (e.target === selectedNodeId) inboundSources.add(e.source);
        if (e.source === selectedNodeId) outboundTargets.add(e.target);
      });
    }

    // 2. Prepare nodes with roles and dimming
    const updatedNodes = nodes.map(n => {
      const degrees = nodeDegrees.get(n.id) || null;
      let role = null;
      let isDimmed = false;

      if (selectedNodeId) {
        if (n.id === selectedNodeId) {
          role = 'selected';
        } else if (inboundSources.has(n.id)) {
          role = 'inbound';
        } else if (outboundTargets.has(n.id)) {
          role = 'outbound';
        } else {
          isDimmed = true;
        }
      }

      // Language Filter check
      if (languageFilter !== 'ALL' && n.data?.language && n.data.language.toLowerCase() !== languageFilter.toLowerCase()) {
        isDimmed = true;
      }

      return {
        ...n,
        data: {
          ...n.data,
          degreeInfo: degrees,
          highlightRole: role,
          isDimmed: isDimmed
        }
      };
    });

    // 3. Prepare edges with color coding & animations
    const updatedEdges = edges.map(e => {
      const isSelected = selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId);
      const isInbound = selectedNodeId && e.target === selectedNodeId;
      const isOutbound = selectedNodeId && e.source === selectedNodeId;
      const isAggregate = e.type === 'aggregateEdge';

      let stroke = '#cbd5e1';
      let strokeWidth = isAggregate ? 2 : 1.5;
      let opacity = 0.4;
      let animated = false;

      if (selectedNodeId) {
        if (isInbound) {
          stroke = '#10b981'; // Emerald for inbound callers
          strokeWidth = 2.5;
          opacity = 1;
          animated = true;
        } else if (isOutbound) {
          stroke = '#8b5cf6'; // Violet for outbound dependencies
          strokeWidth = 2.5;
          opacity = 1;
          animated = true;
        } else {
          opacity = 0.05; // Subdue unrelated edges
        }
      }

      return {
        ...e,
        animated,
        style: { stroke, strokeWidth, opacity },
        markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 16, height: 16 },
        zIndex: isSelected ? 10 : 0
      };
    });

    return { renderedNodes: updatedNodes, renderedEdges: updatedEdges };
  }, [nodes, edges, selectedNodeId, rawGraphData, languageFilter, nodeDegrees]);

  const onNodesChangeHandler = useCallback(
    (changes) => {
      setNodes((nds) => {
        let updatedNodes = applyNodeChanges(changes, nds);
        const dragChange = changes.find(c => c.type === 'position' && c.dragging);
        if (dragChange) {
          updatedNodes = applyLocalRelaxation(updatedNodes, dragChange.id, false);
        }
        return updatedNodes;
      });
    },
    []
  );

  const onEdgesChangeHandler = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  const onNodeDragStop = useCallback(() => {
    saveHistory(expandedPaths, nodes);
  }, [expandedPaths, nodes, saveHistory]);

  const handleUndo = useCallback(() => {
    if (currentStep > 0) {
      const prevStep = currentStep - 1;
      const snapshot = history[prevStep];
      isRestoringHistory.current = true;
      setExpandedPaths(snapshot.expandedPaths);
      setNodes(snapshot.nodes);
      setCurrentStep(prevStep);
    }
  }, [currentStep, history]);

  const handleRedo = useCallback(() => {
    if (currentStep < history.length - 1) {
      const nextStep = currentStep + 1;
      const snapshot = history[nextStep];
      isRestoringHistory.current = true;
      setExpandedPaths(snapshot.expandedPaths);
      setNodes(snapshot.nodes);
      setCurrentStep(nextStep);
    }
  }, [currentStep, history]);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      if (containerRef.current) {
        containerRef.current.requestFullscreen().catch((err) => {
          console.error(`Fullscreen error: ${err.message}`);
        });
      }
    } else {
      document.exitFullscreen();
    }
  };

  const onNodeClick = useCallback((_, node) => {
    setSelectedNodeId(node.id);

    if (node.type === 'folderNode') {
      const path = node.data.path;
      setExpandedPaths(prev => {
        const next = new Set(prev);
        if (next.has(path)) {
          next.delete(path);
        } else {
          next.add(path);
          expandAnchorIdRef.current = node.id;
        }
        return next;
      });
    }
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    if (!searchQuery || !rawGraphData) return;

    const query = searchQuery.toLowerCase();
    const foundNode = rawGraphData.nodes.find(n => 
      n.full_path.toLowerCase().includes(query) || n.id.toLowerCase().includes(query)
    );

    if (foundNode) {
      const path = rawGraphData.nodePathMap.get(foundNode.id);
      if (path) {
        const parts = path.split('/');
        setExpandedPaths(prev => {
          const next = new Set(prev);
          let currentPath = '';
          for (let i = 0; i < parts.length - 1; i++) {
            currentPath = currentPath === '' ? parts[i] : `${currentPath}/${parts[i]}`;
            next.add(currentPath);
          }
          return next;
        });

        setTimeout(() => {
          if (rfInstance.current) {
            rfInstance.current.fitView({ nodes: [{ id: foundNode.id }], duration: 800, padding: 0.5 });
            setSelectedNodeId(foundNode.id);
          }
        }, 200);
      }
    }
  };

  const handleAutoOrganize = useCallback(() => {
    if (!nodes.length) return;
    const reorderedNodes = layoutGraph(nodes, edges, { direction: layoutDirection, forceReorder: true });
    setNodes(reorderedNodes);
    setTimeout(() => {
      if (rfInstance.current) {
        rfInstance.current.fitView({ padding: 0.25, duration: 800 });
      }
    }, 50);
  }, [nodes, edges, layoutDirection]);

  const focusOnNode = (nodeId) => {
    setSelectedNodeId(nodeId);
    if (rfInstance.current) {
      rfInstance.current.fitView({ nodes: [{ id: nodeId }], duration: 600, padding: 0.6 });
    }
  };

  if (isLoading) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center bg-slate-900 text-slate-300 gap-3">
        <div className="w-8 h-8 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
        <span className="text-sm font-medium">Building Virtual Dependency Graph...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-slate-900 text-rose-400 text-sm">
        ⚠️ {error}
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-slate-900 text-slate-400 text-sm">
        No supported dependency nodes found.
      </div>
    );
  }

  return (
    <div 
      ref={containerRef}
      className="w-full h-full bg-slate-950 rounded-xl border border-slate-800 overflow-hidden relative flex"
    >
      {/* Main Canvas Area */}
      <div className="flex-1 h-full relative">
        <ReactFlow
          nodes={renderedNodes}
          edges={renderedEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChangeHandler}
          onEdgesChange={onEdgesChangeHandler}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          onInit={(instance) => { rfInstance.current = instance; }}
          minZoom={0.05}
          maxZoom={2.5}
          nodesDraggable={true}
          onNodeDragStop={onNodeDragStop}
        >
          {/* Rich Canvas Grid Background */}
          <Background color="#334155" gap={24} size={1} />

          {/* Top Floating Glassmorphism Toolbar */}
          <Panel position="top-left" className="m-3 flex flex-wrap items-center gap-2.5 pointer-events-auto">
            {/* Search Box */}
            <form onSubmit={handleSearch} className="flex items-center bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-lg p-1.5 shadow-lg">
              <input 
                type="text" 
                placeholder="Search file in graph..." 
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="text-xs px-2.5 py-1 bg-transparent text-slate-100 placeholder-slate-400 outline-none w-48"
              />
              <button 
                type="submit" 
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1 rounded text-xs font-semibold transition"
              >
                Find
              </button>
            </form>

            {/* Layout Direction & Auto-Organize Switcher */}
            <div className="flex items-center bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-lg p-1 shadow-lg gap-1">
              <button
                onClick={() => setLayoutDirection('LR')}
                className={`text-xs px-2.5 py-1 rounded font-medium transition ${
                  layoutDirection === 'LR' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Horizontal Flow"
              >
                ➔ LR
              </button>
              <button
                onClick={() => setLayoutDirection('TB')}
                className={`text-xs px-2.5 py-1 rounded font-medium transition ${
                  layoutDirection === 'TB' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Vertical Flow"
              >
                ⬇ TB
              </button>
              <button
                onClick={handleAutoOrganize}
                className="text-xs px-3 py-1 rounded font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1 shadow-md shadow-emerald-600/20"
                title="Auto-organize nodes into clean hierarchical layout"
              >
                ⚡ Auto-Organize
              </button>
            </div>

            {/* Language Filter Chips */}
            <div className="flex items-center bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-lg p-1 shadow-lg gap-1 max-w-[320px] overflow-x-auto">
              <button
                onClick={() => setLanguageFilter('ALL')}
                className={`text-[11px] px-2 py-0.5 rounded font-medium transition ${
                  languageFilter === 'ALL' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                All ({rawGraphData?.nodes.length || 0})
              </button>
              {availableLanguages.map(lang => (
                <button
                  key={lang}
                  onClick={() => setLanguageFilter(lang)}
                  className={`text-[11px] px-2 py-0.5 rounded font-medium transition ${
                    languageFilter === lang ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {lang}
                </button>
              ))}
            </div>

            {/* Minimap & Inspector Toggles */}
            <div className="flex items-center bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-lg p-1 shadow-lg gap-1">
              <button
                onClick={() => setShowMinimap(!showMinimap)}
                className={`text-xs px-2 py-1 rounded font-medium transition ${
                  showMinimap ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Toggle MiniMap"
              >
                🗺 Map
              </button>
              <button
                onClick={() => setShowInspector(!showInspector)}
                className={`text-xs px-2 py-1 rounded font-medium transition ${
                  showInspector ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Toggle Inspector Sidebar"
              >
                ℹ Inspector
              </button>
            </div>
          </Panel>

          {/* Interactive Legend Bar at Bottom Left */}
          <Panel position="bottom-left" className="m-3 bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-lg p-2 text-[11px] text-slate-300 flex items-center gap-4 shadow-lg pointer-events-auto">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
              <span>Inbound (Importers)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-violet-500"></span>
              <span>Outbound (Dependencies)</span>
            </div>
            <div className="text-slate-500">|</div>
            <div className="text-slate-400">
              Click node to trace imports & dependencies
            </div>
          </Panel>

          {/* Custom Controls in Bottom Right */}
          <Controls showInteractive={false} showFitView={true} position="bottom-right">
            <ControlButton onClick={handleUndo} disabled={currentStep <= 0} title="Undo">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '14px', height: '14px', opacity: currentStep <= 0 ? 0.3 : 1 }}>
                <path d="M3 7v6h6" />
                <path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13" />
              </svg>
            </ControlButton>
            <ControlButton onClick={handleRedo} disabled={currentStep >= history.length - 1} title="Redo">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '14px', height: '14px', opacity: currentStep >= history.length - 1 ? 0.3 : 1 }}>
                <path d="M21 7v6h-6" />
                <path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3l3 2.7" />
              </svg>
            </ControlButton>
            <ControlButton onClick={toggleFullscreen} title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}>
              {isFullscreen ? (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '14px', height: '14px' }}>
                  <path d="M4 14h6v6" />
                  <path d="M20 10h-6V4" />
                  <path d="M14 10l7-7" />
                  <path d="M3 21l7-7" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '14px', height: '14px' }}>
                  <path d="M15 3h6v6" />
                  <path d="M9 21H3v-6" />
                  <path d="M21 3l-7 7" />
                  <path d="M3 21l7-7" />
                </svg>
              )}
            </ControlButton>
          </Controls>

          {/* MiniMap */}
          {showMinimap && (
            <MiniMap
              position="bottom-right"
              style={{ bottom: 50, right: 10 }}
              nodeColor={(node) => {
                if (node.type === 'folderNode') return '#475569';
                const langConfig = getLanguageConfig(node.data?.language);
                return langConfig.color || '#94a3b8';
              }}
              maskColor="rgba(15, 23, 42, 0.7)"
              className="border border-slate-700 rounded-lg overflow-hidden"
            />
          )}
        </ReactFlow>
      </div>

      {/* Node Inspector Side Sidebar */}
      {showInspector && selectedNodeDetails && (
        <div className="w-80 h-full bg-slate-900 border-l border-slate-800 p-4 flex flex-col gap-4 overflow-y-auto shrink-0 shadow-2xl z-20 animate-in slide-in-from-right duration-200">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-base">📄</span>
              <div className="truncate font-semibold text-sm text-slate-100" title={selectedNodeDetails.node.label}>
                {selectedNodeDetails.node.label}
              </div>
            </div>
            <button 
              onClick={() => setSelectedNodeId(null)}
              className="text-slate-400 hover:text-slate-200 text-xs px-2 py-1 rounded bg-slate-800"
            >
              ✕
            </button>
          </div>

          {/* File Path & Language */}
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">File Path</span>
            <div className="text-xs font-mono bg-slate-950 text-slate-300 p-2 rounded border border-slate-800 break-all">
              {selectedNodeDetails.node.full_path}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs text-slate-400">Language:</span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                {selectedNodeDetails.node.language || 'Unknown'}
              </span>
            </div>
          </div>

          {/* Metrics summary */}
          <div className="grid grid-cols-2 gap-2 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800">
            <div className="flex flex-col">
              <span className="text-[10px] text-slate-400">Inbound Importers</span>
              <span className="text-lg font-bold text-emerald-400">{selectedNodeDetails.degrees.inbound}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] text-slate-400">Outbound Imports</span>
              <span className="text-lg font-bold text-violet-400">{selectedNodeDetails.degrees.outbound}</span>
            </div>
          </div>

          {/* Quick Focus Button */}
          <button
            onClick={() => focusOnNode(selectedNodeDetails.node.id)}
            className="w-full bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold py-2 rounded-lg transition flex items-center justify-center gap-1.5 shadow-md shadow-indigo-600/20"
          >
            🎯 Center View on Node
          </button>

          {/* Inbound Importers List */}
          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
              <span>📥 Imported By</span>
              <span className="text-[10px] text-slate-500">({selectedNodeDetails.inboundFiles.length})</span>
            </span>
            {selectedNodeDetails.inboundFiles.length === 0 ? (
              <div className="text-xs text-slate-500 italic px-1">No files import this module directly.</div>
            ) : (
              <div className="flex flex-col gap-1.5 max-h-40 overflow-y-auto pr-1">
                {selectedNodeDetails.inboundFiles.map(file => (
                  <div 
                    key={file.id}
                    onClick={() => focusOnNode(file.id)}
                    className="p-2 rounded bg-slate-950 hover:bg-slate-800 border border-slate-800/80 cursor-pointer transition flex items-center justify-between text-xs group"
                  >
                    <span className="text-slate-200 group-hover:text-emerald-300 font-mono text-[11px] truncate" title={file.full_path}>
                      {file.label}
                    </span>
                    <span className="text-[10px] text-slate-500 shrink-0">➔</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Outbound Imports List */}
          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold text-violet-400 uppercase tracking-wider flex items-center gap-1">
              <span>📤 Imports Dependencies</span>
              <span className="text-[10px] text-slate-500">({selectedNodeDetails.outboundFiles.length})</span>
            </span>
            {selectedNodeDetails.outboundFiles.length === 0 ? (
              <div className="text-xs text-slate-500 italic px-1">This module imports no local dependencies.</div>
            ) : (
              <div className="flex flex-col gap-1.5 max-h-40 overflow-y-auto pr-1">
                {selectedNodeDetails.outboundFiles.map(file => (
                  <div 
                    key={file.id}
                    onClick={() => focusOnNode(file.id)}
                    className="p-2 rounded bg-slate-950 hover:bg-slate-800 border border-slate-800/80 cursor-pointer transition flex items-center justify-between text-xs group"
                  >
                    <span className="text-slate-200 group-hover:text-violet-300 font-mono text-[11px] truncate" title={file.full_path}>
                      {file.label}
                    </span>
                    <span className="text-[10px] text-slate-500 shrink-0">➔</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
