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
  Settings,
  Globe,
  Palette,
  Database,
  Terminal,
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

/**
 * Returns a file-type specific icon based on extension.
 */
function renderFileIcon(fileName: string) {
  const lower = fileName.toLowerCase();

  // Python
  if (lower.endsWith(".py") || lower.endsWith(".pyw") || lower.endsWith(".ipynb")) {
    return <FileCode className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />;
  }
  // TypeScript
  if (lower.endsWith(".tsx") || lower.endsWith(".ts") || lower.endsWith(".mts")) {
    return <FileCode className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />;
  }
  // JavaScript
  if (lower.endsWith(".jsx") || lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) {
    return <FileCode className="w-3.5 h-3.5 text-amber-300 flex-shrink-0" />;
  }
  // JSON / Data
  if (lower.endsWith(".json") || lower.endsWith(".jsonc")) {
    return <FileJson className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />;
  }
  // Markdown / Docs / Text
  if (lower.endsWith(".md") || lower.endsWith(".mdx") || lower.endsWith(".txt") || lower.endsWith(".rst")) {
    return <FileText className="w-3.5 h-3.5 text-sky-400 flex-shrink-0" />;
  }
  // Config / TOML / YAML / INI
  if (lower.endsWith(".toml") || lower.endsWith(".yaml") || lower.endsWith(".yml") || lower.endsWith(".ini") || lower.endsWith(".cfg")) {
    return <Settings className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />;
  }
  // Web / HTML / SVG
  if (lower.endsWith(".html") || lower.endsWith(".htm") || lower.endsWith(".svg")) {
    return <Globe className="w-3.5 h-3.5 text-orange-400 flex-shrink-0" />;
  }
  // Styles / CSS / SCSS
  if (lower.endsWith(".css") || lower.endsWith(".scss") || lower.endsWith(".sass") || lower.endsWith(".less")) {
    return <Palette className="w-3.5 h-3.5 text-pink-400 flex-shrink-0" />;
  }
  // Database / SQL
  if (lower.endsWith(".sql") || lower.endsWith(".db") || lower.endsWith(".sqlite")) {
    return <Database className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />;
  }
  // Shell / Script
  if (lower.endsWith(".sh") || lower.endsWith(".bash") || lower.endsWith(".zsh") || lower.endsWith(".ps1") || lower.endsWith(".bat")) {
    return <Terminal className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />;
  }
  // Git / Env / Security
  if (lower.startsWith(".env")) {
    return <Lock className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />;
  }
  if (lower.startsWith(".git") || lower.endsWith(".lock")) {
    return <GitBranch className="w-3.5 h-3.5 text-orange-400 flex-shrink-0" />;
  }

  // Generic Document
  return <File className="w-3.5 h-3.5 text-[#8B949E] flex-shrink-0" />;
}

/**
 * Sanitizes the raw tree hierarchy to strictly separate real filesystem directories
 * and files, removing any nested AST code structures (classes/functions) from the file tree.
 */
function sanitizeFileTree(node: FileTreeNode): FileTreeNode {
  if (node.type === "directory") {
    const validChildren = (node.children || [])
      .filter((child) => child.type === "directory" || child.type === "file" || child.name.includes("."))
      .map((child) => {
        // If node is a file, strip any AST symbol children
        if (child.type === "file" || (!child.type && child.name.includes("."))) {
          return {
            name: child.name,
            type: "file" as const,
            path: child.path,
          };
        }
        return sanitizeFileTree(child);
      })
      .sort((a, b) => {
        const aIsDir = a.type === "directory";
        const bIsDir = b.type === "directory";
        if (aIsDir && !bIsDir) return -1;
        if (!aIsDir && bIsDir) return 1;
        return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      });

    return {
      ...node,
      type: "directory",
      children: validChildren,
    };
  }

  return {
    name: node.name,
    type: "file",
    path: node.path,
  };
}

/**
 * Recursively finds the first real file in the scanned hierarchy.
 */
function findFirstValidFile(node: FileTreeNode | null): string | null {
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
  const isDirectory = node.type === "directory";
  const [isOpen, setIsOpen] = useState(depth < 2);

  if (isDirectory) {
    return (
      <div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(!isOpen);
          }}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
          className="w-full py-1 px-1.5 flex items-center gap-1.5 hover:bg-[#1E222A] text-[#E6EDF3] transition-colors text-[11px] font-medium select-none group"
        >
          <span className="w-3.5 h-3.5 flex items-center justify-center text-[#8B949E] group-hover:text-[#E6EDF3]">
            {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </span>
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

  // File Node (No chevron, clicking opens in editor)
  const isActive = activeFile === node.path;
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onSelectFile(node.path);
      }}
      style={{ paddingLeft: `${depth * 12 + 22}px` }}
      className={`w-full py-1 px-1.5 flex items-center gap-2 transition-colors text-[11px] font-mono select-none ${
        isActive
          ? "bg-purple-600/25 text-purple-200 font-semibold border-l-2 border-purple-400 shadow-sm"
          : "hover:bg-[#1E222A] text-[#8B949E] hover:text-[#E6EDF3]"
      }`}
      title={node.path || node.name}
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

  // Fetch real directory structure on mount or repo change
  useEffect(() => {
    let isMounted = true;
    setLoadingStructure(true);

    getRepositoryStructure(repoName)
      .then((tree) => {
        if (isMounted) {
          const sanitizedTree = sanitizeFileTree(tree);
          setTreeHierarchy(sanitizedTree);
          setLoadingStructure(false);

          // Automatically select the first valid file if none is active
          if (!activeFile && sanitizedTree) {
            const firstFile = findFirstValidFile(sanitizedTree);
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
    if (!activeFile) {
      setSymbols([]);
      return;
    }

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
      <div className="h-9 px-3 border-b border-[#2F343A] flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-[#8B949E] flex-shrink-0">
        <div className="flex items-center gap-1.5">
          <Folder className="w-3.5 h-3.5 text-purple-400" />
          <span className="truncate">{repoName}</span>
        </div>
        <div className="flex items-center gap-1 text-[#8B949E]">
          <button
            onClick={() => {
              setLoadingStructure(true);
              getRepositoryStructure(repoName).then((t) => {
                setTreeHierarchy(sanitizeFileTree(t));
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
      <div className="border-t border-[#2F343A] text-xs flex-shrink-0">
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
                <div key={idx} className="flex items-center gap-1.5 py-0.5 px-1 hover:bg-[#1E222A] rounded cursor-pointer">
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
