import { MultiDirectedGraph } from 'graphology';

// ──────────────────────────────────────────────────────────────────────────
// COLOR PALETTES
// ──────────────────────────────────────────────────────────────────────────

export const NODE_TYPE_COLORS: Record<string, string> = {
  FUNCTION: '#10b981',       // Emerald green
  METHOD: '#14b8a6',         // Teal
  CLASS: '#8b5cf6',          // Violet
  FILE: '#3b82f6',           // Blue
  ROUTE: '#f59e0b',          // Amber
  DATABASE_OBJECT: '#06b6d4',// Cyan
  CAPABILITY: '#ec4899',     // Pink
  MODULE: '#6366f1',         // Indigo
  DIRECTORY: '#f97316',      // Orange — folders stand out at top level
  DEFAULT: '#64748b',        // Slate
};

export const EDGE_COLORS_DARK: Record<string, string> = {
  CALLS: 'rgba(16, 185, 129, 0.45)',
  IMPORTS: 'rgba(99, 102, 241, 0.45)',
  INHERITS: 'rgba(139, 92, 246, 0.45)',
  ROUTE_HANDLER: 'rgba(245, 158, 11, 0.50)',
  DATABASE_ACCESS: 'rgba(6, 182, 212, 0.50)',
  CAPABILITY_MEMBER: 'rgba(236, 72, 153, 0.50)',
  DECLARES: 'rgba(148, 163, 184, 0.25)',
  CONTAINS: 'rgba(249, 115, 22, 0.30)',
  USES: 'rgba(148, 163, 184, 0.25)',
  REFERENCES: 'rgba(56, 189, 248, 0.40)',
  GENERIC: 'rgba(148, 163, 184, 0.25)',
};

export const EDGE_COLORS_LIGHT: Record<string, string> = {
  CALLS: 'rgba(5, 150, 105, 0.55)',
  IMPORTS: 'rgba(79, 70, 229, 0.55)',
  INHERITS: 'rgba(124, 58, 237, 0.55)',
  ROUTE_HANDLER: 'rgba(217, 119, 6, 0.60)',
  DATABASE_ACCESS: 'rgba(8, 145, 178, 0.60)',
  CAPABILITY_MEMBER: 'rgba(219, 39, 119, 0.60)',
  DECLARES: 'rgba(100, 116, 139, 0.35)',
  CONTAINS: 'rgba(234, 88, 12, 0.35)',
  USES: 'rgba(100, 116, 139, 0.35)',
  REFERENCES: 'rgba(2, 132, 199, 0.45)',
  GENERIC: 'rgba(100, 116, 139, 0.35)',
};

// ──────────────────────────────────────────────────────────────────────────
// SEMANTIC EDGE WEIGHTS (for ForceAtlas2 physical layout)
// ──────────────────────────────────────────────────────────────────────────

export const SEMANTIC_EDGE_WEIGHTS: Record<string, number> = {
  // Structural/local (tight clustering)
  CONTAINS: 2.0,
  DECLARES: 2.0,
  CAPABILITY_MEMBER: 2.0,
  // Functional/regional
  ROUTE_HANDLER: 2.0,
  DATABASE_ACCESS: 2.0,
  // Bridge/dependency (loose attraction, allowing separation)
  CALLS: 0.5,
  IMPORTS: 0.5,
  REFERENCES: 0.5,
  INHERITS: 1.0,
  USES: 0.5,
  GENERIC: 0.5,
};

// ──────────────────────────────────────────────────────────────────────────
// POSITION HELPERS
// ──────────────────────────────────────────────────────────────────────────

/**
 * Initializes newly added nodes near their parent with non-topological starting coordinates.
 * ForceAtlas2 determines their final positions during expansion settling.
 */
export function computeClusteredPositions(
  newNodes: any[],
  anchorPos: { x: number; y: number }
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const total = newNodes.length;
  if (total === 0) return positions;

  const GOLDEN_ANGLE = 2.399963229728653;
  const c = 20;
  newNodes.forEach((n, idx) => {
    const r = c * Math.sqrt(idx + 1);
    const theta = (idx + 1) * GOLDEN_ANGLE;
    positions.set(n.id, {
      x: anchorPos.x + r * Math.cos(theta),
      y: anchorPos.y + r * Math.sin(theta),
    });
  });
  return positions;
}

/**
 * Assigns valid, finite, non-identical initial coordinates to nodes.
 * The initial coordinates do NOT encode topology or intentionally form an artificial visual layout.
 * ForceAtlas2 determines the resulting spatial organization.
 */
