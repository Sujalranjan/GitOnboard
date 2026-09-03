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

// --- Custom Function Node ---
const FunctionNode = ({ data, selected }) => {
  return (
    <div className={`px-4 py-2 shadow-md rounded-md border-2 bg-white ${selected ? 'border-blue-500 shadow-blue-200' : 'border-gray-200'}`}>
      <Handle type="target" position={Position.Top} className="w-16 !bg-blue-500" />
      <div className="flex flex-col">
        <div className="text-xs text-gray-500 truncate max-w-[200px]" title={data.modulePath}>
          {data.modulePath}
        </div>
        <div className="font-mono font-bold text-sm text-gray-800">
          {data.label}()
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="w-16 !bg-blue-500" />
    </div>
  );
};

const nodeTypes = {
  functionNode: FunctionNode,
};

// --- Layout Algorithm ---
const getLayoutedElements = (nodes, edges, direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  
  const isHorizontal = direction === 'LR';
  dagreGraph.setGraph({ rankdir: direction, nodesep: 50, edgesep: 10, ranksep: 100 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 250, height: 60 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const newNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    // Move the anchor from the center to top-left
    const newNode = {
      ...node,
      position: {
        x: nodeWithPosition.x - 250 / 2,
        y: nodeWithPosition.y - 60 / 2,
      },
    };
    return newNode;
  });

  return { nodes: newNodes, edges };
};

export default function CallGraph({ repoName }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  const rfInstance = useRef(null);

  // Fetch Data
  useEffect(() => {
    const fetchGraph = async () => {
      try {
        setIsLoading(true);
        const res = await fetch(`/api/repos/${repoName}/call-graph`);
        if (!res.ok) throw new Error("Failed to fetch call graph.");
        const data = await res.json();

        const initialNodes = data.nodes.map(n => {
          const parts = n.full_name.split('.');
          const label = parts.pop();
          const modulePath = parts.join('.');
          
          return {
            id: n.id,
            type: 'functionNode',
            data: { label, modulePath, full_name: n.full_name },
            position: { x: 0, y: 0 }, // Will be laid out by dagre
          };
        });

        const initialEdges = data.edges.map(e => ({
          ...e,
          type: 'smoothstep',
          animated: true,
          style: { stroke: '#94a3b8', strokeWidth: 1.5 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: '#94a3b8',
          },
        }));

        const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(initialNodes, initialEdges);

        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
      } catch (err) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    };
    fetchGraph();
  }, [repoName]);

  // Derived State for Sidebar
  const selectedNodeData = useMemo(() => {
    if (!selectedNodeId) return null;
    const node = nodes.find(n => n.id === selectedNodeId);
    if (!node) return null;
    
    const outgoingEdges = edges.filter(e => e.source === selectedNodeId);
    const incomingEdges = edges.filter(e => e.target === selectedNodeId);
    
    const calls = outgoingEdges.map(e => nodes.find(n => n.id === e.target)).filter(Boolean);
    const calledBy = incomingEdges.map(e => nodes.find(n => n.id === e.source)).filter(Boolean);
    
    return { node, calls, calledBy };
  }, [selectedNodeId, nodes, edges]);

  // Handlers
  const onNodeClick = useCallback((_, node) => {
    setSelectedNodeId(node.id);
  }, []);

  const focusNode = useCallback((nodeId) => {
    const node = nodes.find(n => n.id === nodeId);
    if (node && rfInstance.current) {
      rfInstance.current.setCenter(node.position.x + 125, node.position.y + 30, { zoom: 1.2, duration: 800 });
      setSelectedNodeId(nodeId);
    }
  }, [nodes]);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    if (!searchQuery) return;
    
    const term = searchQuery.toLowerCase();
    const match = nodes.find(n => n.data.full_name.toLowerCase().includes(term));
    if (match) {
      focusNode(match.id);
    }
  };

  if (isLoading) {
    return <div className="h-full flex items-center justify-center text-gray-500">Generating Call Graph (AST parsing in progress)...</div>;
  }

  if (error) {
    return <div className="h-full p-4 text-red-600 bg-red-50">{error}</div>;
  }

  return (
    <div className="flex h-full w-full">
      {/* Sidebar */}
      <div className="w-80 border-r border-gray-200 bg-gray-50 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-gray-200 bg-white">
          <h2 className="text-lg font-bold text-gray-800 mb-2">Call Graph</h2>
          <form onSubmit={handleSearch} className="flex gap-2">
            <input 
              type="text" 
              placeholder="Search functions..." 
              className="flex-grow border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:border-blue-500"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <button type="submit" className="bg-blue-500 text-white px-3 py-1 rounded text-sm hover:bg-blue-600">Find</button>
          </form>
        </div>
        
        <div className="flex-grow overflow-y-auto p-4">
          {!selectedNodeData ? (
            <div className="text-gray-500 text-sm italic text-center mt-10">
              Click on a function node to see its relationships.
            </div>
          ) : (
            <div className="space-y-6">
              <div>
                <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Selected Function</h3>
                <div className="font-mono text-sm font-bold text-gray-900 break-all bg-white p-2 border border-gray-200 rounded">
                  {selectedNodeData.node.data.full_name}()
                </div>
              </div>
              
              <div>
                <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 border-b pb-1">
                  Called By ({selectedNodeData.calledBy.length})
                </h3>
                {selectedNodeData.calledBy.length > 0 ? (
                  <ul className="space-y-2">
                    {selectedNodeData.calledBy.map(n => (
                      <li 
                        key={n.id} 
                        onClick={() => focusNode(n.id)}
                        className="text-sm bg-white p-2 border border-gray-200 rounded hover:border-blue-400 cursor-pointer transition-colors font-mono break-all text-blue-700"
                      >
                        {n.data.label}()
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500 italic">No incoming calls found statically.</p>
                )}
              </div>
              
              <div>
                <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 border-b pb-1">
                  Calls ({selectedNodeData.calls.length})
                </h3>
                {selectedNodeData.calls.length > 0 ? (
                  <ul className="space-y-2">
                    {selectedNodeData.calls.map(n => (
                      <li 
                        key={n.id} 
                        onClick={() => focusNode(n.id)}
                        className="text-sm bg-white p-2 border border-gray-200 rounded hover:border-purple-400 cursor-pointer transition-colors font-mono break-all text-purple-700"
                      >
                        {n.data.label}()
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500 italic">No outgoing calls found statically.</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      
      {/* Graph Area */}
      <div className="flex-grow relative h-full">
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
        >
          <Background color="#f3f4f6" gap={20} size={1} />
          <Controls />
          <MiniMap 
            nodeColor={(n) => n.id === selectedNodeId ? '#3b82f6' : '#e5e7eb'}
            maskColor="rgba(240, 240, 240, 0.6)" 
          />
        </ReactFlow>
      </div>
    </div>
  );
}
