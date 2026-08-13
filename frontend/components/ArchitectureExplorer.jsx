"use client";

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Handle,
  Position
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';

// --- Custom Node ---
const ArchitectureNode = ({ data, selected }) => {
  const isExpandable = data.has_children;
  const isExpanded = data.expanded;
  
  const iconMap = {
    repository: '📦',
    folder: '📁',
    file: '📄',
    class: '🧩',
    function: '⚡'
  };
  
  const bgMap = {
    repository: 'bg-gray-100 dark:bg-slate-800',
    folder: 'bg-yellow-50 dark:bg-yellow-950/60',
    file: 'bg-blue-50 dark:bg-blue-950/60',
    class: 'bg-purple-50 dark:bg-purple-950/60',
    function: 'bg-green-50 dark:bg-green-950/60'
  };

  return (
    <div className={`px-3 py-2 shadow-sm rounded-md border-2 ${bgMap[data.type] || 'bg-white dark:bg-slate-900'} ${selected ? 'border-blue-500 shadow-md' : 'border-gray-300 dark:border-slate-700'} flex items-center gap-2 min-w-[160px] transition-colors`}>
      <Handle type="target" position={Position.Top} className="opacity-0" />
      
      <span className="text-xl">{iconMap[data.type] || '📌'}</span>
      
      <div className="flex-grow flex flex-col overflow-hidden">
        <span className="font-mono text-sm font-semibold text-gray-800 dark:text-slate-100 truncate max-w-[140px]" title={data.name}>
          {data.name}
        </span>
        <span className="text-xs text-gray-500 dark:text-slate-400 uppercase">{data.type}</span>
      </div>
      
      {isExpandable && (
        <button 
          onClick={(e) => {
            e.stopPropagation();
            data.onToggleExpand(data.id);
          }}
          className="w-6 h-6 flex items-center justify-center rounded-full bg-white dark:bg-slate-800 border border-gray-300 dark:border-slate-700 hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-600 dark:text-slate-200 font-bold transition-colors text-xs flex-shrink-0"
        >
          {isExpanded ? '−' : '+'}
        </button>
      )}
      
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
};

const nodeTypes = {
  archNode: ArchitectureNode,
};

const getLayoutedElements = (nodes, edges, direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction, nodesep: 40, edgesep: 15, ranksep: 70 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 220, height: 60 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const newNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 220 / 2,
        y: nodeWithPosition.y - 60 / 2,
      },
    };
  });

  return { nodes: newNodes, edges };
};

