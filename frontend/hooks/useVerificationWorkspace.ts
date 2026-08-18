"use client";

import { useState, useCallback, useEffect } from "react";
import { DefectItem, RunState, VerificationReport } from "@/types/workspace";
import {
  submitPipelineTask,
  executePipelineTask,
  repairPipelineTask,
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

  // Complete state reset when repository changes
  useEffect(() => {
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
  }, [initialRepoName]);

  const appendLog = useCallback((message: string) => {
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${message}`]);
  }, []);

  const handleSelectFile = useCallback(
    (filePath: string) => {
      setActiveFile(filePath);
      if (!openTabs.includes(filePath)) {
        setOpenTabs((prev) => [...prev, filePath]);
      }
    },
    [openTabs]
  );

  const handleCloseTab = useCallback(
    (filePath: string) => {
      const newTabs = openTabs.filter((t) => t !== filePath);
      setOpenTabs(newTabs);
      if (activeFile === filePath && newTabs.length > 0) {
        setActiveFile(newTabs[newTabs.length - 1]);
      }
    },
    [activeFile, openTabs]
  );

  // Contract ➔ Agent ➔ Verification ➔ Judge sequence via Pipeline Orchestrator
  const handleStartTaskPrompt = useCallback(
    async (prompt: string) => {
      setRunState((prev) => ({
        ...prev,
        taskPrompt: prompt,
        isLoading: true,
        statusMessage: "1/3 Decomposing requirement into Implementation Contract...",
      }));
      appendLog(`Starting pipeline task for requirement: "${prompt.slice(0, 45)}..."`);

      try {
        // Step 1: Submit requirement and synthesize contract
        const submitRes = await submitPipelineTask(runState.repoId, prompt);
        setRunState((prev) => ({
          ...prev,
          runId: submitRes.task_id,
          contract: submitRes.contract,
          statusMessage: "2/3 Spawning Git worktree & executing AI Coding Agent...",
        }));
        appendLog(`Synthesized Implementation Contract ID: ${submitRes.contract.id}`);

        // Step 2: Execute sandboxed run and multi-vector verification
        const execRes = await executePipelineTask(
          submitRes.task_id,
          runState.repoId,
          submitRes.contract.id,
          submitRes.contract
        );

        setRunState((prev) => ({
          ...prev,
          runId: execRes.run_id,
          rawDiff: execRes.diff,
          report: execRes.report,
          iteration: 1,
          isLoading: false,
          statusMessage: execRes.report.passed
            ? "Verification Passed — Zero Defects Detected"
            : `Verification Failed — ${execRes.report.defects.length} Defect(s) Detected`,
        }));

        setEditorMode("diff");

        if (execRes.report.passed) {
          appendLog("VERIFICATION PASS: All AST, Dynamic, and Contract checks satisfied.");
        } else {
          appendLog(`VERIFICATION FAIL: Detected ${execRes.report.defects.length} defect(s).`);
          execRes.report.defects.forEach((d) => {
            appendLog(`  - [${d.category}] ${d.file_path}: ${d.description}`);
          });
        }
      } catch (error: any) {
        console.error("Pipeline execution error:", error);
        setRunState((prev) => ({
          ...prev,
          isLoading: false,
          statusMessage: "Pipeline error occurred.",
        }));
        appendLog(`ERROR: ${error?.message || "Pipeline execution failed."}`);
      }
    },
    [runState.repoId, appendLog]
  );

  // Automated repair iteration handler (max 3 passes)
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
      const repairRes = await repairPipelineTask(
        runState.runId,
        runState.repoId,
        nextIteration,
        defects,
        runState.contract
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
    } catch (error: any) {
      console.error("Repair error:", error);
      setRunState((prev) => ({
        ...prev,
        isLoading: false,
        statusMessage: "Repair iteration error.",
      }));
      appendLog(`REPAIR ERROR: ${error?.message || "Repair iteration failed."}`);
    }
  }, [runState.runId, runState.repoId, runState.iteration, runState.report, runState.contract, appendLog]);

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
  };
}
