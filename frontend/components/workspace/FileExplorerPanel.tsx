"use client";

import React, { useState, useEffect } from "react";
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
  Folder,
  FolderOpen,
  Code2,
  Box,
  Layers,
  RefreshCw,
} from "lucide-react";
import { RunState } from "@/types/workspace";
import {
  FileTreeNode,
  SymbolItem,
  getRepositoryStructure,
  getFileSymbols,
} from "@/services/repositoryApi";

interface FileExplorerPanelProps {
  activeFile: string;
  onSelectFile: (filePath: string) => void;
  isOpen: boolean;
  onClose: () => void;
  runState?: RunState;
}

// Recursive Tree Node Component
function TreeNode({
  node,
  activeFile,
  onSelectFile,
  depth = 0,
}: {
  node: FileTreeNode;
  activeFile: string;
  onSelectFile: (path: string) => void;
  depth?: number;
}) {
  const [isOpen, setIsOpen] = useState(depth < 2);
  const isDirectory = node.type === "directory" || Boolean(node.children);

  const renderFileIcon = (fileName: string) => {
    const lower = fileName.toLowerCase();
    if (lower.endsWith(".tsx") || lower.endsWith(".ts")) {
      return <FileCode className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />;
    }
    if (lower.endsWith(".js") || lower.endsWith(".jsx") || lower.endsWith(".mjs")) {
      return <FileCode className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />;
    }
    if (lower.endsWith(".json") || lower.endsWith(".toml")) {
      return <FileJson className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />;
    }
    if (lower.endsWith(".md") || lower.endsWith(".txt")) {
      return <FileText className="w-3.5 h-3.5 text-sky-400 flex-shrink-0" />;
    }
    if (lower.startsWith(".env")) {
      return <Lock className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />;
    }
    if (lower === ".gitignore" || lower.endsWith(".lock")) {
      return <GitBranch className="w-3.5 h-3.5 text-orange-400 flex-shrink-0" />;
    }
    return <File className="w-3.5 h-3.5 text-[#8B949E] flex-shrink-0" />;
  };

  if (isDirectory) {
    return (
      <div>
        <button
          onClick={() => setIsOpen(!isOpen)}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
          className="w-full py-1 flex items-center gap-1.5 hover:bg-[#1E222A] text-[#E6EDF3] transition-colors text-[11px] font-medium"
        >
          {isOpen ? (
            <ChevronDown className="w-3 h-3 text-[#8B949E]" />
          ) : (
            <ChevronRight className="w-3 h-3 text-[#8B949E]" />
          )}
          {isOpen ? (
            <FolderOpen className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
          ) : (
            <Folder className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
          )}
          <span className="truncate">{node.name}</span>
        </button>

        {isOpen && node.children && (
          <div>
            {node.children.map((child, idx) => (
              <TreeNode
                key={`${child.path || node.path}-${child.name}-${idx}`}
                node={child}
                activeFile={activeFile}
                onSelectFile={onSelectFile}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const isActive = activeFile === node.path;
  return (
    <button
      onClick={() => onSelectFile(node.path)}
      style={{ paddingLeft: `${depth * 12 + 16}px` }}
      className={`w-full py-1 flex items-center gap-2 transition-colors text-[11px] font-mono ${
        isActive
          ? "bg-purple-600/30 text-white font-medium border-l-2 border-purple-500"
          : "hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3]"
      }`}
    >
      {renderFileIcon(node.name)}
      <span className="truncate">{node.name}</span>
    </button>
  );
}

export function FileExplorerPanel({
  activeFile,
  onSelectFile,
  isOpen,
  onClose,
  runState,
}: FileExplorerPanelProps) {
  const repoName = runState?.repoId || "my-project";

  const [treeHierarchy, setTreeHierarchy] = useState<FileTreeNode | null>(null);
  const [symbols, setSymbols] = useState<SymbolItem[]>([]);
  const [loadingStructure, setLoadingStructure] = useState(true);
  const [isOutlineExpanded, setIsOutlineExpanded] = useState(true);

  // Recursively finds the first real file in the scanned hierarchy
  const findFirstValidFile = (node: FileTreeNode | null): string | null => {
    if (!node) return null;
    if (node.type === "file" && node.path) {
      return node.path;
    }
    if (node.children && node.children.length > 0) {
      for (const child of node.children) {
        const found = findFirstValidFile(child);
        if (found) return found;
      }
    }
    return null;
  };

  // Fetch real directory structure on mount or repo change
  useEffect(() => {
    let isMounted = true;
    setLoadingStructure(true);

    getRepositoryStructure(repoName)
      .then((tree) => {
        if (isMounted) {
          setTreeHierarchy(tree);
          setLoadingStructure(false);

          // Automatically select the first valid file if none is active
          if (!activeFile && tree) {
            const firstFile = findFirstValidFile(tree);
            if (firstFile) {
              onSelectFile(firstFile);
            }
          }
        }
      })
      .catch(() => {
        if (isMounted) setLoadingStructure(false);
      });

    return () => {
      isMounted = false;
    };
  }, [repoName, activeFile, onSelectFile]);

  // Fetch real AST symbols for active file
  useEffect(() => {
    if (!activeFile) return;

    let isMounted = true;
    getFileSymbols(repoName, activeFile).then((data) => {
      if (isMounted) {
        setSymbols(data);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [repoName, activeFile]);

  if (!isOpen) return null;

  return (
    <div className="w-60 bg-[#14181E] border-r border-[#2F343A] flex flex-col h-full select-none flex-shrink-0 text-[#E6EDF3]">
      {/* Top Header */}
      <div className="h-9 px-3 border-b border-[#2F343A] flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-[#8B949E]">
        <div className="flex items-center gap-1.5">
          <Folder className="w-3.5 h-3.5 text-purple-400" />
          <span className="truncate">{repoName}</span>
        </div>
        <div className="flex items-center gap-1 text-[#8B949E]">
          <button
            onClick={() => {
              setLoadingStructure(true);
              getRepositoryStructure(repoName).then((t) => {
                setTreeHierarchy(t);
                setLoadingStructure(false);
              });
            }}
            className="hover:text-[#E6EDF3] transition-colors p-0.5 rounded"
            title="Refresh Structure"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Recursive File Tree Area */}
      <div className="flex-1 overflow-y-auto py-1 text-xs scrollbar-thin">
        {loadingStructure ? (
          <div className="p-3 text-xs text-[#8B949E] font-mono flex items-center gap-2">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-purple-400" />
            <span>Loading tree...</span>
          </div>
        ) : treeHierarchy ? (
          <TreeNode node={treeHierarchy} activeFile={activeFile} onSelectFile={onSelectFile} />
        ) : (
          <div className="p-3 text-xs text-[#8B949E] italic">No directory structure found.</div>
        )}
      </div>

      {/* Real AST Symbols / OUTLINE Panel */}
      <div className="border-t border-[#2F343A] text-xs">
        <button
          onClick={() => setIsOutlineExpanded(!isOutlineExpanded)}
          className="w-full px-3 py-1.5 flex items-center justify-between hover:bg-[#1E222A] font-semibold text-[#8B949E] transition-colors"
        >
          <span className="flex items-center gap-1.5 uppercase tracking-wider text-[10px]">
            <Code2 className="w-3.5 h-3.5 text-purple-400" />
            OUTLINE / SYMBOLS ({symbols.length})
          </span>
          {isOutlineExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </button>

        {isOutlineExpanded && (
          <div className="px-2 py-1 text-[11px] font-mono text-[#8B949E] bg-[#0A0D10]/80 border-t border-[#2F343A]/50 max-h-40 overflow-y-auto space-y-1 scrollbar-thin">
            {symbols.length > 0 ? (
              symbols.map((sym, idx) => (
                <div key={idx} className="flex items-center gap-1.5 py-0.5 px-1 hover:bg-[#1E222A] rounded">
                  {sym.type === "class" ? (
                    <Box className="w-3 h-3 text-amber-400 flex-shrink-0" />
                  ) : sym.type === "import" ? (
                    <Layers className="w-3 h-3 text-sky-400 flex-shrink-0" />
                  ) : (
                    <Code2 className="w-3 h-3 text-purple-400 flex-shrink-0" />
                  )}
                  <span className="text-[#E6EDF3] truncate">{sym.name}</span>
                  {sym.line_number && <span className="text-[9px] text-[#8B949E] ml-auto">:{sym.line_number}</span>}
                </div>
              ))
            ) : (
              <div className="italic text-[10px] text-[#8B949E] p-1">No symbols extracted for active file.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
