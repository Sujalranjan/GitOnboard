"use client";

import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { MultiDirectedGraph } from 'graphology';
import forceAtlas2, { ForceAtlas2Settings } from 'graphology-layout-forceatlas2';
import {
  SigmaContainer,
  useSigma,
  useRegisterEvents,
  useCamera,
  useSetSettings,
} from '@react-sigma/core';
import '@react-sigma/core/lib/style.css';
import { useTheme } from '@/components/theme-provider';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  Sparkles,
} from 'lucide-react';

import {
  NODE_TYPE_COLORS,
  EDGE_COLORS_DARK,
  EDGE_COLORS_LIGHT,
  SEMANTIC_EDGE_WEIGHTS,
} from './graphModel';

export { buildInitialGraph, injectExpansionData } from './graphModel';

// ──────────────────────────────────────────────────────────────────────────
// PROPS INTERFACE
// ──────────────────────────────────────────────────────────────────────────

export interface SigmaKnowledgeGraphCanvasProps {
  /** The stable mutable Graphology graph instance to render */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  graphRef: React.MutableRefObject<any>;
  /** Called whenever the graph has been mutated and sigma should re-render */
  graphVersion: number;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  onExpandNode?: (nodeId: string) => void;
  activeRelFilters: Set<string>;
  focusNodeId?: string | null;
  searchQuery?: string;
}

// ──────────────────────────────────────────────────────────────────────────
// INTERNAL CONTROLLERS
// ──────────────────────────────────────────────────────────────────────────

// ──────────────────────────────────────────────────────────────────────────
// LAYOUT LIFECYCLE & STABILITY CONSTANTS
// ──────────────────────────────────────────────────────────────────────────

type LayoutMode =
  | 'IDLE'
  | 'INITIAL_SETTLING'
  | 'EXPANSION_SETTLING'
  | 'MANUAL_RELAYOUT'
  | 'DRAGGING'
  | 'POST_DRAG_SETTLING';

export type LayoutStopReason =
  | 'STOP_REASON_STABLE'
  | 'STOP_REASON_SAFETY_LIMIT'
  | 'STOP_REASON_CANCELLED'
  | 'STOP_REASON_UNMOUNTED';

// ==========================================
// ForceAtlas2 stability & termination thresholds
// ==========================================
// Movement-based stability requires BOTH average displacement across all non-fixed nodes
// AND maximum displacement of any individual non-fixed node to remain below thresholds
// for REQUIRED_CONSECUTIVE_STABLE_CHECKS consecutive frames.
export const STABLE_AVG_THRESHOLD = 0.015;            // Maximum average displacement across all non-fixed nodes
export const STABLE_MAX_THRESHOLD = 0.06;              // Maximum displacement of any single non-fixed node
export const REQUIRED_CONSECUTIVE_STABLE_CHECKS = 10; // Consecutive frames both thresholds must be met
export const MAX_SAFETY_CAP_FRAMES = 2500;            // Emergency safety fallback limit to prevent infinite loops; NEVER normal termination
const DRAG_THRESHOLD_PX = 5;                           // Screen pixels of movement required to enter drag mode

// ==========================================
// Drag Elastic Spring Parameters
// ==========================================
// Applies temporary restorative spring force to directly connected neighbors during node dragging.
// High-weight structural edges receive stronger spring pull; weak dependencies receive gentle pull.
export const DRAG_SPRING_STIFFNESS = 0.70;             // Spring constant k: fraction of stretch restored per frame
export const DRAG_SPRING_MAX_DISPLACEMENT = 120.0;     // Hard displacement cap (graph units) per frame
export const DRAG_SPRING_MIN_EXTENSION = 0.0;          // Deadzone before spring engages (0 = engages on any stretch)

export interface DragSpringNeighbor {
  neighborId: string;
  restLength: number;
  weight: number;
}

// ==========================================
// ForceAtlas2 tuning parameters
// Manually adjust these values when tuning
// ==========================================
const FA2_LIN_LOG_MODE = true;
const FA2_OUTBOUND_ATTRACTION_DISTRIBUTION = false;
const FA2_SCALING_RATIO = 10.0;
const FA2_GRAVITY = 0.08;
const FA2_EDGE_WEIGHT_INFLUENCE = 1.0;
const FA2_MIN_SCREEN_GAP_PX = 10;

/**
 * Execute ForceAtlas2 iterations and measure node displacement for stability detection.
 */
function runFA2Step(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  g: any,
  iterations: number,
  slowdown: number,
  measureStability: boolean,
  extraRadiusPadding: number = 0
): { avgDisplacement: number; maxDisplacement: number } {
  // Capture previous positions of non-fixed nodes
  const prevPositions = new Map<string, { x: number; y: number }>();
  if (measureStability) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    g.forEachNode((id: string, attr: any) => {
      if (!attr.fixed) {
        prevPositions.set(id, { x: attr.x, y: attr.y });
      }
    });
  }

  // Temporarily apply camera-calibrated collision padding strictly for ForceAtlas2 calculation
  const originalSizes = new Map<string, number>();
  if (extraRadiusPadding > 0) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    g.forEachNode((id: string, attr: any) => {
      const s = attr.size || 1;
      originalSizes.set(id, s);
      g.setNodeAttribute(id, 'size', s + extraRadiusPadding);
    });
  }

  forceAtlas2.assign(g, {
    iterations,
    settings: {
      linLogMode: FA2_LIN_LOG_MODE,
      outboundAttractionDistribution: FA2_OUTBOUND_ATTRACTION_DISTRIBUTION,
      adjustSizes: true,
      edgeWeightInfluence: FA2_EDGE_WEIGHT_INFLUENCE,
      scalingRatio: FA2_SCALING_RATIO,
      gravity: FA2_GRAVITY,
      strongGravityMode: false,
      slowDown: slowdown,
      barnesHutOptimize: g.order > 150,
      barnesHutTheta: 0.5,
    },
  });

  // Immediately restore original node sizes so Sigma WebGL rendering and visual size remain 100% unchanged
  if (extraRadiusPadding > 0) {
    originalSizes.forEach((s, id) => {
      g.setNodeAttribute(id, 'size', s);
    });
  }

  if (!measureStability) {
    return { avgDisplacement: 0, maxDisplacement: 0 };
  }

  let totalDisplacement = 0;
  let maxDisplacement = 0;
  let measuredCount = 0;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  g.forEachNode((id: string, attr: any) => {
    if (!attr.fixed && prevPositions.has(id)) {
      const prev = prevPositions.get(id)!;
      const dx = attr.x - prev.x;
      const dy = attr.y - prev.y;
      const dist = Math.hypot(dx, dy);
      totalDisplacement += dist;
      if (dist > maxDisplacement) {
        maxDisplacement = dist;
      }
      measuredCount++;
    }
  });

  const avgDisplacement = measuredCount > 0 ? totalDisplacement / measuredCount : 0;
  return { avgDisplacement, maxDisplacement };
}

