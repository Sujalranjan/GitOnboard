"use client";

import React, { useState, useCallback, useRef, useMemo } from 'react';
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
    <div className={`px-4 py-2 shadow-md rounded-md border-2 bg-white dark:bg-slate-900 ${selected ? 'border-blue-500 shadow-blue-200 dark:shadow-blue-900' : 'border-gray-200 dark:border-slate-700'} min-w-[200px] transition-colors`}>
      <Handle type="target" position={Position.Top} className="w-8 !bg-blue-500" />
      <div className="flex flex-col">
        <div className="text-xs text-gray-500 dark:text-slate-400 truncate max-w-[200px]" title={data.modulePath}>
          {data.modulePath}
        </div>
        <div className="font-mono font-bold text-sm text-gray-800 dark:text-slate-100">
          {data.label}()
        </div>
      </div>
      
      <div className="mt-2 pt-2 border-t border-gray-100 dark:border-slate-800 flex justify-center">
        <button 
          className="text-xs bg-gray-100 dark:bg-slate-800 hover:bg-gray-200 dark:hover:bg-slate-700 text-gray-700 dark:text-slate-200 px-2 py-1 rounded transition-colors"
          onClick={(e) => {
            e.stopPropagation();
            data.onExpand(data.id);
          }}
          disabled={data.isExpanding}
        >
          {data.isExpanding ? '...' : 'Expand ↓'}
        </button>
      </div>
      <Handle type="source" position={Position.Bottom} className="w-8 !bg-blue-500" />
    </div>
  );
};

const nodeTypes = {
  functionNode: FunctionNode,
};

const getLayoutedElements = (nodes, edges, direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction, nodesep: 50, edgesep: 10, ranksep: 100 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 250, height: 80 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  return nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 250 / 2,
        y: nodeWithPosition.y - 80 / 2,
      },
    };
  });
};

