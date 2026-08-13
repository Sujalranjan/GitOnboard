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
  EdgeLabelRenderer
} from 'reactflow';
import 'reactflow/dist/style.css';
import { layoutGraph, applyLocalRelaxation } from '@/utils/layout';
import { buildVFS, buildNodePathMap, calculateVisualComplexity, getAutoExpandedPaths } from '@/utils/vfs';
import { buildVisibleGraph } from '@/utils/graphBuilder';

import { PythonIcon, JavascriptIcon, TypescriptIcon, ReactIcon, JavaIcon } from './common/LanguageIcons';

const getLanguageConfig = (lang) => {
  switch (lang) {
    case 'Python': return { color: '#6366f1', Icon: PythonIcon };
    case 'JavaScript': return { color: '#eab308', Icon: JavascriptIcon };
    case 'TypeScript': return { color: '#2563eb', Icon: TypescriptIcon };
    case 'React': return { color: '#06b6d4', Icon: ReactIcon };
    case 'Java': return { color: '#ef4444', Icon: JavaIcon };
    default: return { color: '#9ca3af', Icon: null };
  }
};

// Custom Node for Files
const CustomNode = memo(({ data }) => {
  const config = getLanguageConfig(data.language);
  const Icon = config.Icon;
  
  return (
    <div style={{
      background: '#ffffff',
      border: `2px solid ${config.color}`,
      borderRadius: '24px',
      padding: '8px 16px',
      fontSize: '12px',
      fontWeight: '600',
      color: '#374151',
      fontFamily: 'sans-serif',
      boxShadow: '0 2px 4px -1px rgb(0 0 0 / 0.1)',
      minWidth: '50px',
      textAlign: 'center',
      display: 'flex',
      alignItems: 'center',
      gap: '6px'
    }}>
      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden', top: '50%' }} />
      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden', top: '50%' }} />
      {Icon && <Icon style={{ width: '14px', height: '14px' }} />}
      {data.label}
    </div>
  );
});

// Custom Node for Folders
const FolderNode = memo(({ data }) => (
  <div style={{
    background: '#f8fafc',
    border: '2px dashed #94a3b8',
    borderRadius: '8px',
    padding: '12px 20px',
    fontSize: '13px',
    fontWeight: '700',
    color: '#475569',
    fontFamily: 'sans-serif',
    boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)',
    minWidth: '80px',
    textAlign: 'center',
    cursor: 'pointer'
  }}>
    <Handle type="target" position={Position.Top} style={{ visibility: 'hidden', top: '50%' }} />
    <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden', top: '50%' }} />
    📁 {data.label} <span style={{fontSize: '10px', color: '#94a3b8', marginLeft: '4px'}}>({data.descendants})</span>
  </div>
));

// Custom Edge for Aggregates
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
            padding: '2px 6px',
            borderRadius: '12px',
            fontSize: '9px',
            fontWeight: 700,
            color: '#64748b',
            border: '1px solid #e2e8f0',
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

let renderCount = 0;

