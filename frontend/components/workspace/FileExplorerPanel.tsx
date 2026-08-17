"use client";

import React, { useState } from "react";
import {
  FilePlus,
  FolderPlus,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  FileCode,
  FileText,
  FileJson,
  File,
  Lock,
  GitBranch,
} from "lucide-react";

import { RunState } from "@/types/workspace";

interface FileExplorerPanelProps {
  activeFile: string;
  onSelectFile: (filePath: string) => void;
  isOpen: boolean;
  onClose: () => void;
  runState?: RunState;
}

export function FileExplorerPanel({
  activeFile,
  onSelectFile,
  isOpen,
  onClose,
}: FileExplorerPanelProps) {
  const [isMyProjectExpanded, setIsMyProjectExpanded] = useState(true);
  const [isSrcExpanded, setIsSrcExpanded] = useState(true);
  const [isPagesExpanded, setIsPagesExpanded] = useState(true);
  const [isApiExpanded, setIsApiExpanded] = useState(true);
  const [isComponentsExpanded, setIsComponentsExpanded] = useState(false);
  const [isStylesExpanded, setIsStylesExpanded] = useState(false);
  const [isUtilsExpanded, setIsUtilsExpanded] = useState(false);
  const [isGithubExpanded, setIsGithubExpanded] = useState(false);

  const [isOutlineExpanded, setIsOutlineExpanded] = useState(false);
  const [isTimelineExpanded, setIsTimelineExpanded] = useState(false);

  if (!isOpen) return null;

  const renderFileIcon = (fileName: string) => {
    if (fileName.endsWith(".tsx") || fileName.endsWith(".ts")) {
      return <FileCode className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />;
    }
    if (fileName.endsWith(".js") || fileName.endsWith(".mjs")) {
      return <FileCode className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />;
    }
    if (fileName.endsWith(".json")) {
      return <FileJson className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />;
    }
    if (fileName.endsWith(".md")) {
      return <FileText className="w-3.5 h-3.5 text-sky-400 flex-shrink-0" />;
    }
    if (fileName.startsWith(".env")) {
      return <Lock className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />;
    }
    if (fileName === ".gitignore") {
      return <GitBranch className="w-3.5 h-3.5 text-orange-400 flex-shrink-0" />;
    }
    return <File className="w-3.5 h-3.5 text-[#8B949E] flex-shrink-0" />;
  };

  return (
    <div className="w-60 bg-[#14181E] border-r border-[#2F343A] flex flex-col h-full select-none flex-shrink-0 text-[#E6EDF3]">
      {/* Top Header */}
      <div className="h-9 px-3 border-b border-[#2F343A] flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-[#8B949E]">
        <span>EXPLORER</span>
        <div className="flex items-center gap-1.5 text-[#8B949E]">
          <button className="hover:text-[#E6EDF3] transition-colors p-0.5 rounded" title="New File">
            <FilePlus className="w-3.5 h-3.5" />
          </button>
          <button className="hover:text-[#E6EDF3] transition-colors p-0.5 rounded" title="New Folder">
            <FolderPlus className="w-3.5 h-3.5" />
          </button>
          <button className="hover:text-[#E6EDF3] transition-colors p-0.5 rounded" title="Collapse All">
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main File Tree Area */}
      <div className="flex-1 overflow-y-auto py-1 text-xs">
        {/* Collapsible MY-PROJECT Section */}
        <div>
          <button
            onClick={() => setIsMyProjectExpanded(!isMyProjectExpanded)}
            className="w-full px-2 py-1 flex items-center gap-1 hover:bg-[#1E222A] font-bold text-[11px] uppercase tracking-wider text-[#E6EDF3] transition-colors"
          >
            {isMyProjectExpanded ? (
              <ChevronDown className="w-3.5 h-3.5 text-[#8B949E]" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-[#8B949E]" />
            )}
            <span>MY-PROJECT</span>
          </button>

          {isMyProjectExpanded && (
            <div className="pl-2">
              {/* .github Folder */}
              <div>
                <button
                  onClick={() => setIsGithubExpanded(!isGithubExpanded)}
                  className="w-full px-2 py-1 flex items-center gap-1.5 hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3] transition-colors"
                >
                  {isGithubExpanded ? (
                    <ChevronDown className="w-3 h-3 text-[#8B949E]" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-[#8B949E]" />
                  )}
                  <span className="font-medium text-[#E6EDF3]">.github</span>
                </button>
                {isGithubExpanded && (
                  <div className="pl-5 py-0.5 text-[#8B949E] text-[11px]">
                    <div className="px-2 py-0.5 hover:bg-[#1E222A] cursor-pointer">workflows</div>
                  </div>
                )}
              </div>

              {/* src Folder */}
              <div>
                <button
                  onClick={() => setIsSrcExpanded(!isSrcExpanded)}
                  className="w-full px-2 py-1 flex items-center gap-1.5 hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3] transition-colors"
                >
                  {isSrcExpanded ? (
                    <ChevronDown className="w-3 h-3 text-[#8B949E]" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-[#8B949E]" />
                  )}
                  <span className="font-medium text-[#E6EDF3]">src</span>
                </button>

                {isSrcExpanded && (
                  <div className="pl-4">
                    {/* components Folder */}
                    <div>
                      <button
                        onClick={() => setIsComponentsExpanded(!isComponentsExpanded)}
                        className="w-full px-2 py-1 flex items-center gap-1.5 hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3] transition-colors"
                      >
                        {isComponentsExpanded ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronRight className="w-3 h-3" />
                        )}
                        <span>components</span>
                      </button>
                      {isComponentsExpanded && (
                        <div className="pl-4">
                          <button
                            onClick={() => onSelectFile("src/components/TodoItem.tsx")}
                            className={`w-full px-2 py-1 flex items-center gap-2 transition-colors ${
                              activeFile === "src/components/TodoItem.tsx"
                                ? "bg-purple-600/25 text-purple-300 font-semibold border-l-2 border-purple-500"
                                : "hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3]"
                            }`}
                          >
                            {renderFileIcon("TodoItem.tsx")}
                            <span>TodoItem.tsx</span>
                          </button>
                        </div>
                      )}
                    </div>

                    {/* pages Folder */}
                    <div>
                      <button
                        onClick={() => setIsPagesExpanded(!isPagesExpanded)}
                        className="w-full px-2 py-1 flex items-center gap-1.5 hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3] transition-colors"
                      >
                        {isPagesExpanded ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronRight className="w-3 h-3" />
                        )}
                        <span>pages</span>
                      </button>

                      {isPagesExpanded && (
                        <div className="pl-4">
                          {/* api Folder */}
                          <div>
                            <button
                              onClick={() => setIsApiExpanded(!isApiExpanded)}
                              className="w-full px-2 py-1 flex items-center gap-1.5 hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3] transition-colors"
                            >
                              {isApiExpanded ? (
                                <ChevronDown className="w-3 h-3" />
                              ) : (
                                <ChevronRight className="w-3 h-3" />
                              )}
                              <span>api</span>
                            </button>

                            {isApiExpanded && (
                              <div className="pl-4">
                                <button
                                  onClick={() => onSelectFile("src/pages/api/todos.ts")}
                                  className={`w-full px-2 py-1 flex items-center gap-2 transition-colors ${
                                    activeFile === "src/pages/api/todos.ts"
                                      ? "bg-purple-600/25 text-purple-300 font-semibold border-l-2 border-purple-500"
                                      : "hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3]"
                                  }`}
                                >
                                  {renderFileIcon("todos.ts")}
                                  <span>todos.ts</span>
                                </button>

                                <button
                                  onClick={() => onSelectFile("src/pages/api/_app.tsx")}
                                  className={`w-full px-2 py-1 flex items-center gap-2 transition-colors ${
                                    activeFile === "src/pages/api/_app.tsx"
                                      ? "bg-purple-600/25 text-purple-300 font-semibold border-l-2 border-purple-500"
                                      : "hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3]"
                                  }`}
                                >
                                  {renderFileIcon("_app.tsx")}
                                  <span>_app.tsx</span>
                                </button>

                                {/* Highlighted index.tsx */}
                                <button
                                  onClick={() => onSelectFile("src/pages/api/index.tsx")}
                                  className={`w-full px-2 py-1 flex items-center gap-2 transition-colors ${
                                    activeFile === "src/pages/api/index.tsx"
                                      ? "bg-purple-600/30 text-white font-medium border-l-2 border-purple-500 shadow-sm"
                                      : "hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3]"
                                  }`}
                                >
                                  {renderFileIcon("index.tsx")}
                                  <span className="text-[#E6EDF3]">index.tsx</span>
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* styles Folder */}
                    <div>
                      <button
                        onClick={() => setIsStylesExpanded(!isStylesExpanded)}
                        className="w-full px-2 py-1 flex items-center gap-1.5 hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3] transition-colors"
                      >
                        {isStylesExpanded ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronRight className="w-3 h-3" />
                        )}
                        <span>styles</span>
                      </button>
                    </div>

                    {/* utils Folder */}
                    <div>
                      <button
                        onClick={() => setIsUtilsExpanded(!isUtilsExpanded)}
                        className="w-full px-2 py-1 flex items-center gap-1.5 hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3] transition-colors"
                      >
                        {isUtilsExpanded ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronRight className="w-3 h-3" />
                        )}
                        <span>utils</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Root Files */}
              <div className="pt-1">
                {[
                  ".env.local",
                  ".gitignore",
                  "next.config.js",
                  "package.json",
                  "README.md",
                  "tsconfig.json",
                ].map((file) => (
                  <button
                    key={file}
                    onClick={() => onSelectFile(file)}
                    className={`w-full px-2 py-1 flex items-center gap-2 transition-colors ${
                      activeFile === file
                        ? "bg-purple-600/25 text-purple-300 font-semibold border-l-2 border-purple-500"
                        : "hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3]"
                    }`}
                  >
                    {renderFileIcon(file)}
                    <span>{file}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Collapsible Panels: OUTLINE & TIMELINE */}
      <div className="border-t border-[#2F343A] text-xs">
        <button
          onClick={() => setIsOutlineExpanded(!isOutlineExpanded)}
          className="w-full px-3 py-1.5 flex items-center justify-between hover:bg-[#1E222A] font-semibold text-[#8B949E] transition-colors"
        >
          <span>OUTLINE</span>
          {isOutlineExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </button>
        {isOutlineExpanded && (
          <div className="px-4 py-2 text-[11px] text-[#8B949E] bg-[#0A0D10]/50 border-t border-[#2F343A]/50">
            <div>Home (Component)</div>
            <div className="pl-2">todos (state)</div>
            <div className="pl-2">handleAddTodo (function)</div>
          </div>
        )}

        <button
          onClick={() => setIsTimelineExpanded(!isTimelineExpanded)}
          className="w-full px-3 py-1.5 flex items-center justify-between hover:bg-[#1E222A] font-semibold text-[#8B949E] border-t border-[#2F343A] transition-colors"
        >
          <span>TIMELINE</span>
          {isTimelineExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </button>
        {isTimelineExpanded && (
          <div className="px-4 py-2 text-[11px] text-[#8B949E] bg-[#0A0D10]/50 border-t border-[#2F343A]/50">
            <div>3 min ago: Updated index.tsx</div>
            <div>12 min ago: Initial commit</div>
          </div>
        )}
      </div>
    </div>
  );
}