export default function CallExplorer({ repoName }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [error, setError] = useState(null);
  const [depth, setDepth] = useState(1);
  
  const rfInstance = useRef(null);
  
  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery) return;
    
    setIsSearching(true);
    try {
      const res = await fetch(`/api/repos/${repoName}/graph/search?q=${encodeURIComponent(searchQuery)}`);
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      setSearchResults(data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSearching(false);
    }
  };

  const loadNeighborhood = async (nodeId, parentPos = null) => {
    try {
      setNodes(nds => nds.map(n => n.id === nodeId ? { ...n, data: { ...n.data, isExpanding: true } } : n));
      
      const res = await fetch(`/api/repos/${repoName}/graph/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id: nodeId,
          direction: "both",
          depth: depth,
          max_nodes: 50
        })
      });
      
      if (!res.ok) throw new Error("Query failed");
      const data = await res.json();
      
      setNodes(currentNodes => {
        setEdges(currentEdges => {
          const existingNodeIds = new Set(currentNodes.map(n => n.id));
          const existingEdgeIds = new Set(currentEdges.map(e => e.id));
          
          const newRawNodes = data.nodes.filter(n => !existingNodeIds.has(n.id));
          const newRawEdges = data.edges.filter(e => !existingEdgeIds.has(e.id));
          
          if (newRawNodes.length === 0 && (currentNodes.length > 0 || existingNodeIds.has(nodeId))) {
            return currentEdges;
          }
          
          const newEdges = newRawEdges.map(e => ({
            ...e,
            type: 'smoothstep',
            animated: true,
            style: { stroke: '#94a3b8', strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
          }));
          
          const mergedEdges = [...currentEdges, ...newEdges];
          
          let newNodes = newRawNodes.map(n => {
            const parts = n.full_name.split('::');
            const label = parts.pop();
            const modulePath = parts.join('::');
            return {
              id: n.id,
              type: 'functionNode',
              data: { label, modulePath, full_name: n.full_name, onExpand: handleExpand, id: n.id },
              position: { x: 0, y: 0 }
            };
          });
          
          if (currentNodes.length === 0 && !existingNodeIds.has(nodeId)) {
             const rootData = data.nodes.find(n => n.id === nodeId);
             if (rootData) {
                 const parts = rootData.full_name.split('::');
                 newNodes.push({
                     id: rootData.id,
                     type: 'functionNode',
                     data: { label: parts.pop(), modulePath: parts.join('::'), full_name: rootData.full_name, onExpand: handleExpand, id: rootData.id },
                     position: { x: 0, y: 0 }
                 });
             }
          }
          
          const mergedNodes = [...currentNodes, ...newNodes];
          const layoutedNodes = getLayoutedElements(mergedNodes, mergedEdges, 'TB');
          
          if (parentPos) {
             const layoutedParent = layoutedNodes.find(n => n.id === nodeId);
             if (layoutedParent) {
                 const dx = parentPos.x - layoutedParent.position.x;
                 const dy = parentPos.y - layoutedParent.position.y;
                 
                 newNodes = newNodes.map(nn => {
                     const lNode = layoutedNodes.find(n => n.id === nn.id);
                     return {
                         ...nn,
                         position: {
                             x: lNode.position.x + dx,
                             y: lNode.position.y + dy
                         }
                     };
                 });
             }
          } else {
             newNodes = newNodes.map(nn => {
                 const lNode = layoutedNodes.find(n => n.id === nn.id);
                 return { ...nn, position: lNode.position };
             });
          }
          
          setTimeout(() => {
              setNodes([...currentNodes, ...newNodes].map(n => 
                  n.id === nodeId ? { ...n, data: { ...n.data, isExpanding: false } } : n
              ));
              
              if (rfInstance.current && !parentPos) {
                 setTimeout(() => rfInstance.current.fitView({ padding: 0.2, duration: 800 }), 100);
              }
          }, 0);
          
          return mergedEdges;
        });
        
        return currentNodes;
      });
      
    } catch (err) {
      setError(err.message);
      setNodes(nds => nds.map(n => n.id === nodeId ? { ...n, data: { ...n.data, isExpanding: false } } : n));
    }
  };

  const handleExpand = useCallback((nodeId) => {
    setNodes(nds => {
       const node = nds.find(n => n.id === nodeId);
       if (node) {
           loadNeighborhood(nodeId, node.position);
       }
       return nds;
    });
  }, [repoName, depth]);

  const selectEntryPoint = (result) => {
    setNodes([]);
    setEdges([]);
    setSearchResults([]);
    setSearchQuery(result.name);
    loadNeighborhood(result.id, null);
    setSelectedNodeId(result.id);
  };

  const onNodeClick = useCallback((_, node) => {
    setSelectedNodeId(node.id);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);
  
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

  return (
    <div className="flex h-full w-full bg-gray-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors">
      {/* Sidebar */}
      <div className="w-80 border-r border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col shadow-sm z-10 transition-colors">
        <div className="p-4 border-b border-gray-200 dark:border-slate-800">
          <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4">Call Explorer</h2>
          
          <form onSubmit={handleSearch} className="flex gap-2">
            <input 
              type="text" 
              placeholder="Search functions or files..." 
              className="flex-grow border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <button type="submit" className="bg-blue-600 dark:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 dark:hover:bg-blue-500 transition-colors">
              {isSearching ? "..." : "Find"}
            </button>
          </form>
          
          <div className="mt-4 flex items-center justify-between text-sm text-gray-600 dark:text-slate-400">
            <span>Expansion Depth:</span>
            <select 
              className="border border-gray-300 dark:border-slate-700 rounded px-2 py-1 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              value={depth}
              onChange={(e) => setDepth(parseInt(e.target.value))}
            >
              <option value={1}>1 Hop</option>
              <option value={2}>2 Hops</option>
              <option value={3}>3 Hops</option>
            </select>
          </div>
        </div>
        
        <div className="flex-grow overflow-y-auto p-4">
          {error && <div className="text-red-600 dark:text-red-400 text-sm mb-4 bg-red-50 dark:bg-red-950/60 p-2 rounded border border-red-100 dark:border-red-900">{error}</div>}
          
          {searchResults.length > 0 ? (
            <div>
              <h3 className="text-xs font-bold text-gray-500 dark:text-slate-400 uppercase mb-2">Search Results</h3>
              <ul className="space-y-2">
                {searchResults.map(res => (
                  <li 
                    key={res.id} 
                    onClick={() => selectEntryPoint(res)}
                    className="p-3 border border-gray-200 dark:border-slate-800 rounded hover:border-blue-500 dark:hover:border-blue-400 hover:shadow-sm cursor-pointer transition-all bg-white dark:bg-slate-800/80"
                  >
                    <div className="font-mono text-sm font-bold text-blue-700 dark:text-blue-400 truncate">{res.name}()</div>
                    <div className="text-xs text-gray-500 dark:text-slate-400 truncate mt-1">{res.id}</div>
                  </li>
                ))}
              </ul>
            </div>
          ) : !selectedNodeData ? (
            <div className="text-gray-400 dark:text-slate-500 text-sm text-center mt-10">
              <svg className="w-12 h-12 mx-auto mb-3 text-gray-300 dark:text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
              Search for a function to begin exploration.
            </div>
          ) : (
            <div className="space-y-6">
              <div>
                <h3 className="text-xs font-bold text-gray-400 dark:text-slate-400 uppercase tracking-wider mb-2">Selected Node</h3>
                <div className="bg-blue-50 dark:bg-blue-950/60 border border-blue-100 dark:border-blue-900/60 p-3 rounded">
                  <div className="font-mono text-sm font-bold text-gray-900 dark:text-slate-100 break-all mb-1">
                    {selectedNodeData.node.data.label}()
                  </div>
                  <div className="text-xs text-gray-600 dark:text-slate-400 break-all font-mono">
                    {selectedNodeData.node.data.modulePath}
                  </div>
                </div>
              </div>
              
              <div>
                <h3 className="text-xs font-bold text-gray-400 dark:text-slate-400 uppercase tracking-wider mb-2 flex justify-between">
                  <span>Called By</span>
                  <span className="bg-gray-200 dark:bg-slate-800 text-gray-700 dark:text-slate-300 px-2 rounded-full">{selectedNodeData.calledBy.length}</span>
                </h3>
                {selectedNodeData.calledBy.length > 0 ? (
                  <ul className="space-y-2">
                    {selectedNodeData.calledBy.map(n => (
                      <li key={n.id} onClick={() => { setSelectedNodeId(n.id); if (rfInstance.current) rfInstance.current.setCenter(n.position.x + 100, n.position.y + 50, { zoom: 1.2, duration: 800 }); }} className="text-sm bg-white dark:bg-slate-800 p-2 border border-gray-200 dark:border-slate-700 rounded hover:border-blue-400 cursor-pointer transition-colors font-mono truncate text-blue-700 dark:text-blue-400">
                        {n.data.label}()
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-400 dark:text-slate-500 italic">No incoming calls explored.</p>
                )}
              </div>
              
              <div>
                <h3 className="text-xs font-bold text-gray-400 dark:text-slate-400 uppercase tracking-wider mb-2 flex justify-between">
                  <span>Calls</span>
                  <span className="bg-gray-200 dark:bg-slate-800 text-gray-700 dark:text-slate-300 px-2 rounded-full">{selectedNodeData.calls.length}</span>
                </h3>
                {selectedNodeData.calls.length > 0 ? (
                  <ul className="space-y-2">
                    {selectedNodeData.calls.map(n => (
                      <li key={n.id} onClick={() => { setSelectedNodeId(n.id); if (rfInstance.current) rfInstance.current.setCenter(n.position.x + 100, n.position.y + 50, { zoom: 1.2, duration: 800 }); }} className="text-sm bg-white dark:bg-slate-800 p-2 border border-gray-200 dark:border-slate-700 rounded hover:border-purple-400 cursor-pointer transition-colors font-mono truncate text-purple-700 dark:text-purple-400">
                        {n.data.label}()
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-400 dark:text-slate-500 italic">No outgoing calls explored.</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      
      {/* Graph Area */}
      <div className="flex-grow relative h-full bg-slate-50 dark:bg-slate-950">
        {nodes.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-950/80 text-blue-500 dark:text-blue-400 mb-4">
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
              </div>
              <h2 className="text-2xl font-bold text-gray-700 dark:text-slate-100 mb-2">Incremental Graph Explorer</h2>
              <p className="text-gray-500 dark:text-slate-400 max-w-md mx-auto">
                Search for an entry point in the sidebar to start exploring. Click "Expand" on any node to load its immediate neighbors without rendering the entire repository.
              </p>
            </div>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            onInit={(instance) => { rfInstance.current = instance; }}
            minZoom={0.1}
            maxZoom={2}
          >
            <Background color="#94a3b8" gap={20} size={1} />
            <Controls />
            <MiniMap 
              nodeColor={(n) => n.id === selectedNodeId ? '#3b82f6' : '#64748b'}
              maskColor="rgba(15, 23, 42, 0.6)" 
            />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}
