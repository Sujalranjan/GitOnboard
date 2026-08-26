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
      const res = await fetch(`/api/v1/agent/runs/${targetRunId}/workspace`);
      if (!res.ok) {
        throw new Error(`Failed to load workspace snapshot: ${res.statusText}`);
      }
      const data: WorkspaceSnapshot = await res.json();
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
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setConnectionStatus("CONNECTING" as ConnectionStatus);
    const es = new EventSource(`/api/v1/agent/runs/${targetRunId}/events/stream`);
    eventSourceRef.current = es;

    es.onopen = () => {
      setConnectionStatus("CONNECTED");
    };

    es.onmessage = (event) => {
      try {
        if (!event.data || event.data.trim() === "") return;
        const payload: EventStreamItem = JSON.parse(event.data);

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

        // Trigger snapshot refresh on key milestones
        // Note: These event types are defined in backend/agent/events.py SNAPSHOT_REFRESH_TRIGGERS
        const SNAPSHOT_REFRESH_EVENTS = [
          "PLAN_READY_FOR_APPROVAL",
          "PLAN_APPROVED",
          "TASK_COMPLETED",
          "TASK_FAILED",
          "VERIFICATION_COMPLETED",
          "REPAIR_REVERIFY_COMPLETED",
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
      const res = await fetch("/api/v1/agent/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repository_id: repositoryId,
          user_requirement: requirement,
        }),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to start agent run");
      }
      const newRun: AgentRunRecord = await res.json();
      processedEventIds.current.clear();
      lastSequence.current = 0;
      setRunId(newRun.id);
      return newRun;
    } catch (err: any) {
      setError(err.message || "Failed to start run");
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const approvePlan = async () => {
    if (!runId) return;
    try {
      // 1. Approve the plan
      const approveRes = await fetch(`/api/v1/agent/runs/${runId}/plan/approve`, { method: "POST" });
      if (!approveRes.ok) throw new Error("Failed to approve plan");

      // 2. Start execution immediately after approval
      const executeRes = await fetch(`/api/v1/agent/runs/${runId}/execute`, { method: "POST" });
      if (!executeRes.ok) throw new Error("Failed to start execution");

      // 3. Refresh snapshot to show updated state
      await fetchSnapshot(runId);
    } catch (err: any) {
      setError(err.message || "Plan approval failed");
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
