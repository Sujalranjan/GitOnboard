"use client";

import React, { useState } from "react";
import {
  FileCode,
  FileJson,
  FileText,
  File,
  X,
  Plus,
  ChevronRight,
  Sparkles,
} from "lucide-react";

interface CodeEditorPanelProps {
  activeFile: string;
  onSelectFile: (filePath: string) => void;
  openTabs: string[];
  onCloseTab: (filePath: string) => void;
}

export function CodeEditorPanel({
  activeFile,
  onSelectFile,
  openTabs,
  onCloseTab,
}: CodeEditorPanelProps) {
  const getFileBasename = (path: string) => {
    const parts = path.split("/");
    return parts[parts.length - 1];
  };

  const renderTabIcon = (path: string) => {
    const name = getFileBasename(path);
    if (name.endsWith(".tsx") || name.endsWith(".ts")) {
      return <FileCode className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />;
    }
    if (name.endsWith(".json")) {
      return <FileJson className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />;
    }
    if (name.endsWith(".md")) {
      return <FileText className="w-3.5 h-3.5 text-sky-400 flex-shrink-0" />;
    }
    return <File className="w-3.5 h-3.5 text-[#8B949E] flex-shrink-0" />;
  };

  // Sample code contents for supported files
  const fileContents: Record<string, { language: string; lines: string[] }> = {
    "src/pages/api/index.tsx": {
      language: "typescript",
      lines: [
        `import React, { useState, useEffect } from 'react';`,
        `import Head from 'next/head';`,
        `import TodoItem from '@/components/TodoItem';`,
        ``,
        `interface Todo {`,
        `  id: number;`,
        `  text: string;`,
        `  completed: boolean;`,
        `}`,
        ``,
        `export default function Home() {`,
        `  const [todos, setTodos] = useState<Todo[]>([]);`,
        `  const [input, setInput] = useState('');`,
        `  const [loading, setLoading] = useState(false);`,
        ``,
        `  useEffect(() => {`,
        `    fetch('/api/todos')`,
        `      .then((res) => res.json())`,
        `      .then((data) => setTodos(data))`,
        `      .catch(console.error);`,
        `  }, []);`,
        ``,
        `  const handleAddTodo = async (e: React.FormEvent) => {`,
        `    e.preventDefault();`,
        `    if (!input.trim()) return;`,
        `    setLoading(true);`,
        `    const res = await fetch('/api/todos', {`,
        `      method: 'POST',`,
        `      headers: { 'Content-Type': 'application/json' },`,
        `      body: JSON.stringify({ text: input }),`,
        `    });`,
        `    const newTodo = await res.json();`,
        `    setTodos([...todos, newTodo]);`,
        `    setInput('');`,
        `    setLoading(false);`,
        `  };`,
        ``,
        `  return (`,
        `    <div className="min-h-screen bg-[#0A0D10] text-[#E6EDF3] p-8">`,
        `      <Head>`,
        `        <title>AI Workspace - Todo Tracker</title>`,
        `      </Head>`,
        `      <main className="max-w-2xl mx-auto space-y-6">`,
        `        <h1 className="text-3xl font-bold tracking-tight text-purple-400">Task Overview</h1>`,
        `        <form onSubmit={handleAddTodo} className="flex gap-3">`,
        `          <input`,
        `            type="text"`,
        `            value={input}`,
        `            onChange={(e) => setInput(e.target.value)}`,
        `            placeholder="Add new task..."`,
        `            className="flex-1 bg-[#14181E] border border-[#2F343A] px-4 py-2 rounded-lg text-sm"`,
        `          />`,
        `          <button type="submit" disabled={loading} className="bg-purple-600 hover:bg-purple-500 px-5 py-2 rounded-lg text-sm font-semibold">`,
        `            Add Task`,
        `          </button>`,
        `        </form>`,
        `        <ul className="divide-y divide-[#2F343A] rounded-lg bg-[#14181E] border border-[#2F343A]">`,
        `          {todos.map((todo) => (`,
        `            <TodoItem key={todo.id} todo={todo} />`,
        `          ))}`,
        `        </ul>`,
        `      </main>`,
        `    </div>`,
        `  );`,
        `}`,
      ],
    },
    "src/pages/api/todos.ts": {
      language: "typescript",
      lines: [
        `import type { NextApiRequest, NextApiResponse } from 'next';`,
        ``,
        `interface Todo {`,
        `  id: number;`,
        `  text: string;`,
        `  completed: boolean;`,
        `}`,
        ``,
        `let todosList: Todo[] = [`,
        `  { id: 1, text: 'Initialize AI Workspace', completed: true },`,
        `  { id: 2, text: 'Configure Next.js 16 App Router', completed: true },`,
        `  { id: 3, text: 'Build Multi-Panel Verification Engine', completed: false },`,
        `];`,
        ``,
        `export default function handler(req: NextApiRequest, res: NextApiResponse) {`,
        `  if (req.method === 'GET') {`,
        `    return res.status(200).json(todosList);`,
        `  }`,
        `  if (req.method === 'POST') {`,
        `    const { text } = req.body;`,
        `    const newTodo: Todo = {`,
        `      id: Date.now(),`,
        `      text,`,
        `      completed: false,`,
        `    };`,
        `    todosList.push(newTodo);`,
        `    return res.status(201).json(newTodo);`,
        `  }`,
        `  return res.status(45) .json({ error: 'Method Not Allowed' });`,
        `}`,
      ],
    },
    "src/components/TodoItem.tsx": {
      language: "typescript",
      lines: [
        `import React from 'react';`,
        ``,
        `interface TodoItemProps {`,
        `  todo: { id: number; text: string; completed: boolean };`,
        `}`,
        ``,
        `export default function TodoItem({ todo }: TodoItemProps) {`,
        `  return (`,
        `    <li className="px-4 py-3 flex items-center justify-between hover:bg-[#1E222A]">`,
        `      <span className={todo.completed ? 'line-through text-[#8B949E]' : 'text-[#E6EDF3]'}>`,
        `        {todo.text}`,
        `      </span>`,
        `      <span className="text-xs px-2 py-0.5 rounded bg-purple-950 text-purple-300 font-mono">`,
        `        #{todo.id}`,
        `      </span>`,
        `    </li>`,
        `  );`,
        `}`,
      ],
    },
    "package.json": {
      language: "json",
      lines: [
        `{`,
        `  "name": "my-project",`,
        `  "version": "0.1.0",`,
        `  "private": true,`,
        `  "scripts": {`,
        `    "dev": "next dev",`,
        `    "build": "next build",`,
        `    "start": "next start"`,
        `  },`,
        `  "dependencies": {`,
        `    "next": "^16.2.10",`,
        `    "react": "^19.2.4",`,
        `    "tailwindcss": "^4.0.0"`,
        `  }`,
        `}`,
      ],
    },
    "README.md": {
      language: "markdown",
      lines: [
        `# My Project — AI Workspace`,
        ``,
        `AI-powered multi-panel workspace built with Next.js 16, TypeScript, and Tailwind CSS.`,
        ``,
        `## Getting Started`,
        `\`\`\`bash`,
        `npm run dev`,
        `\`\`\``,
      ],
    },
  };

  const currentContent = fileContents[activeFile] || {
    language: "typescript",
    lines: [
      `// File: ${activeFile}`,
      `export default function Component() {`,
      `  return <div>Code loaded for ${activeFile}</div>;`,
      `}`,
    ],
  };

  // Clean token-based syntax highlighter for React
  const formatLine = (line: string) => {
    if (!line) return <span>&nbsp;</span>;

    // Highlight comments
    if (line.trim().startsWith("//") || line.trim().startsWith("/*")) {
      return <span className="text-[#8B949E] italic">{line}</span>;
    }

    const tokenRegex = /(\b(?:import|export|default|function|return|const|let|var|if|async|await|type|interface|from|class|extends)\b|'[^\']*'|"[^\"]*"|`[^\`]*`|\b(?:useState|useEffect|fetch|console|res|req|JSON|String|Number|Boolean)\b|\b(?:Home|TodoItem|Head|Todo|NextApiRequest|NextApiResponse)\b|<\/?[a-zA-Z0-9]+\b|\/?>|\b\d+\b)/g;

    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = tokenRegex.exec(line)) !== null) {
      if (match.index > lastIndex) {
        parts.push(line.substring(lastIndex, match.index));
      }

      const token = match[0];
      let className = "text-[#E6EDF3]";

      if (/^(import|export|default|function|return|const|let|var|if|async|await|type|interface|from|class|extends)$/.test(token)) {
        className = "text-orange-400 font-medium";
      } else if (/^(useState|useEffect|fetch|console|res|req|JSON|String|Number|Boolean)$/.test(token)) {
        className = "text-purple-400";
      } else if (/^(Home|TodoItem|Head|Todo|NextApiRequest|NextApiResponse)$/.test(token)) {
        className = "text-blue-400 font-semibold";
      } else if (/^('[^']*'|"[^"]*"|`[^`]*`)$/.test(token)) {
        className = "text-emerald-400";
      } else if (/^(<\/?[a-zA-Z0-9]+\b|\/?>)$/.test(token)) {
        className = "text-rose-400";
      } else if (/^\d+$/.test(token)) {
        className = "text-amber-400";
      }

      parts.push(
        <span key={`${match.index}-${token}`} className={className}>
          {token}
        </span>
      );

      lastIndex = tokenRegex.lastIndex;
    }

    if (lastIndex < line.length) {
      parts.push(line.substring(lastIndex));
    }

    return <>{parts}</>;
  };

  const breadcrumbs = activeFile.split("/");

  return (
    <div className="flex-1 bg-[#0A0D10] flex flex-col h-full overflow-hidden select-none">
      {/* Top Editor Tabs Bar */}
      <div className="h-9 bg-[#14181E] border-b border-[#2F343A] flex items-center overflow-x-auto text-xs scrollbar-none flex-shrink-0">
        {openTabs.map((filePath) => {
          const isActive = filePath === activeFile;
          const fileName = getFileBasename(filePath);
          return (
            <div
              key={filePath}
              onClick={() => onSelectFile(filePath)}
              className={`h-full px-3 flex items-center gap-2 border-r border-[#2F343A] cursor-pointer transition-colors group ${
                isActive
                  ? "bg-[#0A0D10] text-[#E6EDF3] font-medium border-t-2 border-t-purple-500 shadow-inner"
                  : "bg-[#14181E] text-[#8B949E] hover:bg-[#1E222A] hover:text-[#E6EDF3]"
              }`}
            >
              {renderTabIcon(filePath)}
              <span>{fileName}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(filePath);
                }}
                className="p-0.5 rounded text-[#8B949E] hover:text-white hover:bg-[#2F343A] transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          );
        })}

        {/* Plus New Tab */}
        <button className="h-full px-2.5 flex items-center justify-center text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] transition-colors">
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Breadcrumb Bar */}
      <div className="h-7 px-4 bg-[#0A0D10] border-b border-[#2F343A]/60 flex items-center gap-1.5 text-[11px] text-[#8B949E] font-mono flex-shrink-0">
        {breadcrumbs.map((crumb, idx) => (
          <React.Fragment key={idx}>
            <span className={idx === breadcrumbs.length - 1 ? "text-purple-300 font-semibold" : ""}>
              {crumb}
            </span>
            {idx < breadcrumbs.length - 1 && <ChevronRight className="w-3 h-3 text-[#2F343A]" />}
          </React.Fragment>
        ))}
      </div>

      {/* Code Editor Body */}
      <div className="flex-1 overflow-auto font-mono text-xs leading-6 p-2 bg-[#0A0D10]">
        <div className="table w-full">
          {currentContent.lines.map((line, index) => {
            const lineNumber = index + 1;
            const isHighlightedLine = lineNumber === 14 || lineNumber === 24;
            return (
              <div
                key={index}
                className={`table-row group ${
                  isHighlightedLine ? "bg-purple-950/20 border-l-2 border-purple-500" : "hover:bg-[#14181E]/50"
                }`}
              >
                {/* Line Number */}
                <div className="table-cell pr-4 text-right select-none text-[#8B949E]/50 group-hover:text-[#8B949E] w-10">
                  {lineNumber}
                </div>
                {/* Code Text */}
                <div className="table-cell pl-2 text-[#E6EDF3] whitespace-pre">
                  {formatLine(line)}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
