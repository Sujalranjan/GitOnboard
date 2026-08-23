"use client";

import React, { useState, useEffect, useRef } from "react";
import Editor, { DiffEditor, OnMount, loader } from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import {
  FileCode,
  X,
  ChevronRight,
  Code2,
  FileDiff,
  AlertTriangle,
  Save,
  RefreshCw,
  Check,
  Eye,
  Edit3,
  Copy,
  Layers,
  Sparkles,
} from "lucide-react";
import { RunState } from "@/types/workspace";
import { getFileContent, saveFileContent } from "@/services/repositoryApi";

interface CodeEditorPanelProps {
  activeFile: string;
  onSelectFile: (filePath: string) => void;
  openTabs: string[];
  onCloseTab: (filePath: string) => void;
  runState?: RunState;
  editorMode?: "source" | "diff";
  onSetEditorMode?: (mode: "source" | "diff") => void;
}

export function CodeEditorPanel({
  activeFile,
  onSelectFile,
  openTabs,
  onCloseTab,
  runState,
  editorMode: externalEditorMode,
  onSetEditorMode,
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
  const [planViewMode, setPlanViewMode] = useState<"preview" | "raw">("preview");
  const [copySuccess, setCopySuccess] = useState<boolean>(false);

  const editorRef = useRef<any>(null);

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
    const parts = path.split("/");
    return parts[parts.length - 1];
  };

  const isTempPlan = activeFile === "implementation_plan.md" || activeFile.endsWith("plan.md") || activeFile.startsWith("temp://");

  const loadFile = () => {
    if (!activeFile) {
      setFileContent("");
      setLoadingFile(false);
      setFileError(null);
      return;
    }

    if (isTempPlan) {
      const planMarkdown =
        sessionStorage.getItem("gitonboard_active_plan_markdown") ||
        localStorage.getItem("gitonboard_active_plan_markdown") ||
        "# Implementation Plan\n\nPlan is being synthesized in local memory...";
      setFileContent(planMarkdown);
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
    if (!activeFile) {
      setFileContent("");
      setLoadingFile(false);
      setFileError(null);
      return;
    }

    if (isTempPlan) {
      const planMarkdown =
        sessionStorage.getItem("gitonboard_active_plan_markdown") ||
        localStorage.getItem("gitonboard_active_plan_markdown") ||
        "# Implementation Plan\n\nPlan is being synthesized in local memory...";
      setFileContent(planMarkdown);
      setLoadingFile(false);
      setFileError(null);
      return;
    }

    let isCurrent = true;
    setLoadingFile(true);
    setFileError(null);
    setSaveSuccess(false);

    getFileContent(repoName, activeFile)
      .then((res) => {
        if (!isCurrent) return;
        setFileContent(res.content || "");
        setLoadingFile(false);
      })
      .catch((err: any) => {
        if (!isCurrent) return;
        setFileContent("");
        setFileError(err?.message || "Failed to load file content from storage");
        setLoadingFile(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [repoName, activeFile]);

  // Handle Save Action (Ctrl+S or Save Button)
  const handleSave = async () => {
    if (!activeFile || isSaving || fileError) return;

    const currentCode = editorRef.current ? editorRef.current.getValue() : fileContent;
    setIsSaving(true);

    const success = await saveFileContent(repoName, activeFile, currentCode);
    setIsSaving(false);

    if (success) {
      setFileContent(currentCode);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    }
  };

  // Set Monaco markers for defects
  const handleEditorDidMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;

    // Save shortcut listener
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      handleSave();
    });

    // Set Monaco markers for defects
    const markers = (runState?.report?.defects || [])
      .filter((d) => !d.file_path || d.file_path === activeFile)
      .map((d) => ({
        startLineNumber: d.line_number || 1,
        startColumn: 1,
        endLineNumber: (d.line_number || 1) + 1,
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

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[#0A0D10] text-[#E6EDF3] border-b border-[#2F343A]">
      {/* Top Control Bar */}
      <div className="h-9 bg-[#14181E] border-b border-[#2F343A] flex items-center justify-between px-2 select-none flex-shrink-0">
        {/* Open Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-none max-w-[65%]">
          {openTabs.length > 0 ? (
            openTabs.map((tabPath) => {
              const isActive = tabPath === activeFile;
              const basename = getFileBasename(tabPath);
              const isTabTemp = tabPath === "implementation_plan.md" || tabPath.endsWith("plan.md") || tabPath.startsWith("temp://");
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
                  <FileCode className="w-3.5 h-3.5 text-purple-400" />
                  <span>{basename}</span>
                  {isTabTemp && (
                    <span className="text-[9px] px-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      TEMP
                    </span>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onCloseTab(tabPath);
                    }}
                    className="hover:text-white p-0.5 rounded text-[#8B949E]"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              );
            })
          ) : (
            <div className="text-[11px] text-[#8B949E] italic px-2">No files open</div>
          )}
        </div>

        {/* Right Actions: Save Button & Mode Switcher */}
        <div className="flex items-center gap-2">
          {/* Save Button */}
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

          {/* Mode Switcher: [ Source Code ] vs [ Agent Diff ] */}
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
      </div>

      {/* Breadcrumb Path Bar */}
      <div className="h-6 bg-[#0A0D10] border-b border-[#2F343A]/60 px-3 flex items-center gap-1 text-[11px] text-[#8B949E] font-mono select-none flex-shrink-0">
        <span>{repoName}</span>
        <ChevronRight className="w-3 h-3 text-[#2F343A]" />
        {activeFile ? (
          <>
            <span>{activeFile.split("/").slice(0, -1).join("/") || "."}</span>
            <ChevronRight className="w-3 h-3 text-[#2F343A]" />
            <span className="text-purple-400 font-semibold">{getFileBasename(activeFile)}</span>
          </>
        ) : (
          <span className="text-[#8B949E] italic">(No active file)</span>
        )}

        {runState?.report?.defects && runState.report.defects.length > 0 && (
          <div className="ml-auto flex items-center gap-1 text-rose-400 bg-rose-950/40 px-2 py-0.5 rounded border border-rose-500/30">
            <AlertTriangle className="w-3 h-3" />
            <span>{runState.report.defects.length} defect(s) flagged</span>
          </div>
        )}
      </div>

      {/* Temporary In-Memory Plan Banner & Mode Switcher */}
      {isTempPlan && (
        <div className="bg-[#14181E] border-b border-[#2F343A] px-3 py-1.5 flex items-center justify-between text-xs text-zinc-300 font-mono select-none flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-[11px] font-semibold text-amber-300">Implementation Plan (In-Memory Scratch)</span>
            <span className="text-[10px] text-zinc-500 hidden md:inline">• Stored in local session cache only; will not write to repository files or disk.</span>
          </div>

          <div className="flex items-center gap-2">
            {/* Preview vs Raw Editor Toggle */}
            <div className="flex items-center bg-[#0D1117] p-0.5 rounded-lg border border-[#30363D]">
              <button
                type="button"
                onClick={() => setPlanViewMode("preview")}
                className={`px-2 py-0.5 text-[10px] font-semibold rounded flex items-center gap-1 transition-all cursor-pointer ${
                  planViewMode === "preview"
                    ? "bg-purple-600 text-white shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <Eye className="w-3 h-3" />
                <span>Preview</span>
              </button>
              <button
                type="button"
                onClick={() => setPlanViewMode("raw")}
                className={`px-2 py-0.5 text-[10px] font-semibold rounded flex items-center gap-1 transition-all cursor-pointer ${
                  planViewMode === "raw"
                    ? "bg-purple-600 text-white shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <Edit3 className="w-3 h-3" />
                <span>Raw</span>
              </button>
            </div>

            {/* Copy Button */}
            <button
              type="button"
              onClick={() => {
                navigator.clipboard.writeText(fileContent);
                setCopySuccess(true);
                setTimeout(() => setCopySuccess(false), 2000);
              }}
              className="px-2 py-0.5 text-[10px] rounded bg-[#21262D] hover:bg-[#30363D] text-zinc-300 border border-[#30363D] flex items-center gap-1 transition-colors cursor-pointer font-mono"
            >
              {copySuccess ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3 text-zinc-400" />}
              <span>{copySuccess ? "Copied" : "Copy"}</span>
            </button>
          </div>
        </div>
      )}

      {/* Monaco Editor / Rich Preview Mode / Loading Skeleton / Empty State / Explicit Error Card */}
      <div className="flex-1 min-h-0 relative bg-[#0A0D10]">
        {!activeFile ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#0A0D10] text-[#8B949E] text-xs font-mono p-6 select-none">
            <div className="w-12 h-12 rounded-xl bg-[#14181E] border border-[#2F343A] flex items-center justify-center mb-3 text-purple-400">
              <FileCode className="w-6 h-6" />
            </div>
            <div className="text-sm font-semibold text-[#E6EDF3] mb-1">No File Selected</div>
            <div className="text-xs text-[#8B949E] max-w-sm text-center">
              Select a file from the repository explorer on the left or search symbols (⌘K) to open code in Monaco.
            </div>
          </div>
        ) : loadingFile ? (
          <div className="absolute inset-0 flex items-center justify-center bg-[#0A0D10] text-[#8B949E] text-xs font-mono">
            <div className="flex items-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-purple-400" />
              <span>Loading {getFileBasename(activeFile)} from Azurite Storage...</span>
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
              className="px-3 py-1.5 rounded bg-purple-600/30 hover:bg-purple-600/50 text-purple-300 border border-purple-500/40 text-xs font-semibold flex items-center gap-1.5 transition-all"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Load</span>
            </button>
          </div>
        ) : isTempPlan && planViewMode === "preview" ? (
          /* Proper Rich Document Preview Mode for Implementation Plan */
          <div className="h-full overflow-y-auto bg-[#0D1117] p-6 lg:p-10 text-zinc-200">
            <div className="max-w-4xl mx-auto space-y-6">
              <div className="bg-[#161B22] border border-purple-500/40 rounded-2xl p-5 shadow-lg shadow-purple-950/20 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-purple-600/20 border border-purple-500/40 flex items-center justify-center text-purple-300 shadow-inner">
                    <Layers className="w-5 h-5" />
                  </div>
                  <div>
                    <h2 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                      <span>Repository-Aware Implementation Plan</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-mono">
                        Validated DAG
                      </span>
                    </h2>
                    <p className="text-xs text-zinc-400 font-mono mt-0.5">
                      Target: {repoName} • 0 Git Mutations (Read-Only Preview)
                    </p>
                  </div>
                </div>

                <div className="text-[11px] text-amber-400 bg-amber-950/40 px-3 py-1 rounded-lg border border-amber-500/30 font-mono">
                  ⚡ Session Scratch
                </div>
              </div>

              <div className="bg-[#12161E] border border-[#30363D] rounded-2xl p-6 lg:p-8 shadow-md">
                <ReactMarkdown
                  components={{
                    h1: ({ children }) => (
                      <h1 className="text-lg font-bold text-white mt-4 mb-3 pb-2 border-b border-[#30363D] flex items-center gap-2">
                        {children}
                      </h1>
                    ),
                    h2: ({ children }) => (
                      <h2 className="text-sm font-bold text-purple-300 mt-6 mb-2.5 pb-1 border-b border-zinc-800 flex items-center gap-2">
                        {children}
                      </h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="text-xs font-semibold text-zinc-100 mt-4 mb-2 flex items-center gap-1.5">
                        {children}
                      </h3>
                    ),
                    h4: ({ children }) => (
                      <h4 className="text-xs font-semibold text-purple-400 mt-3 mb-1">
                        {children}
                      </h4>
                    ),
                    p: ({ children }) => (
                      <p className="text-xs text-zinc-300 leading-relaxed my-2">
                        {children}
                      </p>
                    ),
                    ul: ({ children }) => (
                      <ul className="list-disc pl-5 space-y-1.5 my-2.5 text-zinc-300 text-xs">
                        {children}
                      </ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="list-decimal pl-5 space-y-1.5 my-2.5 text-zinc-300 text-xs">
                        {children}
                      </ol>
                    ),
                    li: ({ children }) => (
                      <li className="leading-relaxed">
                        {children}
                      </li>
                    ),
                    strong: ({ children }) => (
                      <strong className="font-semibold text-white">
                        {children}
                      </strong>
                    ),
                    code: ({ className, children, ...props }: any) => {
                      const isMultiline = String(children).includes("\n");
                      if (!isMultiline) {
                        return (
                          <code
                            className="bg-[#21262D] text-purple-300 px-1.5 py-0.5 rounded font-mono text-[11px] border border-zinc-700/60"
                            {...props}
                          >
                            {children}
                          </code>
                        );
                      }
                      return (
                        <pre className="bg-[#0D1117] border border-[#30363D] p-3.5 rounded-xl overflow-x-auto my-3 text-zinc-200 shadow-sm">
                          <code
                            className="font-mono text-xs leading-relaxed block text-zinc-200"
                            {...props}
                          >
                            {children}
                          </code>
                        </pre>
                      );
                    },
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-4 border-purple-500 bg-[#161B22] px-4 py-2.5 rounded-r-lg my-3 text-zinc-300 text-xs italic">
                        {children}
                      </blockquote>
                    ),
                  }}
                >
                  {fileContent}
                </ReactMarkdown>
              </div>
            </div>
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
            theme="vs-dark"
            onMount={handleEditorDidMount}
            options={{
              readOnly: false,
              minimap: { enabled: true },
              scrollBeyondLastLine: false,
              fontSize: 13,
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              automaticLayout: true,
              lineNumbers: "on",
              glyphMargin: true,
            }}
          />
        )}
      </div>
    </div>
  );
}