/**
 * Helper to calculate graph-space distance corresponding to a screen-space pixel displacement
 * at the DEFAULT CAMERA VIEW using Sigma v3's viewportToGraph with explicit cameraState override.
 *
 * This performs calibration against Sigma's default camera state (center {0.5, 0.5}, ratio 1, angle 0)
 * without moving the user's active camera or creating a second coordinate system.
 */
function getGraphDistanceForScreenPixels(sigma: any, desiredGapPx: number): number {
  if (!sigma || typeof sigma.viewportToGraph !== 'function' || desiredGapPx <= 0) {
    return 0;
  }
  try {
    const defaultCameraState = { x: 0.5, y: 0.5, ratio: 1.0, angle: 0 };
    const pA = sigma.viewportToGraph({ x: 0, y: 0 }, { cameraState: defaultCameraState });
    const pB = sigma.viewportToGraph({ x: desiredGapPx, y: 0 }, { cameraState: defaultCameraState });
    return Math.hypot(pB.x - pA.x, pB.y - pA.y);
  } catch (err) {
    if (process.env.NODE_ENV !== 'production') {
      console.warn('[Sigma FA2 Calibration] Failed to convert screen pixels to graph distance:', err);
    }
    return 0;
  }
}

/**
 * Unified Layout and Interaction Controller.
 * Manages ForceAtlas2 layout states (initial settling, expansion relaxation, manual re-layout)
 * and interactive node dragging (with node pinned as fixed: true and FA2 actively responding).
 */
