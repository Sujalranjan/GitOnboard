"use client";

import { useState, useCallback } from "react";
import { DefectItem, RunState } from "@/types/workspace";
import {
  runVerification,
  triggerRepair,
} from "@/services/verificationApi";

export function useVerificationWorkspace(initialRepoName: string = "default") {
  const [activeFile, setActiveFile] = useState<string>("");
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  const [editorMode, setEditorMode] = useState<"source" | "diff">("source");
  const [logs, setLogs] = useState<string[]>([
    `[System] GitOnBoard Workspace initialized for repository '${initialRepoName}'.`,
    "[Ready] Multi-Vector Verification Mesh stand-by.",
  ]);

  const [runState, setRunState] = useState<RunState>({
    runId: null,
    repoId: initialRepoName,
    branch: "main",
    taskPrompt: "Add a new API route for managing user todos with GET and POST handlers.",
    contract: null,
    rawDiff: "",
    report: null,
    iteration: 0,
    isLoading: false,
    statusMessage: "",
  });

  // Track repository changes to reset state cleanly without cascading effects
  const [prevRepo, setPrevRepo] = useState(initialRepoName);
  if (prevRepo !== initialRepoName) {
    setPrevRepo(initialRepoName);
    setActiveFile("");
    setOpenTabs([]);
    setEditorMode("source");
    setLogs([
      `[System] Switched to repository '${initialRepoName}'.`,
      "[Ready] Multi-Vector Verification Mesh stand-by.",
    ]);
    setRunState({
      runId: null,
      repoId: initialRepoName,
      branch: "main",
      taskPrompt: "Add a new API route for managing user todos with GET and POST handlers.",
      contract: null,
      rawDiff: "",
      report: null,
      iteration: 0,
      isLoading: false,
      statusMessage: "",
    });
  }

  const appendLog = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, `[${timestamp}] ${message}`]);
  }, []);

  const handleSelectFile = useCallback((filePath: string) => {
    setActiveFile(filePath);
    setOpenTabs((prev) => {
      if (!prev.includes(filePath)) {
        return [...prev, filePath];
      }
      return prev;
    });
  }, []);

  const handleCloseTab = useCallback(
    (filePath: string) => {
      setOpenTabs((prev) => {
        const next = prev.filter((p) => p !== filePath);
        if (activeFile === filePath) {
          setActiveFile(next.length > 0 ? next[next.length - 1] : "");
        }
        return next;
      });
    },
    [activeFile]
  );

  // Active Multi-Vector Verification execution handler
  const handleStartTaskPrompt = useCallback(
    async (prompt: string) => {
      setRunState((prev) => ({
        ...prev,
        taskPrompt: prompt,
        isLoading: true,
        statusMessage: "Running Multi-Vector Verification Mesh...",
      }));
      appendLog(`Starting verification for requirement: "${prompt.slice(0, 45)}..."`);

      try {
        const runId = runState.runId || `run-${Date.now()}`;
        const report = await runVerification(runId, runState.repoId);

        setRunState((prev) => ({
          ...prev,
          runId,
          report,
          iteration: 1,
          isLoading: false,
          statusMessage: report.passed
            ? "Verification Passed — Zero Defects Detected"
            : `Verification Failed — ${report.defects.length} Defect(s) Detected`,
        }));

        if (report.passed) {
          appendLog("VERIFICATION PASS: All AST, Dynamic, and Contract checks satisfied.");
        } else {
          appendLog(`VERIFICATION FAIL: Detected ${report.defects.length} defect(s).`);
          report.defects.forEach((d: DefectItem) => {
            appendLog(`  - [${d.category}] ${d.file_path}: ${d.description}`);
          });
        }
      } catch (error: unknown) {
        console.error("Verification execution error:", error);
        setRunState((prev) => ({
          ...prev,
          isLoading: false,
          statusMessage: "Verification error occurred.",
        }));
        const msg = error instanceof Error ? error.message : "Verification execution failed.";
        appendLog(`ERROR: ${msg}`);
      }
    },
    [runState.runId, runState.repoId, appendLog]
  );

  // Automated repair iteration handler (max 3 passes) via active /api/v1/repair/iterate
  const handleTriggerRepair = useCallback(async () => {
    if (!runState.runId) return;

    const nextIteration = runState.iteration + 1;
    if (nextIteration > 3) {
      setRunState((prev) => ({
        ...prev,
        statusMessage: "Maximum repair attempts (3) reached.",
      }));
      appendLog("REPAIR GUARD: Reached maximum allowed repair iterations (3).");
      return;
    }

    setRunState((prev) => ({
      ...prev,
      isLoading: true,
      statusMessage: `Repair Iteration ${nextIteration}/3 in progress...`,
    }));
    appendLog(`Triggering Adversarial Repair Iteration ${nextIteration}/3...`);

    try {
      const defects = runState.report?.defects || [];
      const repairRes = await triggerRepair(
        runState.runId,
        nextIteration,
        defects,
        runState.repoId
      );

      setRunState((prev) => ({
        ...prev,
        rawDiff: repairRes.diff || prev.rawDiff,
        report: repairRes.report,
        iteration: nextIteration,
        isLoading: false,
        statusMessage: repairRes.report.passed
          ? `Repair iteration ${nextIteration} passed successfully!`
          : `Repair iteration ${nextIteration} complete with remaining defects.`,
      }));

      setEditorMode("diff");

      if (repairRes.report.passed) {
        appendLog(`REPAIR SUCCESS: Iteration ${nextIteration} resolved all defects.`);
      } else {
        appendLog(`REPAIR ITERATION ${nextIteration}: ${repairRes.report.defects.length} remaining defect(s).`);
      }
    } catch (error: unknown) {
      console.error("Repair error:", error);
      setRunState((prev) => ({
        ...prev,
        isLoading: false,
        statusMessage: "Repair iteration error.",
      }));
      const msg = error instanceof Error ? error.message : "Repair iteration failed.";
      appendLog(`ERROR: ${msg}`);
    }
  }, [runState.runId, runState.repoId, runState.iteration, runState.report, appendLog]);

  return {
    runState,
    activeFile,
    openTabs,
    editorMode,
    setEditorMode,
    logs,
    handleSelectFile,
    handleCloseTab,
    handleStartTaskPrompt,
    handleTriggerRepair,
    appendLog,
  };
}