export function computeInitialPositions(nodes: any[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  if (!nodes || nodes.length === 0) return positions;
  const total = nodes.length;

  const GOLDEN_ANGLE = 2.399963229728653;
  // Dynamic scale factor ensures constant density whether there are 8 or 800 nodes
  const c = Math.max(22, 160 / Math.sqrt(Math.max(total, 1)));
  nodes.forEach((n, idx) => {
    const r = c * Math.sqrt(idx + 1);
    const theta = (idx + 1) * GOLDEN_ANGLE;
    positions.set(n.id, {
      x: r * Math.cos(theta),
      y: r * Math.sin(theta),
    });
  });
  return positions;
}

export function buildNodeAttributes(n: any, pos: { x: number; y: number }, isDark: boolean) {
  const typeKey = (n.type || 'DEFAULT').toUpperCase();
  const color = NODE_TYPE_COLORS[typeKey] || NODE_TYPE_COLORS.DEFAULT;
  const degree = (n.in_degree || 0) + (n.out_degree || 0);
  const isDir = typeKey === 'DIRECTORY';
  const isCap = typeKey === 'CAPABILITY';

  // Directories and capabilities are larger/more prominent
  const size = isDir
    ? 18
    : isCap
    ? 14
    : Math.min(16, Math.max(6.5, 6.5 + Math.sqrt(degree) * 1.5));

  let zIndex = 1;
  if (isDir || isCap) zIndex = 4;
  else if (typeKey === 'FILE' || typeKey === 'CLASS' || typeKey === 'ROUTE') zIndex = 2;

  return {
    x: pos.x,
    y: pos.y,
    size,
    color,
    label: n.name || n.label || n.id,
    rawType: typeKey,
    rawNode: n,
    degree,
    zIndex,
    expandable: n.expandable ?? false,
    expanded: n.expanded ?? false,
    isNewExpansion: false,
  };
}

export function buildEdgeAttributes(e: any, isDark: boolean) {
  const relType = (e.type || 'GENERIC').toUpperCase();
  const edgeColorPalette = isDark ? EDGE_COLORS_DARK : EDGE_COLORS_LIGHT;
  const weight = SEMANTIC_EDGE_WEIGHTS[relType] ?? SEMANTIC_EDGE_WEIGHTS.GENERIC;
  return {
    color: edgeColorPalette[relType] || edgeColorPalette.GENERIC,
    size: relType === 'CONTAINS' ? 0.8 : 1.0,
    weight,
    type: 'arrow',
    relType,
    evidenceLine: e.evidence_line,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// GRAPH BUILDER UTILITIES
// ──────────────────────────────────────────────────────────────────────────

/**
 * Build a fresh Graphology graph from overview/full graph data.
 * Call this on initial load or full reset.
 */
export function buildInitialGraph(
  nodes: any[],
  edges: any[],
  isDark: boolean,
  activeRelFilters: Set<string>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): any {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const g: any = new MultiDirectedGraph();
  if (!nodes || nodes.length === 0) return g;

  const initialPositions = computeInitialPositions(nodes);

  nodes.forEach((n: any) => {
    const pos = initialPositions.get(n.id) || { x: 0, y: 0 };
    g.addNode(n.id, buildNodeAttributes(n, pos, isDark));
  });

  if (edges) {
    edges.forEach((e: any) => {
      if (g.hasNode(e.source) && g.hasNode(e.target)) {
        const relType = (e.type || 'GENERIC').toUpperCase();
        if (activeRelFilters.size > 0 && !activeRelFilters.has(relType)) return;
        const edgeKey = e.id || `e-${e.source}-${e.target}-${relType}`;
        if (!g.hasEdge(edgeKey)) {
          g.addEdgeWithKey(edgeKey, e.source, e.target, buildEdgeAttributes(e, isDark));
        }
      }
    });
  }

  return g;
}

/**
 * Inject new nodes and edges from an expansion response into an existing graph.
 * New nodes are positioned near the expanded node with non-topological initial coordinates.
 * Returns the list of newly added node IDs.
 */
export function injectExpansionData(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  graph: any,
  expandedNodeId: string,
  newNodes: any[],
  newEdges: any[],
  isDark: boolean,
  activeRelFilters: Set<string>
): string[] {
  // Mark the expanded node as already expanded
  if (graph.hasNode(expandedNodeId)) {
    graph.setNodeAttribute(expandedNodeId, 'expanded', true);
    graph.setNodeAttribute(expandedNodeId, 'expandable', false);
  }

  // Determine anchor position (where to cluster new nodes)
  let anchorPos = { x: 0, y: 0 };
  if (graph.hasNode(expandedNodeId)) {
    anchorPos = {
      x: graph.getNodeAttribute(expandedNodeId, 'x'),
      y: graph.getNodeAttribute(expandedNodeId, 'y'),
    };
  }

  // Only add truly new nodes (skip duplicates)
  const trulyNew = newNodes.filter((n) => !graph.hasNode(n.id));
  const positions = computeClusteredPositions(trulyNew, anchorPos);

  const addedIds: string[] = [];
  trulyNew.forEach((n: any) => {
    const pos = positions.get(n.id) || anchorPos;
    const attrs = buildNodeAttributes(n, pos, isDark);
    attrs.isNewExpansion = true;
    graph.addNode(n.id, attrs);
    addedIds.push(n.id);
  });

  // Add edges (skip duplicates)
  newEdges.forEach((e: any) => {
    if (graph.hasNode(e.source) && graph.hasNode(e.target)) {
      const relType = (e.type || 'GENERIC').toUpperCase();
      if (activeRelFilters.size > 0 && !activeRelFilters.has(relType)) return;
      const edgeKey = e.id || `e-${e.source}-${e.target}-${relType}`;
      if (!graph.hasEdge(edgeKey)) {
        graph.addEdgeWithKey(edgeKey, e.source, e.target, buildEdgeAttributes(e, isDark));
      }
    }
  });

  return addedIds;
}