function GraphLayoutAndEventsController({
  graphRef,
  graphVersion,
  onSelectNode,
  onDeselect,
  setHoveredNode,
  onExpandNode,
  focusNodeId,
  rerunTrigger,
  setIsSettling,
  isDraggingRef,
  onLayoutFinished,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  graphRef: React.MutableRefObject<any>;
  graphVersion: number;
  onSelectNode: (nodeId: string) => void;
  onDeselect: () => void;
  setHoveredNode: (nodeId: string | null) => void;
  onExpandNode?: (nodeId: string) => void;
  focusNodeId?: string | null;
  rerunTrigger: number;
  setIsSettling: (s: boolean) => void;
  isDraggingRef: React.MutableRefObject<boolean>;
  onLayoutFinished?: () => void;
}) {
  const sigma = useSigma();
  const registerEvents = useRegisterEvents();
  const { reset, gotoNode } = useCamera();

  // Stable references for props to prevent re-triggering effects and accidental loop cancellation
  const onSelectNodeRef = useRef(onSelectNode);
  const onDeselectRef = useRef(onDeselect);
  const onExpandNodeRef = useRef(onExpandNode);
  const setHoveredNodeRef = useRef(setHoveredNode);
  const setIsSettlingRef = useRef(setIsSettling);
  const onLayoutFinishedRef = useRef(onLayoutFinished);

  useEffect(() => {
    onSelectNodeRef.current = onSelectNode;
    onDeselectRef.current = onDeselect;
    onExpandNodeRef.current = onExpandNode;
    setHoveredNodeRef.current = setHoveredNode;
    setIsSettlingRef.current = setIsSettling;
    onLayoutFinishedRef.current = onLayoutFinished;
  });

  // Layout lifecycle state refs
  const animFrameRef = useRef<number | null>(null);
  const modeRef = useRef<LayoutMode>('IDLE');
  const frameRef = useRef<number>(0);
  const stableCountRef = useRef<number>(0);
  const isFirstLoad = useRef<boolean>(true);
  const lastStopReasonRef = useRef<LayoutStopReason | null>(null);

  // Drag tracking refs
  const pointerDownNodeRef = useRef<string | null>(null);
  const pointerDownScreenPosRef = useRef<{ x: number; y: number } | null>(null);
  const lastClickTimeRef = useRef<number>(0);
  const lastClickNodeRef = useRef<string | null>(null);
  const dragSpringNeighborsRef = useRef<DragSpringNeighbor[]>([]);

  // Focus camera on searched/selected node without restarting layout
  useEffect(() => {
    if (!focusNodeId || !sigma) return;
    const g = sigma.getGraph();
    if (g && g.hasNode(focusNodeId)) {
      gotoNode(focusNodeId, { duration: 500 });
    }
  }, [focusNodeId, sigma, gotoNode]);

  // Main ForceAtlas2 layout step engine
  const startLayout = useCallback((newMode: LayoutMode) => {
    if (!sigma) return;
    const graph = sigma.getGraph();
    if (!graph || graph.order === 0) return;

    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
      if (modeRef.current !== 'IDLE') {
        lastStopReasonRef.current = 'STOP_REASON_CANCELLED';
        if (typeof window !== 'undefined') {
          (window as any).__FA2_LAST_STOP_REASON = 'STOP_REASON_CANCELLED';
        }
      }
    }

    modeRef.current = newMode;
    frameRef.current = 0;
    stableCountRef.current = 0;

    // Determine graph-coordinate scale corresponding to the DEFAULT Sigma camera view.
    // Convert FA2_MIN_SCREEN_GAP_PX into Graphology coordinate units once for this layout run.
    const minGapGraphUnits = getGraphDistanceForScreenPixels(sigma, FA2_MIN_SCREEN_GAP_PX);
    // In ForceAtlas2 (adjustSizes: true), collision distance = dist - (r1 + r2).
    // Adding half the desired gap to each node's collision radius ensures a minimum
    // separation of (r1 + extra) + (r2 + extra) = r1 + r2 + minGapGraphUnits.
    const extraRadiusPadding = minGapGraphUnits / 2;

    if (
      newMode === 'INITIAL_SETTLING' ||
      newMode === 'EXPANSION_SETTLING' ||
      newMode === 'MANUAL_RELAYOUT' ||
      newMode === 'POST_DRAG_SETTLING'
    ) {
      setIsSettlingRef.current(true);
    }

    const finishSettling = (
      reason: LayoutStopReason,
      frame: number,
      avgDisplacement: number,
      maxDisplacement: number
    ) => {
      lastStopReasonRef.current = reason;
      if (typeof window !== 'undefined') {
        (window as any).__FA2_LAST_STOP_REASON = reason;
        (window as any).__FA2_LAST_STOP_STATS = {
          iteration: frame,
          averageDisplacement: avgDisplacement,
          maximumDisplacement: maxDisplacement,
          consecutiveStableChecks: stableCountRef.current,
          stopReason: reason,
          mode: modeRef.current,
        };
        if ((window as any).__FA2_DEBUG) {
          (window as any).__FA2_DEBUG.stopReason = reason;
        }
      }
      if (process.env.NODE_ENV !== 'production') {
        if (reason === 'STOP_REASON_STABLE') {
          console.debug(
            `[ForceAtlas2] Layout converged cleanly (${reason}) at frame ${frame} (${modeRef.current}): avg=${avgDisplacement.toFixed(4)}, max=${maxDisplacement.toFixed(4)}`
          );
        } else if (reason === 'STOP_REASON_SAFETY_LIMIT') {
          console.warn(
            `[ForceAtlas2] Layout emergency safety limit reached (${reason}) at frame ${frame} (${modeRef.current}): avg=${avgDisplacement.toFixed(4)}, max=${maxDisplacement.toFixed(4)}`
          );
        }
      }

      const wasInitial = modeRef.current === 'INITIAL_SETTLING';
      modeRef.current = 'IDLE';
      setIsSettlingRef.current(false);
      onLayoutFinishedRef.current?.();
      animFrameRef.current = null;
      sigma.refresh();

      if (wasInitial && isFirstLoad.current) {
        isFirstLoad.current = false;
        reset({ duration: 400 });
      }
    };

    const step = () => {
      const g = sigma.getGraph();
      if (!g || g.order === 0) {
        modeRef.current = 'IDLE';
        setIsSettlingRef.current(false);
        animFrameRef.current = null;
        return;
      }

      const currentMode = modeRef.current;
      if (currentMode === 'IDLE') {
        setIsSettlingRef.current(false);
        animFrameRef.current = null;
        return;
      }

      frameRef.current++;
      const frame = frameRef.current;

      // ── DRAGGING (runs moderate FA2 step + temporary restoring spring force to directly connected neighbors) ──
      if (currentMode === 'DRAGGING') {
        // Step 1: Run standard ForceAtlas2 step for global layout consistency
        runFA2Step(g, 2, 1.25, false, extraRadiusPadding);

        // Step 2: Apply temporary spring force to directly connected neighbors
        const draggedNodeId = pointerDownNodeRef.current;
        const springs = dragSpringNeighborsRef.current;
        if (draggedNodeId && g.hasNode(draggedNodeId) && springs.length > 0) {
          const draggedX = g.getNodeAttribute(draggedNodeId, 'x');
          const draggedY = g.getNodeAttribute(draggedNodeId, 'y');

          for (let i = 0; i < springs.length; i++) {
            const { neighborId, restLength, weight } = springs[i];
            if (!g.hasNode(neighborId)) continue;
            // The dragged node or any explicitly pinned node must never be moved by spring
            if (g.getNodeAttribute(neighborId, 'fixed')) continue;

            const nX = g.getNodeAttribute(neighborId, 'x');
            const nY = g.getNodeAttribute(neighborId, 'y');
            const dx = draggedX - nX;
            const dy = draggedY - nY;
            const currentDist = Math.hypot(dx, dy);

            // Calculate edge extension beyond initial rest length
            const extension = currentDist - restLength;

            // Only apply restoring spring force when edge is stretched beyond rest length
            // When compressed (extension <= 0), let ForceAtlas2's normal repulsion handle separation
            if (extension > DRAG_SPRING_MIN_EXTENSION && currentDist > 0.001) {
              // Normalized unit vector pointing from neighbor toward the dragged node
              const ux = dx / currentDist;
              const uy = dy / currentDist;

              // Spring pull: F = k * extension * normalized_weight
              // Weight scale: baseline 1.0 (CONTAINS/DECLARES=2.0 -> 2x pull, CALLS/IMPORTS=0.5 -> 0.5x pull)
              const weightFactor = Math.max(0.2, weight);
              const rawDisplacement = DRAG_SPRING_STIFFNESS * extension * weightFactor;

              // Cap maximum spring displacement per frame to prevent oscillation or overshoot
              const clampedDisplacement = Math.min(rawDisplacement, DRAG_SPRING_MAX_DISPLACEMENT);

              g.setNodeAttribute(neighborId, 'x', nX + ux * clampedDisplacement);
              g.setNodeAttribute(neighborId, 'y', nY + uy * clampedDisplacement);
            }
          }
        }

        try {
          const container = typeof sigma.getContainer === 'function' ? sigma.getContainer() : null;
          if (!container || (container.offsetWidth > 0 && container.offsetHeight > 0)) {
            sigma.refresh();
          }
        } catch {
          // Ignore transient container resize / layout refresh errors
        }
        animFrameRef.current = requestAnimationFrame(step);
        return;
      }

      // ── SETTLING MODES (INITIAL_SETTLING, EXPANSION_SETTLING, MANUAL_RELAYOUT, POST_DRAG_SETTLING) ──
      // All modes share the exact same movement-based stability detection and emergency safety cap rule.
      if (
        currentMode === 'INITIAL_SETTLING' ||
        currentMode === 'EXPANSION_SETTLING' ||
        currentMode === 'MANUAL_RELAYOUT' ||
        currentMode === 'POST_DRAG_SETTLING'
      ) {
        if (currentMode === 'EXPANSION_SETTLING' && frame === 1) {
          // Unpin any existing nodes and clean expansion marker so all nodes participate in layout
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          g.forEachNode((id: string, attr: any) => {
            if (attr.isNewExpansion) {
              g.removeNodeAttribute(id, 'isNewExpansion');
            }
            if (attr.fixed && id !== pointerDownNodeRef.current) {
              g.setNodeAttribute(id, 'fixed', false);
            }
          });
        }

        // Run ForceAtlas2 step and measure non-fixed node displacement in Graphology coordinates
        const { avgDisplacement, maxDisplacement } = runFA2Step(g, 2, 2.5, true, extraRadiusPadding);

        // Movement-based stability check: BOTH average and maximum displacement must be below threshold
        const isStableThisFrame =
          avgDisplacement < STABLE_AVG_THRESHOLD &&
          maxDisplacement < STABLE_MAX_THRESHOLD;

        if (isStableThisFrame) {
          stableCountRef.current++;
        } else {
          stableCountRef.current = 0;
        }

        // Expose debug telemetry on window for inspection during settling
        if (typeof window !== 'undefined') {
          (window as any).__FA2_DEBUG = {
            iteration: frame,
            averageDisplacement: avgDisplacement,
            maximumDisplacement: maxDisplacement,
            consecutiveStableChecks: stableCountRef.current,
            currentMode,
            stopReason: null,
          };
        }

        // Periodic development logging
        if (process.env.NODE_ENV !== 'production' && (frame % 50 === 0 || isStableThisFrame)) {
          console.debug(
            `[ForceAtlas2 Settling] frame=${frame} (${currentMode}): avgD=${avgDisplacement.toFixed(4)}, maxD=${maxDisplacement.toFixed(4)}, stableChecks=${stableCountRef.current}/${REQUIRED_CONSECUTIVE_STABLE_CHECKS}`
          );
        }

        // Path A: Normal Termination via consecutive movement-based stability checks
        if (stableCountRef.current >= REQUIRED_CONSECUTIVE_STABLE_CHECKS) {
          finishSettling('STOP_REASON_STABLE', frame, avgDisplacement, maxDisplacement);
          return;
        }

        // Path B: Emergency Safety Cap (fallback ONLY to prevent infinite simulations)
        if (frame >= MAX_SAFETY_CAP_FRAMES) {
          finishSettling('STOP_REASON_SAFETY_LIMIT', frame, avgDisplacement, maxDisplacement);
          return;
        }

        // Active layout continues: refresh WebGL view and request next frame
        try {
          const container = typeof sigma.getContainer === 'function' ? sigma.getContainer() : null;
          if (!container || (container.offsetWidth > 0 && container.offsetHeight > 0)) {
            sigma.refresh();
          }
        } catch {
          // Ignore transient container resize / layout refresh errors
        }
        animFrameRef.current = requestAnimationFrame(step);
        return;
      }
    };

    animFrameRef.current = requestAnimationFrame(step);
  }, [sigma, reset]);

  // Layout RAF cleanup on unmount ONLY — React rerenders must NEVER cancel layout loop
  useEffect(() => {
    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
        lastStopReasonRef.current = 'STOP_REASON_UNMOUNTED';
        if (typeof window !== 'undefined') {
          (window as any).__FA2_LAST_STOP_REASON = 'STOP_REASON_UNMOUNTED';
        }
      }
    };
  }, []);

  // Handle graphVersion changes (initial load or expansion)
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || graph.order === 0) return;

    let hasNew = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    graph.forEachNode((_: string, attr: any) => {
      if (attr.isNewExpansion) hasNew = true;
    });

    if (hasNew) {
      startLayout('EXPANSION_SETTLING');
    } else {
      startLayout('INITIAL_SETTLING');
    }
  }, [graphVersion, graphRef, startLayout]);

  // Handle manual re-layout trigger
  useEffect(() => {
    if (rerunTrigger === 0) return;
    startLayout('MANUAL_RELAYOUT');
  }, [rerunTrigger, startLayout]);

  const lastNodeClickTimeRef = useRef<number>(0);

  // Handle click & double-click logic when pointer release is below drag threshold
  const handleNodeClick = useCallback((node: string) => {
    const now = Date.now();
    lastNodeClickTimeRef.current = now;
    const DOUBLE_CLICK_MS = 350;
    if (
      lastClickNodeRef.current === node &&
      now - lastClickTimeRef.current < DOUBLE_CLICK_MS
    ) {
      // Double click: expand node if expandable
      const graph = sigma.getGraph();
      if (graph && graph.hasNode(node)) {
        const expandable = graph.getNodeAttribute(node, 'expandable');
        if (expandable) {
          onExpandNodeRef.current?.(node);
        }
      }
      lastClickNodeRef.current = null;
      lastClickTimeRef.current = 0;
    } else {
      // Single click: select node
      lastClickTimeRef.current = now;
      lastClickNodeRef.current = node;
      onSelectNodeRef.current(node);
    }
  }, [sigma]);

  // Register Sigma pointer and stage events
  useEffect(() => {
    if (!sigma) return;

    registerEvents({
      downNode: (e) => {
        const graph = sigma.getGraph();
        if (!graph.hasNode(e.node)) return;

        pointerDownNodeRef.current = e.node;
        pointerDownScreenPosRef.current = { x: e.event.x, y: e.event.y };
        isDraggingRef.current = false;
      },

      clickNode: (e) => {
        lastNodeClickTimeRef.current = Date.now();
        if (!isDraggingRef.current) {
          handleNodeClick(e.node);
        }
      },

      moveBody: (e) => {
        const node = pointerDownNodeRef.current;
        if (!node) return;

        if (!isDraggingRef.current) {
          const startPos = pointerDownScreenPosRef.current;
          if (!startPos) return;
          const dist = Math.hypot(e.event.x - startPos.x, e.event.y - startPos.y);
          if (dist < DRAG_THRESHOLD_PX) {
            return; // Below threshold: still a potential click
          }

          // Crossed threshold: enter DRAGGING
          isDraggingRef.current = true;
          const graph = sigma.getGraph();
          if (graph.hasNode(node)) {
            graph.setNodeAttribute(node, 'fixed', true);

            // Record incident edges and initial rest lengths for temporary drag spring
            const springs: DragSpringNeighbor[] = [];
            const nodeX = graph.getNodeAttribute(node, 'x');
            const nodeY = graph.getNodeAttribute(node, 'y');

            graph.forEachNeighbor(node, (neighbor: string, attr: any) => {
              if (neighbor === node) return;
              const nX = attr.x ?? 0;
              const nY = attr.y ?? 0;
              const initialDist = Math.hypot(nodeX - nX, nodeY - nY);

              // Find maximum semantic weight among parallel edges between node and neighbor
              let maxWeight = 1.0;
              let foundEdge = false;
              graph.forEachEdge(node, neighbor, (_edge: string, edgeAttr: any) => {
                foundEdge = true;
                const w =
                  edgeAttr.weight ??
                  (edgeAttr.relType ? SEMANTIC_EDGE_WEIGHTS[edgeAttr.relType] : undefined) ??
                  SEMANTIC_EDGE_WEIGHTS.GENERIC ??
                  1.0;
                if (w > maxWeight) maxWeight = w;
              });

              if (!foundEdge) {
                maxWeight = SEMANTIC_EDGE_WEIGHTS.GENERIC ?? 1.0;
              }

              springs.push({
                neighborId: neighbor,
                restLength: Math.max(initialDist, 1.0),
                weight: maxWeight,
              });
            });

            dragSpringNeighborsRef.current = springs;
          }
          sigma.getCamera().disable();
          startLayout('DRAGGING');
        }

        // Dragging in progress: track cursor in graph space
        const currentPos = sigma.viewportToGraph(e.event);
        const graph = sigma.getGraph();
        if (graph.hasNode(node)) {
          graph.setNodeAttribute(node, 'x', currentPos.x);
          graph.setNodeAttribute(node, 'y', currentPos.y);
        }

        e.preventSigmaDefault();
      },

      upNode: () => {
        const node = pointerDownNodeRef.current;
        const wasDragging = isDraggingRef.current;

        pointerDownNodeRef.current = null;
        pointerDownScreenPosRef.current = null;
        isDraggingRef.current = false;
        dragSpringNeighborsRef.current = [];

        if (wasDragging) {
          sigma.getCamera().enable();
          const graph = sigma.getGraph();
          if (node && graph.hasNode(node)) {
            graph.setNodeAttribute(node, 'fixed', false);
          }
          startLayout('POST_DRAG_SETTLING');
        } else {
          // Normal click — select node
          if (node) {
            handleNodeClick(node);
          }
        }
      },

      upStage: () => {
        const node = pointerDownNodeRef.current;
        const wasDragging = isDraggingRef.current;

        pointerDownNodeRef.current = null;
        pointerDownScreenPosRef.current = null;
        isDraggingRef.current = false;
        dragSpringNeighborsRef.current = [];

        if (wasDragging) {
          sigma.getCamera().enable();
          const graph = sigma.getGraph();
          if (node && graph.hasNode(node)) {
            graph.setNodeAttribute(node, 'fixed', false);
          }
          startLayout('POST_DRAG_SETTLING');
        }
      },

      clickStage: () => {
        // Only deselect if this was not preceded by a node click within 200ms
        const timeSinceNodeClick = Date.now() - lastNodeClickTimeRef.current;
        if (!isDraggingRef.current && timeSinceNodeClick > 250) {
          onDeselectRef.current();
          lastClickNodeRef.current = null;
        }
      },

      enterNode: (e) => {
        setHoveredNodeRef.current(e.node);
      },

      leaveNode: () => {
        setHoveredNodeRef.current(null);
      },
    });

    // Safety fallback: if pointer is released outside canvas
    const handleGlobalRelease = () => {
      if (isDraggingRef.current) {
        const node = pointerDownNodeRef.current;
        pointerDownNodeRef.current = null;
        pointerDownScreenPosRef.current = null;
        isDraggingRef.current = false;
        dragSpringNeighborsRef.current = [];

        sigma.getCamera().enable();
        const graph = sigma.getGraph();
        if (node && graph.hasNode(node)) {
          graph.setNodeAttribute(node, 'fixed', false);
        }
        startLayout('POST_DRAG_SETTLING');
      } else {
        pointerDownNodeRef.current = null;
        pointerDownScreenPosRef.current = null;
        dragSpringNeighborsRef.current = [];
      }
    };

    window.addEventListener('pointerup', handleGlobalRelease);
    window.addEventListener('mouseup', handleGlobalRelease);

    return () => {
      window.removeEventListener('pointerup', handleGlobalRelease);
      window.removeEventListener('mouseup', handleGlobalRelease);
    };
  }, [registerEvents, sigma, startLayout, handleNodeClick]);

  return null;
}

