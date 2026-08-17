"use client";

import React, { useState, useRef } from "react";
import Editor, { DiffEditor, OnMount, loader } from "@monaco-editor/react";
import {
  FileCode,
  FileJson,
  FileText,
  File,
  X,
  Plus,
  ChevronRight,
  Sparkles,
  Columns,
  Code2,
  FileDiff,
  AlertTriangle,
} from "lucide-react";
import { RunState } from "@/types/workspace";

interface CodeEditorPanelProps {
  activeFile: string;
  onSelectFile: (filePath: string) => void;
  openTabs: string[];
  onCloseTab: (filePath: string) => void;
  runState?: RunState;
  editorMode?: "source" | "diff";
  onSetEditorMode?: (mode: "source" | "diff") => void;
}

const SAMPLE_SOURCE_CODE: Record<string, string> = {
  "src/pages/api/index.tsx": `import React from 'react';
import Head from 'next/head';

export default function Home() {
  return (
    <div className="container mx-auto px-4 py-8">
      <Head>
        <title>GitOnBoard Verification Platform</title>
      </Head>
      <h1 className="text-3xl font-bold text-[#E6EDF3]">
        GitOnBoard — Repository Intelligence & Verification
      </h1>
      <p className="mt-2 text-slate-400">
        Adversarial multi-vector verification mesh for AI-generated code.
      </p>
    </div>
  );
}`,

  "src/components/TodoItem.tsx": `import React from 'react';

interface TodoItemProps {
  id: number;
  text: string;
  completed: boolean;
  onToggle: (id: number) => void;
}

export function TodoItem({ id, text, completed, onToggle }: TodoItemProps) {
  return (
    <div className="flex items-center gap-2 p-2 border border-slate-800 rounded">
      <input
        type="checkbox"
        checked={completed}
        onChange={() => onToggle(id)}
        className="rounded text-purple-600 focus:ring-purple-500"
      />
      <span className={completed ? 'line-through text-slate-500' : 'text-slate-200'}>
        {text}
      </span>
    </div>
  );
}`,

  "src/pages/api/todos.ts": `import type { NextApiRequest, NextApiResponse } from 'next';

interface Todo {
  id: number;
  text: string;
  completed: boolean;
}

let todosList: Todo[] = [
  { id: 1, text: 'Initialize AI Workspace', completed: true },
];

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method === 'GET') {
    return res.status(200).json(todosList);
  }
  if (req.method === 'POST') {
    const { text } = req.body;
    const newTodo: Todo = { id: Date.now(), text, completed: false };
    todosList.push(newTodo);
    return res.status(201).json(newTodo);
  }
  return res.status(405).end();
}`,
};

const SAMPLE_PATCHED_CODE = `import type { NextApiRequest, NextApiResponse } from 'next';
import { z } from 'zod';

const createTodoSchema = z.object({
  text: z.string().min(1, 'Task description required'),
});

interface Todo {
  id: number;
  text: string;
  completed: boolean;
}

let todosList: Todo[] = [
  { id: 1, text: 'Initialize AI Workspace', completed: true },
];

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method === 'GET') {
    return res.status(200).json(todosList);
  }
  if (req.method === 'POST') {
    const validation = createTodoSchema.safeParse(req.body);
    if (!validation.success) {
      return res.status(400).json({ error: 'Validation failed', details: validation.error.format() });
    }
    const { text } = req.body;
    const newTodo: Todo = { id: Date.now(), text, completed: false };
    todosList.push(newTodo);
    return res.status(201).json(newTodo);
  }
  return res.status(405).end();
}`;

export function CodeEditorPanel({
  activeFile,
  onSelectFile,
  openTabs,
  onCloseTab,
  runState,
  editorMode: externalEditorMode,
  onSetEditorMode,
}: CodeEditorPanelProps) {
  const [internalEditorMode, setInternalEditorMode] = useState<"source" | "diff">("source");
  const editorMode = externalEditorMode || internalEditorMode;

  const setEditorMode = (mode: "source" | "diff") => {
    setInternalEditorMode(mode);
    if (onSetEditorMode) onSetEditorMode(mode);
  };

  const getFileBasename = (path: string) => {
    const parts = path.split("/");
    return parts[parts.length - 1];
  };

  const getLanguage = (path: string) => {
    if (path.endsWith(".tsx") || path.endsWith(".ts")) return "typescript";
    if (path.endsWith(".jsx") || path.endsWith(".js")) return "javascript";
    if (path.endsWith(".json")) return "json";
    if (path.endsWith(".md")) return "markdown";
    return "typescript";
  };

  // Base code vs Patched code for DiffEditor
  const baseCode = SAMPLE_SOURCE_CODE[activeFile] || `// ${activeFile}\nexport default function Module() {\n  return null;\n}`;
  const patchedCode =
    activeFile === "src/pages/api/todos.ts"
      ? SAMPLE_PATCHED_CODE
      : runState?.rawDiff || baseCode;

  // Set Monaco markers for defects
  const handleEditorDidMount: OnMount = (editor, monaco) => {
    const defects = runState?.report?.defects || [];
    if (!defects.length) return;

    const markers = defects
      .filter((d) => !d.file_path || d.file_path.includes(getFileBasename(activeFile)))
      .map((d) => ({
        startLineNumber: d.line_number || 1,
        startColumn: 1,
        endLineNumber: d.line_number || 2,
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

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[#0A0D10] text-[#E6EDF3] border-b border-[#2F343A]">
      {/* Top Editor Control Bar with Tabs */}
      <div className="h-9 bg-[#14181E] border-b border-[#2F343A] flex items-center justify-between px-2 select-none flex-shrink-0">
        {/* Open Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-none max-w-[70%]">
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

      {/* Breadcrumb Path Bar */}
      <div className="h-6 bg-[#0A0D10] border-b border-[#2F343A]/60 px-3 flex items-center gap-1 text-[11px] text-[#8B949E] font-mono select-none flex-shrink-0">
        <span>{activeFile.split("/")[0]}</span>
        <ChevronRight className="w-3 h-3 text-[#2F343A]" />
        <span>{activeFile.split("/").slice(1, -1).join("/")}</span>
        <ChevronRight className="w-3 h-3 text-[#2F343A]" />
        <span className="text-purple-400 font-semibold">{getFileBasename(activeFile)}</span>

        {runState?.report?.defects && runState.report.defects.length > 0 && (
          <div className="ml-auto flex items-center gap-1 text-rose-400 bg-rose-950/40 px-2 py-0.5 rounded border border-rose-500/30">
            <AlertTriangle className="w-3 h-3" />
            <span>{runState.report.defects.length} verification defect(s) flagged</span>
          </div>
        )}
      </div>

      {/* Monaco Editor / Diff Editor Container */}
      <div className="flex-1 min-h-0 relative bg-[#0A0D10]">
        {editorMode === "diff" ? (
          <DiffEditor
            height="100%"
            language={getLanguage(activeFile)}
            original={baseCode}
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
            value={baseCode}
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
