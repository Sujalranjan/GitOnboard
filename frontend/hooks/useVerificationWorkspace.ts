"use client";

import { useState, useCallback } from "react";
import { DefectItem, RunState, VerificationReport } from "@/types/workspace";
import {
  createContract,
  executeAgentRun,
  runVerification,
  triggerRepair,
} from "@/services/verificationApi";

export function useVerificationWorkspace() {
  const [activeFile, setActiveFile] = useState<string>("src/pages/api/index.tsx");
  const [openTabs, setOpenTabs] = useState<string[]>([
    "src/pages/api/index.tsx",
    "src/components/TodoItem.tsx",
  ]);
  const [editorMode, setEditorMode] = useState<"source" | "diff">("source");
  const [logs, setLogs] = useState<string[]>([
    "[System] GitOnBoard Workspace initialized.",
    "[Ready] Multi-Vector Verification Mesh stand-by.",
  ]);

  const [runState, setRunState] = useState<RunState>({
    runId: null,
    repoId: "my-project",
    branch: "main",
    taskPrompt: "Add a new API route for managing user todos with GET and POST handlers.",
    contract: null,
    rawDiff: "",
    report: null,
    iteration: 0,
    isLoading: false,
    statusMessage: "",
  });

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

  // Contract ➔ Agent ➔ Verification ➔ Judge sequence
  const handleStartTaskPrompt = useCallback(
    async (prompt: string) => {
      setRunState((prev) => ({
        ...prev,
        taskPrompt: prompt,
        isLoading: true,
        statusMessage: "1/3 Decomposing requirement into Implementation Contract...",
      }));
      appendLog(`Starting requirement analysis for: "${prompt.slice(0, 45)}..."`);

      try {
        // 1. Create Implementation Contract
        const contract = await createContract(runState.repoId, prompt);
        setRunState((prev) => ({
          ...prev,
          contract,
          statusMessage: "2/3 Executing AI Coding Agent in isolated Git worktree...",
        }));
        appendLog(`Synthesized Implementation Contract ID: ${contract.id}`);

        // 2. Execute Agent Run
        const agentRun = await executeAgentRun(runState.repoId, contract.id);
        setRunState((prev) => ({
          ...prev,
          runId: agentRun.run_id,
          rawDiff: agentRun.diff,
          statusMessage: "3/3 Running Multi-Vector Verification Mesh (Static, Dynamic, Contract)...",
        }));
        appendLog(`Agent generated unified changeset diff (${agentRun.diff.split("\n").length} lines).`);

        // 3. Multi-Vector Verification
        const report = await runVerification(agentRun.run_id, runState.repoId);
        setRunState((prev) => ({
          ...prev,
          report,
          isLoading: false,
          statusMessage: report.passed ? "Verification Passed" : "Verification Failed - Defect Detected",
        }));

        if (report.passed) {
          appendLog("VERIFICATION PASS: All AST, Dynamic, and Contract checks satisfied.");
        } else {
          appendLog(`VERIFICATION FAIL: Detected ${report.defects.length} defect(s).`);
          report.defects.forEach((d) => {
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
          ? `Repair iteration ${nextIteration} passed!`
          : `Repair iteration ${nextIteration} complete with remaining defects.`,
      }));

      if (repairRes.report.passed) {
        appendLog(`REPAIR SUCCESS: Iteration ${nextIteration} resolved all defects.`);
        setEditorMode("diff");
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
  }, [runState.runId, runState.iteration, runState.repoId, runState.report, appendLog]);

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