/**
 * Handles WebGL-level property overrides for hover, selection, and neighbor highlighting.
 */
function VisualReducersController({
  selectedNodeId,
  hoveredNodeId,
  searchQuery,
  isDark,
}: {
  selectedNodeId: string | null;
  hoveredNodeId: string | null;
  searchQuery?: string;
  isDark: boolean;
}) {
  const sigma = useSigma();
  const setSettings = useSetSettings();

  useEffect(() => {
    if (!sigma) return;
    const graph = sigma.getGraph();

    const normalizedQuery = (searchQuery || '').trim().toLowerCase();

    // Mode 1: Search Query Active — SHOW ONLY NODES & THEIR CHILDREN (Connections)
    // When someone searches that key, show only nodes and its children that contain that keyword
    if (normalizedQuery) {
      const matchedSeedIds = new Set<string>();
      graph.forEachNode((id: string, attr: any) => {
        const label = (attr.label || '').toLowerCase();
        const rawNode = attr.rawNode || {};
        const file = (rawNode.file || '').toLowerCase();
        const fullName = (rawNode.full_name || '').toLowerCase();
        const rawType = (attr.rawType || '').toLowerCase();

        if (
          label.includes(normalizedQuery) ||
          file.includes(normalizedQuery) ||
          fullName.includes(normalizedQuery) ||
          rawType.includes(normalizedQuery) ||
          id.toLowerCase().includes(normalizedQuery)
        ) {
          matchedSeedIds.add(id);
        }
      });

      // Collect seed matches + all of their children (out-neighbors and direct connections)
      const visibleNodeIds = new Set<string>(matchedSeedIds);
      matchedSeedIds.forEach((seedId) => {
        if (graph.hasNode(seedId)) {
          // Add outgoing neighbors (children/dependencies) and neighbors
          graph.forEachNeighbor(seedId, (neighbor: string) => {
            visibleNodeIds.add(neighbor);
          });
        }
      });

      const activeEdgeColor = isDark ? '#38bdf8' : '#2563eb';

      setSettings({
        nodeReducer: (node, data) => {
          const res: any = { ...data };
          if (visibleNodeIds.has(node)) {
            res.hidden = false;
            if (matchedSeedIds.has(node)) {
              res.highlighted = true;
              res.forceLabel = true;
              res.zIndex = 15;
            } else {
              // Direct child / connection of matched node
              res.highlighted = false;
              res.zIndex = 5;
            }
          } else {
            // Strictly hide nodes that do not contain keyword or are not its children
            res.hidden = true;
            res.label = '';
            res.zIndex = 0;
          }
          return res;
        },
        edgeReducer: (edge, data) => {
          const res: any = { ...data };
          const ext = graph.extremities(edge);
          // Show edge only if at least one endpoint is a matched seed, and both are in visible set
          const connectsSeed = matchedSeedIds.has(ext[0]) || matchedSeedIds.has(ext[1]);
          if (connectsSeed && visibleNodeIds.has(ext[0]) && visibleNodeIds.has(ext[1])) {
            res.hidden = false;
            res.size = 1.8;
            res.color = activeEdgeColor;
            res.zIndex = 5;
          } else {
            res.hidden = true;
            res.zIndex = 0;
          }
          return res;
        },
      });
      return;
    }

    // Mode 2: Selected / Clicked Node — ISOLATE & GLOW
    // When a node is selected (by click), strictly hide all unrelated nodes,
    // show only direct connections, and mark the clicked node with isClickedGlow.
    if (selectedNodeId && graph.hasNode(selectedNodeId)) {
      const neighborSet = new Set(graph.neighbors(selectedNodeId));
      const activeEdgeColor = isDark ? '#38bdf8' : '#2563eb';

      setSettings({
        nodeReducer: (node, data) => {
          const res: any = { ...data };
          if (node === selectedNodeId) {
            res.highlighted = true;
            res.isClickedGlow = true;
            res.size = Math.min(28, (data.size || 8) * 1.45);
            res.forceLabel = true;
            res.zIndex = 20;
          } else if (neighborSet.has(node)) {
            res.highlighted = true;
            res.forceLabel = true;
            res.zIndex = 10;
          } else {
            // Strictly hide all non-connected nodes on click
            res.hidden = true;
            res.label = '';
            res.zIndex = 0;
          }
          return res;
        },
        edgeReducer: (edge, data) => {
          const res: any = { ...data };
          const ext = graph.extremities(edge);
          const isConnected = ext[0] === selectedNodeId || ext[1] === selectedNodeId;
          if (isConnected) {
            res.size = 2.2;
            res.color = activeEdgeColor;
            res.zIndex = 10;
          } else {
            // Hide all non-connected edges on click
            res.hidden = true;
            res.zIndex = 0;
          }
          return res;
        },
      });
      return;
    }

    // Mode 3: Hovered Node Only — HIGHLIGHT CONNECTIONS (Do NOT hide others)
    // On hover, keep the full graph visible: highlight the hovered node & its neighbors,
    // dim unrelated nodes, and highlight incident edges.
    if (hoveredNodeId && graph.hasNode(hoveredNodeId)) {
      const neighborSet = new Set(graph.neighbors(hoveredNodeId));
      const activeEdgeColor = isDark ? '#38bdf8' : '#2563eb';
      const dimmedNodeColor = isDark ? '#1e293b' : '#e2e8f0';

      setSettings({
        nodeReducer: (node, data) => {
          const res: any = { ...data };
          if (node === hoveredNodeId) {
            res.highlighted = true;
            res.size = Math.min(24, (data.size || 8) * 1.3);
            res.forceLabel = true;
            res.zIndex = 15;
          } else if (neighborSet.has(node)) {
            res.highlighted = true;
            res.forceLabel = true;
            res.zIndex = 8;
          } else {
            // Dimmed but NOT hidden on hover
            res.label = '';
            res.color = dimmedNodeColor;
            res.zIndex = 0;
          }
          return res;
        },
        edgeReducer: (edge, data) => {
          const res: any = { ...data };
          const ext = graph.extremities(edge);
          const isConnected = ext[0] === hoveredNodeId || ext[1] === hoveredNodeId;
          if (isConnected) {
            res.size = 2.0;
            res.color = activeEdgeColor;
            res.zIndex = 10;
          } else {
            res.hidden = true;
            res.zIndex = 0;
          }
          return res;
        },
      });
      return;
    }

    // Mode 4: Normal / Idle State — Full Graph
    setSettings({
      nodeReducer: null,
      edgeReducer: null,
    });
  }, [sigma, setSettings, selectedNodeId, hoveredNodeId, searchQuery, isDark]);

  return null;
}



