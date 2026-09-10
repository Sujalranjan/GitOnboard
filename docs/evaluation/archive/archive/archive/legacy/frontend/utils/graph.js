/**
 * Computes the Weakly Connected Components (WCCs) of a directed graph.
 * 
 * @param {Array} nodes - Array of graph nodes
 * @param {Array} edges - Array of graph edges
 * @returns {Object} An object containing the components and standalone files.
 *  - components: Array of components, each containing { id, label, nodes, edges }.
 *  - standaloneNodes: Array of standalone nodes (degree 0).
 */
export const computeComponents = (nodes, edges) => {
  const wccAdj = new Map();
  nodes.forEach(n => wccAdj.set(n.id, []));
  
  // Build undirected adjacency list for WCC
  edges.forEach(e => {
    if (wccAdj.has(e.source) && wccAdj.has(e.target)) {
      wccAdj.get(e.source).push(e.target);
      wccAdj.get(e.target).push(e.source);
    }
  });

  const visited = new Set();
  const components = [];
  const standaloneNodes = [];
  
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  
  nodes.forEach(n => {
    if (!visited.has(n.id)) {
      const compNodes = [];
      const q = [n.id];
      visited.add(n.id);
      
      while (q.length > 0) {
        const u = q.shift();
        compNodes.push(nodeMap.get(u));
        
        for (const v of wccAdj.get(u)) {
          if (!visited.has(v)) {
            visited.add(v);
            q.push(v);
          }
        }
      }
      
      if (compNodes.length === 1) {
        standaloneNodes.push(compNodes[0]);
      } else {
        components.push(compNodes);
      }
    }
  });
  
  // Sort components by size descending
  components.sort((a, b) => b.length - a.length);
  
  // Map to structured objects and filter their specific edges
  const structuredComponents = components.map((compNodes, index) => {
    const compNodeIds = new Set(compNodes.map(n => n.id));
    const compEdges = edges.filter(e => compNodeIds.has(e.source) && compNodeIds.has(e.target));
    
    // Create a generic label for the component
    let label = `Component ${index + 1}`;
    if (index === 0) label = 'Main Component';
    else if (compNodes.length > 10) label = `Large Subsystem ${index + 1}`;
    else label = `Subsystem ${index + 1}`;
    
    return {
      id: `comp-${index}`,
      label,
      nodes: compNodes,
      edges: compEdges
    };
  });
  
  return {
    components: structuredComponents,
    standaloneNodes
  };
};
