import dagre from 'dagre';

/**
 * Computes a static layout for the given nodes and edges using Dagre.
 * This abstracts the layout engine away from the React Flow component.
 * 
 * @param {Array} nodes - Array of React Flow nodes
 * @param {Array} edges - Array of React Flow edges
 * @param {Object} options - Layout configuration options
 * @param {string} options.direction - Direction of the layout ('TB', 'LR', 'RL', 'BT')
 * @returns {Array} nodes - A new array of nodes with computed position coordinates
 */
export const layoutGraph = (nodes, edges, options = {}) => {
  const { direction = 'LR', forceReorder = false } = options;
  
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  
  // Set global layout config with optimal ranker and generous spacing
  dagreGraph.setGraph({ 
    rankdir: direction,
    nodesep: 80,  // horizontal distance between sibling nodes
    ranksep: 180, // vertical/layer distance between ranks
    ranker: 'network-simplex',
    marginx: 40,
    marginy: 40
  });

  // Add nodes to Dagre with accurate bounding dimensions
  nodes.forEach((node) => {
    const label = node.data?.label || '';
    const isFolder = node.type === 'folderNode';
    const estimatedWidth = isFolder ? 220 : Math.max(180, label.length * 8 + 48);
    const estimatedHeight = isFolder ? 65 : 55; 
    
    dagreGraph.setNode(node.id, { 
      width: estimatedWidth, 
      height: estimatedHeight 
    });
  });

  // Add edges to Dagre
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Execute the layout algorithm
  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    // If forceReorder is false, preserve existing stable positions
    if (!forceReorder && node.position && (node.position.x !== 0 || node.position.y !== 0) && !node._isNew) {
      return node;
    }
    
    const nodeWithPosition = dagreGraph.node(node.id);
    
    if (!nodeWithPosition) return node;

    return {
      ...node,
      _isNew: false,
      position: {
        x: nodeWithPosition.x - nodeWithPosition.width / 2,
        y: nodeWithPosition.y - nodeWithPosition.height / 2,
      },
    };
  });

  return layoutedNodes;
};

/**
 * Checks for AABB intersection between two rectangles.
 */
const checkIntersection = (rect1, rect2) => {
  return (
    rect1.x < rect2.x + rect2.width &&
    rect1.x + rect1.width > rect2.x &&
    rect1.y < rect2.y + rect2.height &&
    rect1.y + rect1.height > rect2.y
  );
};

/**
 * Unified Constraint-Based Local Relaxation algorithm with Compact Incremental Packing.
 * Used for both Expansion and Dragging to resolve overlaps naturally and locally.
 * 
 * @param {Array} nodes - All current React Flow nodes
 * @param {string} anchorNodeId - The ID of the immovable parent or dragged node
 * @param {boolean} isExpansion - If true, new nodes are densely packed into a local cluster
 */