// ==========================================
// Dynamic Screen-Space Node Overlap Correction
// ==========================================
export const CAMERA_INACTIVITY_DEBOUNCE_MS = 3000;
export const COLLISION_GAP_PX = 2;
export const MAX_COLLISION_PASSES = 5;

/**
 * Controller that dynamically detects and resolves circle-circle node overlaps
 * in viewport/screen coordinates when the Sigma camera has been idle for 3 seconds.
 * Corrected positions are converted back to Graphology graph space without restarting ForceAtlas2.
 */
function NodeOverlapCorrectionController({
  isSettling,
  isDraggingRef,
  layoutVersion,
}: {
  isSettling: boolean;
  isDraggingRef: React.MutableRefObject<boolean>;
  layoutVersion: number;
}) {
  const sigma = useSigma();
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const runCorrection = useCallback(() => {
    if (!sigma) return;
    const graph = sigma.getGraph();
    if (!graph || graph.order === 0) return;

    // Do not run while layout is settling or while a node is actively being dragged
    if (isSettling || isDraggingRef.current) return;

    interface NodeScreenData {
      id: string;
      screenX: number;
      screenY: number;
      radius: number;
    }

    const nodesData: NodeScreenData[] = [];

    // 1. Convert current Graphology positions to viewport coordinates and get rendered screen radius
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    graph.forEachNode((id: string, attr: any) => {
      if (attr.hidden) return;
      const screenPos = sigma.graphToViewport({ x: attr.x, y: attr.y });
      const radius = sigma.scaleSize(attr.size || 1);
      nodesData.push({
        id,
        screenX: screenPos.x,
        screenY: screenPos.y,
        radius,
      });
    });

    const count = nodesData.length;
    if (count <= 1) return;

    let anyDisplaced = false;

    // 2. Perform bounded iterative pairwise collision resolution in screen space
    for (let pass = 0; pass < MAX_COLLISION_PASSES; pass++) {
      let passCollisions = 0;

      for (let i = 0; i < count; i++) {
        const nodeA = nodesData[i];
        for (let j = i + 1; j < count; j++) {
          const nodeB = nodesData[j];

          const dx = nodeB.screenX - nodeA.screenX;
          const dy = nodeB.screenY - nodeA.screenY;
          const dist = Math.hypot(dx, dy);
          const requiredDist = nodeA.radius + nodeB.radius + COLLISION_GAP_PX;

          if (dist < requiredDist) {
            passCollisions++;
            anyDisplaced = true;

            const overlap = requiredDist - dist;
            let nx = 0;
            let ny = 0;

            if (dist > 1e-4) {
              nx = dx / dist;
              ny = dy / dist;
            } else {
              // Centers are coincident: separate in arbitrary deterministic direction
              const angle = ((i * 31 + j * 17) % 360) * (Math.PI / 180);
              nx = Math.cos(angle);
              ny = Math.sin(angle);
            }

            // Distribute displacement inversely proportional to radii (or proportional to the other node's size)
            const sumRadii = nodeA.radius + nodeB.radius;
            const weightA = sumRadii > 0 ? nodeB.radius / sumRadii : 0.5;
            const weightB = sumRadii > 0 ? nodeA.radius / sumRadii : 0.5;

            nodeA.screenX -= nx * overlap * weightA;
            nodeA.screenY -= ny * overlap * weightA;
            nodeB.screenX += nx * overlap * weightB;
            nodeB.screenY += ny * overlap * weightB;
          }
        }
      }

      // Early exit if no overlaps detected in this pass
      if (passCollisions === 0) {
        break;
      }
    }

    // 3. If any nodes were adjusted, convert corrected screen positions back to graph space
    if (anyDisplaced) {
      for (let i = 0; i < count; i++) {
        const node = nodesData[i];
        const graphPos = sigma.viewportToGraph({ x: node.screenX, y: node.screenY });
        graph.setNodeAttribute(node.id, 'x', graphPos.x);
        graph.setNodeAttribute(node.id, 'y', graphPos.y);
      }
      sigma.refresh();
    }
  }, [sigma, isSettling, isDraggingRef]);

  // Stable ref for isSettling to avoid dropping camera events or tearing down timers on state transitions
  const isSettlingRef = useRef(isSettling);
  useEffect(() => {
    isSettlingRef.current = isSettling;
  }, [isSettling]);

  // Listen to camera 'updated' event and debounce 3 seconds of camera inactivity
  useEffect(() => {
    if (!sigma) return;
    const camera = sigma.getCamera();

    const handleCameraUpdate = () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }

      // If actively dragging or settling, do not schedule overlap correction
      if (isDraggingRef.current || isSettlingRef.current) {
        return;
      }

      timerRef.current = setTimeout(() => {
        runCorrection();
        timerRef.current = null;
      }, CAMERA_INACTIVITY_DEBOUNCE_MS);
    };

    camera.on('updated', handleCameraUpdate);

    return () => {
      camera.removeListener('updated', handleCameraUpdate);
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [sigma, isDraggingRef, runCorrection]);

  // Trigger overlap correction after every graph layout change / settling completion
  useEffect(() => {
    if (isSettling || isDraggingRef.current) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(() => {
      runCorrection();
      timerRef.current = null;
    }, CAMERA_INACTIVITY_DEBOUNCE_MS);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isSettling, layoutVersion, isDraggingRef, runCorrection]);

  return null;
}