export default function DependencyGraph({ repoName }) {
  renderCount++;
  console.log(`[Profiler] DependencyGraph rendered. Total renders: ${renderCount}`);

  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Custom Control States
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  
  // Architecture States
  const [vfsRoot, setVfsRoot] = useState(null);
  const [rawGraphData, setRawGraphData] = useState(null);
  const [expandedPaths, setExpandedPaths] = useState(new Set());
  
  const containerRef = useRef(null);
  const rfInstance = useRef(null);
  const expandAnchorIdRef = useRef(null);
  
  // History State
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
        
        // Ensure nodes have full_path
        const validNodes = data.nodes.filter(n => n.full_path);
        
        // Build VFS
        const root = buildVFS(validNodes);
        const nodePathMap = buildNodePathMap(validNodes);
        
        // Filter edges where both source and target exist
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

  // Re-build visible graph when expansion state changes
  useEffect(() => {
    if (!vfsRoot || !rawGraphData) return;
    
    if (isRestoringHistory.current) {
      // Skip layout algorithms when restoring history, just rebuild edges
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
      nodes // pass existing nodes to preserve positions
    );
    
    let positionedNodes = newNodes;
    
    // If we have an anchor, this was a manual expansion
    if (expandAnchorIdRef.current) {
      positionedNodes = applyLocalRelaxation(positionedNodes, expandAnchorIdRef.current, true);
      expandAnchorIdRef.current = null;
    } else {
      // Global layout for initial load or search (only moves unpositioned/new nodes)
      positionedNodes = layoutGraph(positionedNodes, newEdges, { direction: 'LR' });
    }
    
    setNodes(positionedNodes);
    setEdges(newEdges);
    
    // Save history after a structural layout change
    saveHistory(expandedPaths, positionedNodes);
    
    // Center view only on initial load
    if (nodes.length === 0) {
      setTimeout(() => {
        if (rfInstance.current) {
          rfInstance.current.fitView({ padding: 0.2, duration: 800 });
        }
      }, 100);
    }
  }, [vfsRoot, rawGraphData, expandedPaths]);

  const onNodesChange = useCallback(
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
  
  const onEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  const onNodeDragStop = useCallback(() => {
    // Save history after dragging
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
          console.error(`Error attempting to enable fullscreen mode: ${err.message}`);
        });
      }
    } else {
      document.exitFullscreen();
    }
  };

  const onNodeClick = useCallback((_, node) => {
    setSelectedNode(node.id);
    
    // Handle Folder Expansion/Collapse
    if (node.type === 'folderNode') {
      const path = node.data.path;
      
      setExpandedPaths(prev => {
        const next = new Set(prev);
        if (next.has(path)) {
          next.delete(path);
          // When collapsing, we don't need a click coordinate because nodes are disappearing
        } else {
          next.add(path);
          // Store ID so the local layout spawns children here and anchors the parent
          expandAnchorIdRef.current = node.id;
        }
        return next;
      });
    }
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  // Compute styles dynamically for selection effects
  const renderedEdges = useMemo(() => {
    return edges.map(e => {
      const isSelectedNodeConnected = selectedNode && (e.source === selectedNode || e.target === selectedNode);
      
      const isAggregate = e.type === 'aggregateEdge';
      
      let stroke = '#cbd5e1';
      let opacity = 0.15;
      let strokeWidth = isAggregate ? 2 : 1;
      
      if (selectedNode) {
        if (isSelectedNodeConnected) {
          stroke = '#6366f1';
          opacity = 1;
          strokeWidth = isAggregate ? 3 : 2;
        } else {
          opacity = 0.05; // heavily subdue unrelated edges
        }
      } else {
        // Default unselected state
        opacity = 0.4;
      }
      
      return {
        ...e,
        style: { stroke, strokeWidth, opacity },
        animated: isSelectedNodeConnected && !isAggregate,
        markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 20, height: 20 },
        zIndex: isSelectedNodeConnected ? 10 : 0
      };
    });
  }, [edges, selectedNode]);

  const handleSearch = (e) => {
    e.preventDefault();
    if (!searchQuery || !rawGraphData) return;
    
    const query = searchQuery.toLowerCase();
    
    // Find file in raw nodes
    const foundNode = rawGraphData.nodes.find(n => 
      n.full_path.toLowerCase().includes(query) || n.id.toLowerCase().includes(query)
    );
    
    if (foundNode) {
      // Find its path and expand all ancestors
      const path = rawGraphData.nodePathMap.get(foundNode.id);
      if (path) {
        const parts = path.split('/');
        setExpandedPaths(prev => {
          const next = new Set(prev);
          let currentPath = '';
          // We don't expand the file itself, just its parent folders
          for (let i = 0; i < parts.length - 1; i++) {
            currentPath = currentPath === '' ? parts[i] : `${currentPath}/${parts[i]}`;
            next.add(currentPath);
          }
          return next;
        });
        
        // Wait for render, then center
        setTimeout(() => {
          if (rfInstance.current) {
            rfInstance.current.fitView({ nodes: [{ id: foundNode.id }], duration: 800, padding: 0.5 });
            setSelectedNode(foundNode.id);
          }
        }, 200);
      }
    }
  };

  if (isLoading) {
    return <div className="h-full flex items-center justify-center text-gray-500 dark:text-slate-400">Building Virtual File System...</div>;
  }

  if (error) {
    return <div className="h-full flex items-center justify-center text-red-500 dark:text-red-400">{error}</div>;
  }

  if (nodes.length === 0) {
    return <div className="h-full flex items-center justify-center text-gray-400 dark:text-slate-500">No supported source files found to analyze.</div>;
  }

  return (
    <div 
      ref={containerRef}
      className="w-full h-full bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-800 overflow-hidden relative"
    >
      <ReactFlow
        nodes={nodes}
        edges={renderedEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        onInit={(instance) => { rfInstance.current = instance; }}
        minZoom={0.05}
        maxZoom={2.5}
        nodesDraggable={true}
        onNodeDragStop={onNodeDragStop}
      >
        <Background color="#94a3b8" gap={20} size={1} />
        
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
        
        <Panel position="top-left" className="bg-white/90 dark:bg-slate-800/90 shadow-sm border border-gray-100 dark:border-slate-700 p-2 rounded-lg flex flex-col pointer-events-auto">
          <form onSubmit={handleSearch} className="flex gap-2">
            <input 
              type="text" 
              placeholder="Search file..." 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="text-xs px-2 py-1 border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 rounded outline-none focus:border-indigo-500 w-48"
            />
            <button type="submit" className="bg-indigo-50 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-300 px-2 py-1 rounded text-xs font-semibold hover:bg-indigo-100 dark:hover:bg-indigo-900/80">Find</button>
          </form>
        </Panel>
      </ReactFlow>
    </div>
  );
}
