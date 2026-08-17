"use client";

import React, { useState, useEffect, useRef } from "react";
import Editor, { DiffEditor, OnMount, loader } from "@monaco-editor/react";
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
  const [loadingFile, setLoadingFile] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);

  const editorRef = useRef<any>(null);

  // Auto-detect language for Monaco
  const getLanguage = (path: string) => {
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
    const parts = path.split("/");
    return parts[parts.length - 1];
  };

  // Dynamically fetch file content from Azurite Blob Storage on activeFile change
  useEffect(() => {
    if (!activeFile) return;

    let isMounted = true;
    setLoadingFile(true);
    setSaveSuccess(false);

    getFileContent(repoName, activeFile)
      .then((res) => {
        if (isMounted) {
          setFileContent(res.content || "");
          setLoadingFile(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setFileContent(`// Error loading file content for ${activeFile}`);
          setLoadingFile(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [repoName, activeFile]);

  // Handle Save Action (Ctrl+S or Save Button)
  const handleSave = async () => {
    if (!activeFile || isSaving) return;

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

    const defects = runState?.report?.defects || [];
    if (!defects.length) return;

    const markers = defects
      .filter((d) => !d.file_path || d.file_path.includes(getFileBasename(activeFile)))
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
          {openTabs.map((tabPath) => {
            const isActive = tabPath === activeFile;
            const basename = getFileBasename(tabPath);
            return (
              <div
                key={tabPath}
                onClick={() => onSelectFile(tabPath)}
                className={`h-7 px-2.5 rounded-t flex items-center gap-2 text-xs font-mono border-t border-x cursor-pointer transition-colors ${
                  isActive
                    ? "bg-[#0A0D10] border-[#2F343A] text-purple-300 font-medium"
                    : "bg-[#14181E] border-transparent text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A]"
                }`}
              >
                <FileCode className="w-3.5 h-3.5 text-purple-400" />
                <span>{basename}</span>
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
          })}
        </div>

        {/* Right Actions: Save Button & Mode Switcher */}
        <div className="flex items-center gap-2">
          {/* Save Button */}
          <button
            onClick={handleSave}
            disabled={isSaving}
            className={`px-2 py-0.5 rounded text-xs font-semibold flex items-center gap-1 transition-all ${
              saveSuccess
                ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
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
        <span>{activeFile.split("/").slice(0, -1).join("/") || "."}</span>
        <ChevronRight className="w-3 h-3 text-[#2F343A]" />
        <span className="text-purple-400 font-semibold">{getFileBasename(activeFile)}</span>

        {runState?.report?.defects && runState.report.defects.length > 0 && (
          <div className="ml-auto flex items-center gap-1 text-rose-400 bg-rose-950/40 px-2 py-0.5 rounded border border-rose-500/30">
            <AlertTriangle className="w-3 h-3" />
            <span>{runState.report.defects.length} defect(s) flagged</span>
          </div>
        )}
      </div>

      {/* Monaco Editor / Loading Skeleton */}
      <div className="flex-1 min-h-0 relative bg-[#0A0D10]">
        {loadingFile ? (
          <div className="absolute inset-0 flex items-center justify-center bg-[#0A0D10] text-[#8B949E] text-xs font-mono">
            <div className="flex items-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-purple-400" />
              <span>Streaming blob payload from Azurite Storage...</span>
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
