"use client";

import React, { useState, useEffect, useRef } from "react";
import Editor, { DiffEditor, OnMount, loader } from "@monaco-editor/react";
import {
  FileCode,
  X,
  Code2,
  FileDiff,
  AlertTriangle,
  Save,
  RefreshCw,
  Check,
  Layers,
  Sparkles,
} from "lucide-react";
import { ImplementationPlanData, RunState } from "@/types/workspace";
import { getFileContent, saveFileContent } from "@/services/repositoryApi";
import { PlanDocumentViewer } from "./PlanDocumentViewer";

interface CodeEditorPanelProps {
  activeFile: string;
  onSelectFile: (filePath: string) => void;
  openTabs: string[];
  onCloseTab: (filePath: string) => void;
  runState?: RunState;
  editorMode?: "source" | "diff";
  onSetEditorMode?: (mode: "source" | "diff") => void;
  activePlan?: ImplementationPlanData | null;
  selectedPlan?: ImplementationPlanData | null;
  onApprovePlan?: () => void;
  onRejectPlan?: (reason?: string) => void;
  onSelectPlan?: (plan: ImplementationPlanData) => void;
}

export function CodeEditorPanel({
  activeFile,
  onSelectFile,
  openTabs,
  onCloseTab,
  runState,
  editorMode: externalEditorMode,
  onSetEditorMode,
  activePlan,
  selectedPlan,
  onApprovePlan,
  onRejectPlan,
  onSelectPlan,
}: CodeEditorPanelProps) {
  const repoName = runState?.repoId || "my-project";

  const [internalEditorMode, setInternalEditorMode] = useState<"source" | "diff">("source");
  const editorMode = externalEditorMode || internalEditorMode;

  const setEditorMode = (mode: "source" | "diff") => {
    setInternalEditorMode(mode);
    if (onSetEditorMode) onSetEditorMode(mode);
  };

  const [fileContent, setFileContent] = useState<string>("");
  const [loadingFile, setLoadingFile] = useState<boolean>(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);

  const editorRef = useRef<any>(null);

  const isPlanDoc = (filePath: string) =>
    Boolean(filePath) &&
    (filePath === "virtual://plan" ||
      filePath.startsWith("virtual://plan") ||
      filePath.startsWith("plan://"));

  // Auto-detect language for Monaco
  const getLanguage = (path: string) => {
    if (!path) return "plaintext";
    const lower = path.toLowerCase();
    if (lower.endsWith(".tsx") || lower.endsWith(".ts")) return "typescript";
    if (lower.endsWith(".jsx") || lower.endsWith(".js")) return "javascript";
    if (lower.endsWith(".py")) return "python";
    if (lower.endsWith(".json")) return "json";
    if (lower.endsWith(".css")) return "css";
    if (lower.endsWith(".html")) return "html";
    if (lower.endsWith(".md")) return "markdown";
    if (lower.endsWith(".toml") || lower.endsWith(".yaml") || lower.endsWith(".yml")) return "yaml";
    return "plaintext";
  };

  const getFileBasename = (path: string) => {
    if (!path) return "";
    if (isPlanDoc(path)) {
      const planVer = selectedPlan?.version || activePlan?.version || 1;
      return `Implementation Plan · v${planVer}`;
    }
    const parts = path.split("/");
    return parts[parts.length - 1];
  };

  const loadFile = () => {
    if (!activeFile || isPlanDoc(activeFile)) {
      setFileContent("");
      setLoadingFile(false);
      setFileError(null);
      return;
    }

    setLoadingFile(true);
    setFileError(null);
    setSaveSuccess(false);

    getFileContent(repoName, activeFile)
      .then((res) => {
        setFileContent(res.content || "");
        setLoadingFile(false);
      })
      .catch((err: any) => {
        setFileContent("");
        setFileError(err?.message || "Failed to load file content from storage");
        setLoadingFile(false);
      });
  };

  useEffect(() => {
    if (!activeFile || isPlanDoc(activeFile)) {
      setFileContent("");
      setLoadingFile(false);
      setFileError(null);
      return;
    }
    loadFile();
  }, [activeFile, repoName]);

  const handleSave = async () => {
    if (!activeFile || isPlanDoc(activeFile) || isSaving || fileError) return;

    try {
      setIsSaving(true);
      await saveFileContent(repoName, activeFile, fileContent);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err: any) {
      console.error("Save error:", err);
      setFileError(err.message || "Failed to save file");
    } finally {
      setIsSaving(false);
    }
  };

  // Keyboard shortcut Ctrl+S / Cmd+S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeFile, fileContent, isSaving, fileError]);

  const handleEditorDidMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;

    // Apply Verification Vector Defect markers if any on active file
    const defects = runState?.report?.defects || [];
    const markers = defects
      .filter((d) => d.file_path === activeFile && d.line_number)
      .map((d) => ({
        startLineNumber: d.line_number || 1,
        startColumn: 1,
        endLineNumber: d.line_number || 1,
        endColumn: 100,
        message: `[${d.category}] ${d.description}`,
        severity:
          d.severity === "CRITICAL" || d.severity === "HIGH"
            ? monaco.MarkerSeverity.Error
            : monaco.MarkerSeverity.Warning,
      }));

    if (markers.length) {
      const model = editor.getModel();
      if (model) {
        monaco.editor.setModelMarkers(model, "gitonboard_verifier", markers);
      }
    }
  };

  const patchedCode = runState?.rawDiff || fileContent;
  const isViewingPlan = isPlanDoc(activeFile);

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[#0A0D10] text-[#E6EDF3] border-b border-[#2F343A]">
      {/* Top Tab Bar */}
      <div className="h-9 bg-[#14181E] border-b border-[#2F343A] flex items-center justify-between px-2 select-none flex-shrink-0">
        {/* Open Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-none max-w-[65%]">
          {openTabs.length > 0 ? (
            openTabs.map((tabPath) => {
              const isActive = tabPath === activeFile;
              const isTabPlan = isPlanDoc(tabPath);
              const label = getFileBasename(tabPath);

              return (
                <div
                  key={tabPath}
                  onClick={() => onSelectFile(tabPath)}
                  className={`h-7 px-2.5 rounded-t flex items-center gap-1.5 text-xs font-mono border-t border-x cursor-pointer transition-colors ${
                    isActive
                      ? "bg-[#0A0D10] border-[#2F343A] text-purple-300 font-medium"
                      : "bg-[#14181E] border-transparent text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A]"
                  }`}
                >
                  {isTabPlan ? (
                    <Layers className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                  ) : (
                    <FileCode className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                  )}
                  <span className="truncate max-w-[180px]">{label}</span>
                  {isTabPlan && (
                    <span className="text-[9px] px-1 py-0.2 rounded bg-purple-950 text-purple-300 border border-purple-500/40">
                      PLAN
                    </span>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onCloseTab(tabPath);
                    }}
                    className="hover:text-white p-0.5 rounded text-[#8B949E]"
                    title="Close tab"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              );
            })
          ) : (
            <div className="text-[11px] text-[#8B949E] italic px-2">No documents open</div>
          )}
        </div>

        {/* Right Actions: Save Button & Mode Switcher (only for code files) */}
        {!isViewingPlan && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={!activeFile || isSaving || Boolean(fileError)}
              className={`px-2 py-0.5 rounded text-xs font-semibold flex items-center gap-1 transition-all ${
                saveSuccess
                  ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                  : !activeFile || Boolean(fileError)
                  ? "opacity-40 cursor-not-allowed bg-purple-950/20 text-[#8B949E] border border-[#2F343A]"
                  : "bg-purple-600/30 hover:bg-purple-600/50 text-purple-300 border border-purple-500/40"
              }`}
              title="Save File (Ctrl+S)"
            >
              {isSaving ? (
                <RefreshCw className="w-3 h-3 animate-spin text-purple-300" />
              ) : saveSuccess ? (
                <Check className="w-3 h-3 text-emerald-400" />
              ) : (
                <Save className="w-3 h-3" />
              )}
              <span>{saveSuccess ? "Saved" : "Save"}</span>
            </button>

            {/* Mode Switcher */}
            <div className="flex items-center gap-1 bg-[#0A0D10] border border-[#2F343A] p-0.5 rounded-lg text-xs font-mono">
              <button
                onClick={() => setEditorMode("source")}
                className={`px-2 py-0.5 rounded flex items-center gap-1 transition-all ${
                  editorMode === "source"
                    ? "bg-purple-600/30 text-purple-300 font-semibold border border-purple-500/40 shadow-sm"
                    : "text-[#8B949E] hover:text-[#E6EDF3]"
                }`}
              >
                <Code2 className="w-3.5 h-3.5" />
                <span>Source Code</span>
              </button>

              <button
                onClick={() => setEditorMode("diff")}
                className={`px-2 py-0.5 rounded flex items-center gap-1 transition-all ${
                  editorMode === "diff"
                    ? "bg-purple-600/30 text-purple-300 font-semibold border border-purple-500/40 shadow-sm"
                    : "text-[#8B949E] hover:text-[#E6EDF3]"
                }`}
              >
                <FileDiff className="w-3.5 h-3.5" />
                <span>Agent Diff</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Main Surface: Plan Document Viewer vs Monaco Code Editor */}
      <div className="flex-1 min-h-0 relative bg-[#0A0D10]">
        {!activeFile ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#0A0D10] text-[#8B949E] text-xs font-mono p-6 select-none">
            <div className="w-12 h-12 rounded-xl bg-[#14181E] border border-[#2F343A] flex items-center justify-center mb-3 text-purple-400">
              <FileCode className="w-6 h-6" />
            </div>
            <div className="text-sm font-semibold text-[#E6EDF3] mb-1">No Document Selected</div>
            <div className="text-xs text-[#8B949E] max-w-sm text-center">
              Select a file from the repository explorer or preview an implementation plan from the AI agent.
            </div>
          </div>
        ) : isViewingPlan ? (
          <PlanDocumentViewer
            plan={selectedPlan || activePlan || null}
            activePlan={activePlan}
            onApprovePlan={onApprovePlan}
            onRejectPlan={onRejectPlan}
            onSelectFile={onSelectFile}
            onSelectPlan={onSelectPlan}
          />
        ) : loadingFile ? (
          <div className="absolute inset-0 flex items-center justify-center bg-[#0A0D10] text-[#8B949E] text-xs font-mono">
            <div className="flex items-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-purple-400" />
              <span>Loading {getFileBasename(activeFile)} from Storage...</span>
            </div>
          </div>
        ) : fileError ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#0A0D10] text-rose-300 text-xs font-mono p-6">
            <div className="w-12 h-12 rounded-xl bg-rose-950/30 border border-rose-500/40 flex items-center justify-center mb-3 text-rose-400">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <div className="text-sm font-semibold text-rose-200 mb-1">Failed to Load File</div>
            <div className="text-xs text-rose-400/90 max-w-md text-center mb-4 bg-[#14181E] p-3 rounded border border-rose-500/30">
              {fileError}
            </div>
            <button
              onClick={loadFile}
              className="px-3 py-1.5 rounded bg-purple-600/30 hover:bg-purple-600/50 text-purple-300 border border-purple-500/40 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Load</span>
            </button>
          </div>
        ) : editorMode === "diff" ? (
          <DiffEditor
            height="100%"
            language={getLanguage(activeFile)}
            original={fileContent}
            modified={patchedCode}
            theme="vs-dark"
            options={{
              readOnly: true,
              renderSideBySide: true,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              fontSize: 13,
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              automaticLayout: true,
            }}
          />
        ) : (
          <Editor
            height="100%"
            language={getLanguage(activeFile)}
            value={fileContent}
            onChange={(val) => setFileContent(val || "")}
            theme="vs-dark"
            onMount={handleEditorDidMount}
            options={{
              readOnly: false,
              minimap: { enabled: true },
              scrollBeyondLastLine: false,
              fontSize: 13,
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              automaticLayout: true,
            }}
          />
        )}
      </div>
    </div>
  );
}