export default function ArchitectureExplorer({ repoName }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  
  const rfInstance = useRef(null);

  const fetchRoot = async () => {
    setIsLoading(true);
    setError(null);
    setSelectedNodeId(null);
    setExpandedNodes(new Set());
    
    try {
      const res = await fetch(`/api/repos/${repoName}/architecture?node_id=root`);
      if (!res.ok) throw new Error("Failed to fetch root architecture");
      const data = await res.json();
      
      const rawNodes = data.nodes || [];
      
      const rootNode = {
        id: 'root',
        type: 'archNode',
        data: {
          id: 'root',
          name: repoName,
          type: 'repository',
          has_children: true,
          expanded: true,
          onToggleExpand: handleToggleExpand,
        },
        position: { x: 0, y: 0 }
      };

      const initialExpanded = new Set(['root']);
      setExpandedNodes(initialExpanded);

      const formattedChildNodes = rawNodes.map(n => ({
        id: n.id,
        type: 'archNode',
        data: {
          ...n,
          expanded: false,
          onToggleExpand: handleToggleExpand,
        },
        position: { x: 0, y: 0 }
      }));

      const initialNodes = [rootNode, ...formattedChildNodes];
      
      const initialEdges = rawNodes.map(n => ({
        id: `e-root-${n.id}`,
        source: 'root',
        target: n.id,
        type: 'smoothstep',
        animated: true,
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
      }));

      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(initialNodes, initialEdges, 'TB');
      setNodes(layoutedNodes);
      setEdges(layoutedEdges);

      setTimeout(() => {
        if (rfInstance.current) rfInstance.current.fitView({ padding: 0.2, duration: 600 });
      }, 100);

    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleExpand = useCallback(async (nodeId) => {
    setNodes(currentNodes => {
      setEdges(currentEdges => {
        setExpandedNodes(prevExpanded => {
          const isCurrentlyExpanded = prevExpanded.has(nodeId);
          const nextExpanded = new Set(prevExpanded);

          if (isCurrentlyExpanded) {
            // Collapse: recursively find and remove all children of nodeId
            nextExpanded.delete(nodeId);

            const findChildIds = (parentIds) => {
              const children = currentEdges.filter(e => parentIds.has(e.source)).map(e => e.target);
              if (children.length === 0) return [];
              const childrenSet = new Set(children);
              return [...children, ...findChildIds(childrenSet)];
            };

            const descendantIds = new Set(findChildIds(new Set([nodeId])));

            const filteredNodes = currentNodes.map(n => {
              if (n.id === nodeId) {
                return { ...n, data: { ...n.data, expanded: false } };
              }
              return n;
            }).filter(n => !descendantIds.has(n.id));

            const filteredEdges = currentEdges.filter(e => !descendantIds.has(e.source) && !descendantIds.has(e.target));

            const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(filteredNodes, filteredEdges, 'TB');
            
            setTimeout(() => {
              setNodes(layoutedNodes);
              setEdges(layoutedEdges);
            }, 0);

            return nextExpanded;
          } else {
            // Expand: fetch children from backend API
            nextExpanded.add(nodeId);

            fetch(`/api/repos/${repoName}/architecture?node_id=${encodeURIComponent(nodeId)}`)
              .then(res => res.ok ? res.json() : Promise.reject(new Error("Failed to load children")))
              .then(data => {
                const childNodesData = data.nodes || [];
                if (childNodesData.length === 0) return;

                const existingNodeIds = new Set(currentNodes.map(n => n.id));
                const newChildNodes = childNodesData
                  .filter(n => !existingNodeIds.has(n.id))
                  .map(n => ({
                    id: n.id,
                    type: 'archNode',
                    data: {
                      ...n,
                      expanded: false,
                      onToggleExpand: handleToggleExpand,
                    },
                    position: { x: 0, y: 0 }
                  }));

                const newChildEdges = childNodesData.map(n => ({
                  id: `e-${nodeId}-${n.id}`,
                  source: nodeId,
                  target: n.id,
                  type: 'smoothstep',
                  animated: true,
                  style: { stroke: '#94a3b8', strokeWidth: 1.5 },
                  markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
                }));

                const updatedNodes = currentNodes.map(n => {
                  if (n.id === nodeId) {
                    return { ...n, data: { ...n.data, expanded: true } };
                  }
                  return n;
                }).concat(newChildNodes);

                const existingEdgeIds = new Set(currentEdges.map(e => e.id));
                const updatedEdges = currentEdges.concat(newChildEdges.filter(e => !existingEdgeIds.has(e.id)));

                const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(updatedNodes, updatedEdges, 'TB');

                setNodes(layoutedNodes);
                setEdges(layoutedEdges);
              })
              .catch(err => console.error("Error expanding node:", err));

            return nextExpanded;
          }
        });
        return currentEdges;
      });
      return currentNodes;
    });
  }, [repoName]);

  useEffect(() => {
    if (repoName) {
      fetchRoot();
    }
  }, [repoName]);

  const onNodeClick = useCallback((_, node) => {
    setSelectedNodeId(node.id);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  const selectedNodeData = useMemo(() => {
    if (!selectedNodeId) return null;
    const n = nodes.find(node => node.id === selectedNodeId);
    return n ? n.data : null;
  }, [selectedNodeId, nodes]);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950">
        <div className="flex flex-col items-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 dark:border-blue-400 mb-2"></div>
          <span>Building Architecture Hierarchy...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center p-8 bg-slate-50 dark:bg-slate-950">
        <div className="bg-red-50 dark:bg-red-950/60 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 p-4 rounded-lg max-w-md text-center">
          <h3 className="font-bold mb-1">Architecture Error</h3>
          <p className="text-sm">{error}</p>
          <button 
            onClick={fetchRoot}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded text-xs font-bold uppercase tracking-wider hover:bg-red-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full bg-gray-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors">
      {/* Sidebar Details Panel */}
      <div className="w-80 border-r border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col shadow-sm z-10 transition-colors">
        <div className="p-4 border-b border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex justify-between items-start">
          <div>
            <h2 className="text-lg font-bold text-gray-800 dark:text-slate-100">Architecture</h2>
            <p className="text-sm text-gray-500 dark:text-slate-400 mt-1">Hierarchical Repository View</p>
          </div>
          <button 
            onClick={fetchRoot}
            className="text-xs bg-gray-200 dark:bg-slate-800 hover:bg-gray-300 dark:hover:bg-slate-700 text-gray-700 dark:text-slate-200 px-2 py-1 rounded transition-colors"
            title="Reset to root view"
          >
            Reset
          </button>
        </div>
        
        <div className="flex-grow overflow-y-auto p-4">
          {!selectedNodeData ? (
            <div className="text-gray-500 dark:text-slate-400 text-sm italic text-center mt-10">
              Select a node to view its details.
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <h3 className="text-xs font-bold text-gray-400 dark:text-slate-400 uppercase tracking-wider mb-1">Name</h3>
                <div className="font-mono text-sm font-bold text-gray-900 dark:text-slate-100 break-all bg-white dark:bg-slate-800 p-2 border border-gray-200 dark:border-slate-700 rounded">
                  {selectedNodeData.name}
                </div>
              </div>
              
              <div>
                <h3 className="text-xs font-bold text-gray-400 dark:text-slate-400 uppercase tracking-wider mb-1">Type</h3>
                <div className="text-sm text-gray-700 dark:text-slate-200 bg-white dark:bg-slate-800 p-2 border border-gray-200 dark:border-slate-700 rounded uppercase font-semibold">
                  {selectedNodeData.type}
                </div>
              </div>
              
              <div>
                <h3 className="text-xs font-bold text-gray-400 dark:text-slate-400 uppercase tracking-wider mb-1">Path / ID</h3>
                <div className="text-sm text-gray-600 dark:text-slate-300 font-mono bg-gray-100 dark:bg-slate-800 p-2 rounded break-all border border-gray-200 dark:border-slate-700">
                  {selectedNodeData.id}
                </div>
              </div>
              
              <div>
                <h3 className="text-xs font-bold text-gray-400 dark:text-slate-400 uppercase tracking-wider mb-1">Children</h3>
                <div className="text-sm text-gray-700 dark:text-slate-300">
                  {selectedNodeData.has_children ? 'Has children (can expand)' : 'Leaf node'}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      
      {/* Graph Area */}
      <div className="flex-grow relative h-full bg-slate-50 dark:bg-slate-950">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          onInit={(instance) => { rfInstance.current = instance; instance.fitView(); }}
          fitView
          minZoom={0.05}
          maxZoom={2}
          nodesDraggable={false}
        >
          <Background color="#94a3b8" gap={20} size={1} />
          <Controls />
          <MiniMap 
            nodeColor={(n) => n.id === selectedNodeId ? '#3b82f6' : '#64748b'}
            maskColor="rgba(15, 23, 42, 0.6)" 
          />
        </ReactFlow>
      </div>
    </div>
  );
}