/**
 * Floating canvas toolbar.
 */
function GraphControlsBar({
  isSettling,
  onRerunLayout,
}: {
  isSettling: boolean;
  onRerunLayout: () => void;
}) {
  const { zoomIn, zoomOut, reset } = useCamera();
  return (
    <div className="absolute bottom-5 left-5 z-10 flex items-center gap-1.5 p-1.5 rounded-xl bg-white/90 dark:bg-slate-900/90 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 backdrop-blur-md shadow-xl transition-colors">
      <button
        onClick={() => zoomIn({ duration: 200, factor: 1.5 })}
        className="p-2 rounded-lg text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        title="Zoom In"
      >
        <ZoomIn className="w-4 h-4" />
      </button>

      <button
        onClick={() => zoomOut({ duration: 200, factor: 1.5 })}
        className="p-2 rounded-lg text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        title="Zoom Out"
      >
        <ZoomOut className="w-4 h-4" />
      </button>

      <button
        onClick={() => reset({ duration: 300 })}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium transition-colors"
        title="Reset Zoom & Camera View"
      >
        <Maximize2 className="w-4 h-4" />
        <span>Reset View</span>
      </button>

      <div className="w-[1px] h-4 bg-slate-200 dark:bg-slate-800 mx-1" />

      <button
        onClick={onRerunLayout}
        disabled={isSettling}
        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
          isSettling
            ? 'bg-blue-600/20 text-blue-600 dark:text-blue-300 cursor-not-allowed border border-blue-400/30'
            : 'bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-slate-700'
        }`}
        title="Recalculate ForceAtlas2 Layout"
      >
        <RotateCcw className={`w-3.5 h-3.5 ${isSettling ? 'animate-spin text-blue-500' : ''}`} />
        <span>{isSettling ? 'Settling...' : 'Re-layout'}</span>
      </button>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// MAIN SIGMA CANVAS COMPONENT
// ──────────────────────────────────────────────────────────────────────────

export default function SigmaKnowledgeGraphCanvas({
  graphRef,
  graphVersion,
  selectedNodeId,
  onSelectNode,
  onExpandNode,
  activeRelFilters,
  focusNodeId,
  searchQuery,
}: SigmaKnowledgeGraphCanvasProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme !== 'light';
  const bgColor = isDark ? '#020617' : '#f8fafc';

  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [isSettling, setIsSettling] = useState(false);
  const [rerunTrigger, setRerunTrigger] = useState(0);
  const [layoutVersion, setLayoutVersion] = useState(0);
  const isDraggingRef = useRef<boolean>(false);



  // Custom node label drawing with high-contrast pill background
  const drawNodeLabel = useCallback(
    (context: CanvasRenderingContext2D, data: any, settings: any) => {
      if (!data.label) return;
      const size = settings.labelSize || 12;
      const font = settings.labelFont || 'sans-serif';
      const weight = settings.labelWeight || '600';
      context.font = `${weight} ${size}px ${font}`;

      const text = String(data.label);
      const textWidth = context.measureText(text).width;
      const paddingX = 5;
      const paddingY = 2;
      const boxHeight = size + paddingY * 2;
      const boxWidth = textWidth + paddingX * 2;
      const x = data.x + data.size + 4;
      const y = data.y - boxHeight / 2;

      // ── GLOW AURA FOR CLICKED / SELECTED NODE ──
      if (data.isClickedGlow) {
        context.save();
        // Outer ambient glow ring
        context.beginPath();
        context.arc(data.x, data.y, data.size + 10, 0, Math.PI * 2);
        context.fillStyle = isDark ? 'rgba(56, 189, 248, 0.22)' : 'rgba(37, 99, 235, 0.20)';
        context.fill();

        // Inner luminous pulse ring
        context.beginPath();
        context.arc(data.x, data.y, data.size + 5, 0, Math.PI * 2);
        context.fillStyle = isDark ? 'rgba(56, 189, 248, 0.40)' : 'rgba(37, 99, 235, 0.35)';
        context.strokeStyle = isDark ? '#38bdf8' : '#2563eb';
        context.lineWidth = 2.5;
        context.shadowColor = isDark ? '#38bdf8' : '#2563eb';
        context.shadowBlur = 14;
        context.stroke();
        context.fill();
        context.restore();
      }

      // Draw contrast pill
      context.fillStyle = isDark ? 'rgba(15, 23, 42, 0.88)' : 'rgba(255, 255, 255, 0.92)';
      context.strokeStyle = data.isClickedGlow
        ? (isDark ? '#38bdf8' : '#2563eb')
        : (isDark ? 'rgba(51, 65, 85, 0.7)' : 'rgba(203, 213, 225, 0.9)');
      context.lineWidth = data.isClickedGlow ? 1.8 : 1;
      context.beginPath();
      if (typeof (context as any).roundRect === 'function') {
        (context as any).roundRect(x, y, boxWidth, boxHeight, 4);
      } else {
        context.rect(x, y, boxWidth, boxHeight);
      }
      context.fill();
      context.stroke();

      context.fillStyle = isDark ? '#f8fafc' : '#0f172a';
      context.fillText(text, x + paddingX, data.y + size / 3);

      // Draw expand indicator on expandable nodes that haven't been expanded
      if (data.expandable && !data.expanded) {
        context.fillStyle = isDark ? '#f97316' : '#ea580c';
        context.font = `bold ${size - 2}px sans-serif`;
        context.fillText('⊕', x + boxWidth + 3, data.y + size / 3);
      }
    },
    [isDark]
  );

  // Custom node hover drawing
  const drawNodeHover = useCallback(
    (context: CanvasRenderingContext2D, data: any, settings: any) => {
      if (!data.label) return;
      const size = (settings.labelSize || 12) + 1;
      const font = settings.labelFont || 'sans-serif';
      context.font = `700 ${size}px ${font}`;

      const text = String(data.label);
      const textWidth = context.measureText(text).width;
      const paddingX = 6;
      const paddingY = 3;
      const boxHeight = size + paddingY * 2;
      const boxWidth = textWidth + paddingX * 2;
      const x = data.x + data.size + 5;
      const y = data.y - boxHeight / 2;

      context.fillStyle = isDark ? 'rgba(30, 41, 59, 0.96)' : 'rgba(255, 255, 255, 0.98)';
      context.strokeStyle = data.expandable
        ? isDark ? '#f97316' : '#ea580c'
        : isDark ? '#38bdf8' : '#2563eb';
      context.lineWidth = 1.5;
      context.beginPath();
      if (typeof (context as any).roundRect === 'function') {
        (context as any).roundRect(x, y, boxWidth, boxHeight, 5);
      } else {
        context.rect(x, y, boxWidth, boxHeight);
      }
      context.fill();
      context.stroke();

      context.fillStyle = isDark ? '#ffffff' : '#0f172a';
      context.fillText(text, x + paddingX, data.y + size / 3);
    },
    [isDark]
  );

  // Sigma settings
  const sigmaSettings = useMemo(
    () => ({
      renderLabels: true,
      renderEdgeLabels: false,
      labelRenderedSizeThreshold: 6,
      labelDensity: 0.8,
      labelGridCellSize: 80,
      labelFont: 'JetBrains Mono, Inter, system-ui, sans-serif',
      labelSize: 12,
      labelWeight: '600',
      labelColor: { color: isDark ? '#f8fafc' : '#0f172a' },
      defaultDrawNodeLabel: drawNodeLabel,
      defaultDrawNodeHover: drawNodeHover,
      defaultNodeType: 'circle',
      defaultEdgeType: 'arrow',
      minEdgeThickness: 1.0,
      hideEdgesOnMove: true,
      hideLabelsOnMove: false,
      enableCameraZooming: true,
      enableCameraPanning: true,
      enableCameraRotation: false,
      zIndex: true,
      stagePadding: 50,
      autoRescale: true,
      allowInvalidContainer: true,
    }),
    [isDark, drawNodeLabel, drawNodeHover]
  );

  const handleDeselect = useCallback(() => onSelectNode(null), [onSelectNode]);

  return (
    <div
      className="relative w-full h-full overflow-hidden transition-colors duration-200"
      style={
        {
          backgroundColor: bgColor,
          '--sigma-background-color': bgColor,
        } as React.CSSProperties
      }
    >
      <style>{`
        .react-sigma,
        .sigma-container {
          background-color: ${bgColor} !important;
        }
        .sigma-container canvas {
          background-color: transparent !important;
        }
      `}</style>

      {isSettling && (
        <div className="absolute top-4 left-4 z-10 flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/90 dark:bg-slate-900/90 border border-blue-400/40 text-blue-600 dark:text-blue-400 text-xs font-mono backdrop-blur-md shadow-lg animate-pulse transition-colors">
          <Sparkles className="w-3.5 h-3.5 text-blue-500 animate-spin" />
          <span>ForceAtlas2 settling graph layout...</span>
        </div>
      )}

      {graphRef.current && (
      <SigmaContainer
        graph={graphRef.current}
        settings={sigmaSettings}
        className="w-full h-full"
      >
        <GraphLayoutAndEventsController
          graphRef={graphRef}
          graphVersion={graphVersion}
          onSelectNode={onSelectNode}
          onDeselect={handleDeselect}
          setHoveredNode={setHoveredNodeId}
          onExpandNode={onExpandNode}
          focusNodeId={focusNodeId}
          rerunTrigger={rerunTrigger}
          setIsSettling={setIsSettling}
          isDraggingRef={isDraggingRef}
          onLayoutFinished={() => setLayoutVersion((v) => v + 1)}
        />
        <NodeOverlapCorrectionController
          isSettling={isSettling}
          isDraggingRef={isDraggingRef}
          layoutVersion={layoutVersion}
        />
        <VisualReducersController
          selectedNodeId={selectedNodeId}
          hoveredNodeId={hoveredNodeId}
          searchQuery={searchQuery}
          isDark={isDark}
        />
        <GraphControlsBar
          isSettling={isSettling}
          onRerunLayout={() => setRerunTrigger((prev) => prev + 1)}
        />
      </SigmaContainer>
      )}
    </div>
  );
}