export const applyLocalRelaxation = (nodes, anchorNodeId, isExpansion = false) => {
  let relaxedNodes = nodes.map(n => ({ ...n }));
  
  const anchorIndex = relaxedNodes.findIndex(n => n.id === anchorNodeId);
  if (anchorIndex === -1) return nodes; // No anchor, do nothing
  
  const anchorNode = relaxedNodes[anchorIndex];
  
  const NODE_WIDTH = 130;
  const NODE_HEIGHT = 50;
  const MARGIN = 15;
  
  const checkIntersectionMargin = (r1, r2, m = 15) => {
    return (
      r1.x < r2.x + r2.width + m &&
      r1.x + r1.width > r2.x - m &&
      r1.y < r2.y + r2.height + m &&
      r1.y + r1.height > r2.y - m
    );
  };
  
  // If this is an expansion, pack new children tightly around the anchor
  if (isExpansion) {
    let newNodes = relaxedNodes.filter(n => n._isNew);
    let maxClusterRadius = 0;
    
    if (newNodes.length > 0) {
      const placedChildrenRects = [];
      const parentRect = { x: anchorNode.position.x, y: anchorNode.position.y, width: NODE_WIDTH, height: NODE_HEIGHT };

      newNodes.forEach((n) => {
        let placed = false;
        let r = 80; // Start searching just outside the parent
        let theta = 0;
        
        while (!placed && r < 3000) {
          const x = anchorNode.position.x + Math.cos(theta) * r;
          const y = anchorNode.position.y + Math.sin(theta) * r;
          const candidateRect = { x, y, width: NODE_WIDTH, height: NODE_HEIGHT };
          
          let overlaps = checkIntersectionMargin(candidateRect, parentRect, MARGIN);
          if (!overlaps) {
            for (const placedRect of placedChildrenRects) {
              if (checkIntersectionMargin(candidateRect, placedRect, MARGIN)) {
                overlaps = true;
                break;
              }
            }
          }
          
          if (!overlaps) {
            n.position = { x, y };
            placedChildrenRects.push(candidateRect);
            placed = true;
            maxClusterRadius = Math.max(maxClusterRadius, r);
          } else {
            // Spiral outward slightly
            theta += 0.5; // radians
            r += 2; // px
          }
        }
        n._isNew = false;
      });

      // Exclude NON-DESCENDANT nodes from the cluster's local space
      const anchorPath = anchorNode.data?.path || '';
      const exclusionRadius = maxClusterRadius + 80; // Add padding margin around the grape bunch
      
      for (const n of relaxedNodes) {
        if (n.id === anchorNodeId) continue;
        if (!n.position) continue;
        
        // VFS-based descendant check
        const isDescendant = n.data?.path && n.data.path.startsWith(anchorPath + '/');
        
        // If it's a descendant, it belongs inside the territory. Skip it.
        if (isDescendant) continue;
        
        const dx = n.position.x - anchorNode.position.x;
        const dy = n.position.y - anchorNode.position.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        
        // If a non-descendant is inside the exclusion zone, push it radially outside
        if (dist < exclusionRadius) {
          const safeDx = dist === 0 ? 0.1 : dx;
          const safeDy = dist === 0 ? 0.1 : dy;
          const safeDist = dist === 0 ? 0.14 : dist;
          
          const pushAmount = exclusionRadius - safeDist;
          n.position.x += (safeDx / safeDist) * pushAmount;
          n.position.y += (safeDy / safeDist) * pushAmount;
        }
      }
    }
  }

  // Iterative relaxation loop (propagating local collision)
  const ITERATIONS = 15;

  for (let iter = 0; iter < ITERATIONS; iter++) {
    let moved = false;
    
    // Check every pair
    for (let i = 0; i < relaxedNodes.length; i++) {
      for (let j = i + 1; j < relaxedNodes.length; j++) {
        const n1 = relaxedNodes[i];
        const n2 = relaxedNodes[j];
        
        // Skip if neither has a position yet
        if (!n1.position || !n2.position) continue;

        const dx = n1.position.x - n2.position.x;
        const dy = n1.position.y - n2.position.y;
        
        const distX = Math.abs(dx);
        const distY = Math.abs(dy);
        
        const minX = NODE_WIDTH + MARGIN;
        const minY = NODE_HEIGHT + MARGIN;

        // AABB Collision Check
        if (distX < minX && distY < minY) {
          // They overlap!
          moved = true;
          
          // Calculate how far they need to move to resolve overlap
          const overlapX = minX - distX;
          const overlapY = minY - distY;
          
          // Resolve along the axis with the smallest overlap
          let pushX = 0;
          let pushY = 0;
          
          if (overlapX < overlapY) {
            pushX = dx > 0 ? overlapX : -overlapX;
            // Add a tiny bit of noise to prevent perfect vertical stacking locks
            pushY = (Math.random() - 0.5) * 5; 
          } else {
            pushY = dy > 0 ? overlapY : -overlapY;
            pushX = (Math.random() - 0.5) * 5;
          }

          const isN1Anchor = (n1.id === anchorNodeId);
          const isN2Anchor = (n2.id === anchorNodeId);

          if (isN1Anchor) {
            n2.position.x -= pushX;
            n2.position.y -= pushY;
          } else if (isN2Anchor) {
            n1.position.x += pushX;
            n1.position.y += pushY;
          } else {
            n1.position.x += pushX * 0.5;
            n1.position.y += pushY * 0.5;
            n2.position.x -= pushX * 0.5;
            n2.position.y -= pushY * 0.5;
          }
        }
      }
    }
    
    if (!moved) break; // Early exit if perfectly relaxed
  }

  return relaxedNodes;
};
