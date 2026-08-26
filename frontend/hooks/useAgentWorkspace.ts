"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AgentRunRecord,
  AgentWorkspaceView,
  ApprovalRequestItem,
  ConnectionStatus,
  EventStreamItem,
  ImplementationPlanData,
  PlanTaskItem,
  WorkspaceChangesData,
  WorkspaceSnapshot,
} from "@/types/workspace";

interface UseAgentWorkspaceOptions {
  initialRunId?: string | null;
  repositoryId?: string;
}

export function useAgentWorkspace({
  initialRunId = null,
  repositoryId = "default",
}: UseAgentWorkspaceOptions = {}) {
  const [runId, setRunId] = useState<string | null>(initialRunId);
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [planHistory, setPlanHistory] = useState<ImplementationPlanData[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<AgentWorkspaceView>("chat");
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("DISCONNECTED");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const processedEventIds = useRef<Set<string>>(new Set());
  const lastSequence = useRef<number>(0);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const addPlanToHistory = useCallback((plan: ImplementationPlanData) => {
    if (!plan) return;
    setPlanHistory((prev) => {
      const exists = prev.some(
        (p) => (p.plan_id && p.plan_id === plan.plan_id) || (p.version && p.version === plan.version)
      );
      if (exists) {
        return prev.map((p) =>
          (p.plan_id && p.plan_id === plan.plan_id) || (p.version && p.version === plan.version) ? plan : p
        );
      }
      return [plan, ...prev];
    });
  }, []);

  // 1. Snapshot Fetcher (Authoritative Hydration & Reconnect Reconciliation)
  const fetchSnapshot = useCallback(async (targetRunId: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const snapshotUrl = `/api/v1/agent/runs/${targetRunId}/workspace`;
      console.log(`[Workspace] Fetching snapshot from: ${snapshotUrl}`);
      const res = await fetch(snapshotUrl);
      console.log(`[Workspace] Response status: ${res.status}`);
      if (!res.ok) {
        const errorText = await res.text();
        console.error(`[Workspace] Error response: ${errorText}`);
        throw new Error(`Failed to load workspace snapshot: ${res.statusText}`);
      }
      const data: WorkspaceSnapshot = await res.json();
      console.log(`[Workspace] Received snapshot:`, {
        runId: data.run?.id,
        currentState: data.run?.current_state,
        planId: data.plan?.plan_id,
        planStatus: data.plan?.status,
        latestEventsCount: data.latest_events?.length || 0,
      });
      setSnapshot(data);

      if (data.plan) {
        addPlanToHistory(data.plan);
      }

      // Fetch plan history from backend
      try {
        const historyRes = await fetch(`/api/v1/agent/runs/${targetRunId}/plan/history`);
        if (historyRes.ok) {
          const historyData: ImplementationPlanData[] = await historyRes.json();
          if (Array.isArray(historyData)) {
            historyData.forEach((plan) => addPlanToHistory(plan));
          }
        }
      } catch (historyErr) {
        console.warn("Failed to fetch plan history from backend:", historyErr);
      }

      // Re-seed processed events
      if (data.latest_events && Array.isArray(data.latest_events)) {
        data.latest_events.forEach((e) => {
          if (e.event_id) processedEventIds.current.add(e.event_id);
          if (e.sequence && e.sequence > lastSequence.current) {
            lastSequence.current = e.sequence;
          }
        });
      }

      // Default active file from changes or active task if not selected
      if (!activeFile) {
        if (data.changes?.modified_files?.length) {
          setActiveFile(data.changes.modified_files[0]);
        } else if (data.active_task?.affected_files?.length) {
          setActiveFile(data.active_task.affected_files[0]);
        }
      }
      return data;
    } catch (err: any) {
      console.error("Workspace snapshot error:", err);
      setError(err.message || "Failed to load workspace snapshot");
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [activeFile, addPlanToHistory]);

  // 2. Connect SSE Stream
  const connectSSE = useCallback((targetRunId: string) => {
    console.log(`[SSE] Connecting to stream for run: ${targetRunId}`);
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setConnectionStatus("CONNECTING" as ConnectionStatus);
    const esUrl = `/api/v1/agent/runs/${targetRunId}/events/stream`;
    console.log(`[SSE] Opening EventSource at: ${esUrl}`);
    const es = new EventSource(esUrl);
    eventSourceRef.current = es;

    es.onopen = () => {
      console.log(`[SSE] CONNECTED to stream for run: ${targetRunId}`);
      setConnectionStatus("CONNECTED");
    };

    es.onmessage = (event) => {
      console.log(`[SSE] Received message from stream`);
      try {
        if (!event.data || event.data.trim() === "") {
          console.log(`[SSE] Empty message data, skipping`);
          return;
        }
        console.log(`[SSE] Message data:`, event.data.substring(0, 200));
        const payload: EventStreamItem = JSON.parse(event.data);
        console.log(`[SSE] Parsed event type: ${payload.event_type}, sequence: ${payload.sequence}`);

        // Deduplication Guardrail
        if (payload.event_id && processedEventIds.current.has(payload.event_id)) {
          return;
        }
        if (payload.sequence && payload.sequence <= lastSequence.current) {
          return;
        }

        if (payload.event_id) processedEventIds.current.add(payload.event_id);
        if (payload.sequence) lastSequence.current = payload.sequence;

        // Apply Real-Time State Progression
        setSnapshot((prev) => {
          if (!prev) return prev;

          const updatedEvents = [...(prev.latest_events || []), payload];
          let updatedRun = { ...prev.run };
          let updatedApprovals = [...prev.pending_approvals];

          // Handle state-affecting events
          if (payload.event_type === "STATE_TRANSITION" && payload.payload?.to_state) {
            updatedRun.current_state = payload.payload.to_state;
          } else if (payload.event_type === "CANCELLATION_COMPLETED") {
            updatedRun.current_state = "CANCELLED";
            updatedRun.cancellation_reason = payload.payload?.reason || "Cancelled by user";
          } else if (payload.event_type === "ACTION_APPROVAL_REQUESTED" && payload.payload?.approval_request_id) {
            // Re-fetch snapshot to get typed approval detail
            fetchSnapshot(targetRunId);
          } else if (payload.event_type === "ACTION_APPROVED" || payload.event_type === "ACTION_REJECTED") {
            const apprId = payload.payload?.approval_request_id;
            if (apprId) {
              updatedApprovals = updatedApprovals.filter((a) => a.id !== apprId);
            }
          }

          return {
            ...prev,
            run: updatedRun,
            pending_approvals: updatedApprovals,
            latest_events: updatedEvents,
          };
        });

        // Trigger snapshot refresh on key milestones and execution activity
        const SNAPSHOT_REFRESH_EVENTS = [
          "PLAN_READY_FOR_APPROVAL",
          "PLAN_APPROVED",
          "TASK_STARTED",
          "NEXT_TASK_SELECTED",
          "TASK_EXECUTION_COMPLETED",
          "TASK_EXECUTION_FAILED",
          "TASK_VERIFYING",
          "TASK_PASSED",
          "TASK_COMPLETED",
          "TASK_FAILED",
          "TASK_BLOCKED",
          "FILE_WRITTEN",
          "TOOL_CALL_STARTED",
          "TOOL_CALL_COMPLETED",
          "VERIFICATION_COMPLETED",
          "REPAIR_REVERIFY_COMPLETED",
          "RUN_COMPLETED",
          "RUN_FAILED",
        ];
        if (SNAPSHOT_REFRESH_EVENTS.includes(payload.event_type)) {
          fetchSnapshot(targetRunId);
        }
      } catch (err) {
        console.warn("Error parsing SSE event:", err);
      }
    };

    es.onerror = () => {
      setConnectionStatus("RECONNECTING");
      if (es.readyState === EventSource.CLOSED) {
        // Reconnect after brief backoff
        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(async () => {
          const fresh = await fetchSnapshot(targetRunId);
          if (fresh) {
            connectSSE(targetRunId);
          } else {
            setConnectionStatus("DISCONNECTED");
          }
        }, 3000);
      }
    };
  }, [fetchSnapshot]);

  // 3. Hydrate and Start Stream on Run ID change
  useEffect(() => {
    if (!runId) return;

    fetchSnapshot(runId).then((data) => {
      if (data) {
        connectSSE(runId);
      }
    });

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [runId, fetchSnapshot, connectSSE]);

  // 4. Action Handlers (strictly presentation -> backend requests)

  const startRun = async (requirement: string) => {
    try {
      setIsLoading(true);
      setError(null);
      console.log(`[Run] Starting new run with requirement: ${requirement}`);
      const res = await fetch("/api/v1/agent/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repository_id: repositoryId,
          user_requirement: requirement,
        }),
      });
      console.log(`[Run] Create run response status: ${res.status}`);
      if (!res.ok) {
        const errData = await res.json();
        console.error(`[Run] Create run error:`, errData);
        throw new Error(errData.detail || "Failed to start agent run");
      }
      const newRun: AgentRunRecord = await res.json();
      console.log(`[Run] Created run with ID: ${newRun.id}, state: ${newRun.current_state}`);
      processedEventIds.current.clear();
      lastSequence.current = 0;
      setRunId(newRun.id);
      return newRun;
    } catch (err: any) {
      console.error(`[Run] Error:`, err);
      setError(err.message || "Failed to start run");
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const approvePlan = async () => {
    if (!runId) {
      console.error(`[Approve] No runId available`);
      return;
    }
    try {
      console.log(`[Approve] Approving plan for run: ${runId}`);
      // Approve the plan and start execution (both done by the endpoint)
      const approveUrl = `/api/v1/agent/runs/${runId}/plan/approve`;
      console.log(`[Approve] POST to: ${approveUrl}`);
      const approveRes = await fetch(approveUrl, { method: "POST" });
      console.log(`[Approve] Response status: ${approveRes.status}`);
      if (!approveRes.ok) {
        const errorText = await approveRes.text();
        console.error(`[Approve] Error response:`, errorText);
        throw new Error(`Approval failed (${approveRes.status}): ${errorText}`);
      }
      console.log(`[Approve] Plan approved successfully for run: ${runId}`);

      // Refresh snapshot to show updated state
      console.log(`[Approve] Fetching updated snapshot...`);
      await fetchSnapshot(runId);
      console.log(`[Approve] Snapshot refreshed`);
    } catch (err: any) {
      console.error(`[Approve] Error:`, err);
      setError(err.message || "Plan approval failed");
      console.error("Approval error:", err);
    }
  };

  const revisePlan = async (feedback: string) => {
    try {
      setIsLoading(true);
      setError(null);
      let revisedPlan: ImplementationPlanData | null = null;
      if (runId) {
        const res = await fetch(`/api/v1/agent/runs/${runId}/plan/revise`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feedback }),
        });
        if (res.ok) {
          revisedPlan = await res.json();
        }
      }
      if (!revisedPlan) {
        const res = await fetch(`/api/v1/agent/classify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            requirement: `Review feedback modification: ${feedback}`,
            repository_id: repositoryId,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          revisedPlan = data.plan;
        }
      }
      if (revisedPlan) {
        addPlanToHistory(revisedPlan);
        if (runId) await fetchSnapshot(runId);
      }
      return revisedPlan;
    } catch (err: any) {
      setError(err.message || "Failed to revise plan");
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const rejectPlan = async (reason?: string) => {
    if (!runId) return;
    try {
      const res = await fetch(`/api/v1/agent/runs/${runId}/plan/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason || "User requested plan revision" }),
      });
      if (!res.ok) throw new Error("Failed to reject plan");
      await fetchSnapshot(runId);
    } catch (err: any) {
      setError(err.message || "Plan rejection failed");
    }
  };

  const approveAction = async (approvalId: string) => {
    try {
      const res = await fetch(`/api/v1/agent/approvals/${approvalId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolved_by: "human_user" }),
      });
      if (!res.ok) throw new Error("Failed to approve action");
      if (runId) await fetchSnapshot(runId);
    } catch (err: any) {
      setError(err.message || "Action approval failed");
    }
  };

  const rejectAction = async (approvalId: string, reason: string) => {
    try {
      const res = await fetch(`/api/v1/agent/approvals/${approvalId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason, resolved_by: "human_user" }),
      });
      if (!res.ok) throw new Error("Failed to reject action");
      if (runId) await fetchSnapshot(runId);
    } catch (err: any) {
      setError(err.message || "Action rejection failed");
    }
  };

  const cancelRun = async (reason?: string) => {
    if (!runId) return;
    try {
      const res = await fetch(`/api/v1/agent/runs/${runId}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason || "User requested stop" }),
      });
      if (!res.ok) throw new Error("Failed to cancel run");
      await fetchSnapshot(runId);
    } catch (err: any) {
      setError(err.message || "Cancellation failed");
    }
  };

  // 5. Compute Monaco Editor State Transition
  // RUNNING/AWAITING_APPROVAL/VERIFYING/REPAIRING -> READ_ONLY
  // BLOCKED -> EDITABLE
  // COMPLETED/CANCELLED -> READ_ONLY
  const currentState = snapshot?.run?.current_state || "IDLE";
  const editorMode: "read-only" | "editable" = currentState === "BLOCKED" ? "editable" : "read-only";

  return {
    runId,
    setRunId,
    snapshot,
    planHistory,
    selectedPlanId,
    setSelectedPlanId,
    addPlanToHistory,
    activeView,
    setActiveView,
    activeFile,
    setActiveFile,
    connectionStatus,
    editorMode,
    isLoading,
    error,
    startRun,
    approvePlan,
    rejectPlan,
    revisePlan,
    approveAction,
    rejectAction,
    cancelRun,
    refreshSnapshot: () => runId && fetchSnapshot(runId),
  };
}
