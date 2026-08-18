"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  ChevronDown,
  Search,
  UserPlus,
  Settings,
  Bell,
  Check,
  GitBranch,
  Play,
  RefreshCw,
  Folder,
  FolderTree,
  Terminal,
  Keyboard,
} from "lucide-react";
import { RunState } from "@/types/workspace";

interface HeaderGlobalProps {
  runState?: RunState;
  onRunVerification?: () => void;
  isFileExplorerOpen?: boolean;
  onToggleFileExplorer?: () => void;
  isTerminalOpen?: boolean;
  onToggleTerminal?: () => void;
  isAIAgentOpen?: boolean;
  onToggleAIAgent?: () => void;
  onOpenShortcuts?: () => void;
}

export function HeaderGlobal({
  runState,
  onRunVerification,
  isFileExplorerOpen = true,
  onToggleFileExplorer,
  isTerminalOpen = true,
  onToggleTerminal,
  isAIAgentOpen = true,
  onToggleAIAgent,
  onOpenShortcuts,
}: HeaderGlobalProps) {
  const router = useRouter();
  const currentRepo = runState?.repoId || "default";

  const [repositories, setRepositories] = useState<Array<{ id: number | string; name: string; branch: string }>>([]);
  const [selectedProject, setSelectedProject] = useState<string>(currentRepo);
  const [selectedBranch, setSelectedBranch] = useState<string>(runState?.branch || "main");
  const [isProjectDropdownOpen, setIsProjectDropdownOpen] = useState(false);
  const [isBranchDropdownOpen, setIsBranchDropdownOpen] = useState(false);

  // Search Bar state (⌘ K)
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ name: string; type: string; file_path: string }>>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);

  // Fetch registered repositories from GET /api/repos on mount
  useEffect(() => {
    async function fetchRepos() {
      try {
        const res = await fetch("/api/repos");
        if (res.ok) {
          const data = await res.json();
          const repoList = (data.repositories || data || []).map((r: any) => ({
            id: r.id || r.name,
            name: r.project_name || r.name || (r.url ? r.url.split("/").pop().replace(".git", "") : "default"),
            branch: r.branch || r.default_branch || "main",
          }));
          if (repoList.length > 0) {
            setRepositories(repoList);
            const found = repoList.find((r: any) => r.name === currentRepo);
            if (found) {
              setSelectedBranch(found.branch);
            }
          }
        }
      } catch (err) {
        console.warn("Failed to fetch registered repositories:", err);
      }
    }
    fetchRepos();
  }, [currentRepo]);

  // Handle switching projects
  const handleSelectProject = (projName: string) => {
    setSelectedProject(projName);
    setIsProjectDropdownOpen(false);
    router.push(`/repository/${encodeURIComponent(projName)}/workspace`);
  };

  // Perform live symbol / semantic search on input
  useEffect(() => {
    if (!searchQuery.trim() || searchQuery.length < 2) {
      setSearchResults([]);
      setShowSearchDropdown(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsSearching(true);
      setShowSearchDropdown(true);
      try {
        const res = await fetch(`/api/repos/${encodeURIComponent(currentRepo)}/symbols`);
        if (res.ok) {
          const data = await res.json();
          const allSymbols = data.symbols || [];
          const q = searchQuery.toLowerCase();
          const filtered = allSymbols
            .filter((s: any) => (s.name || "").toLowerCase().includes(q) || (s.file_path || "").toLowerCase().includes(q))
            .slice(0, 8);
          setSearchResults(filtered);
        }
      } catch (err) {
        console.warn("Symbol search error:", err);
      } finally {
        setIsSearching(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [searchQuery, currentRepo]);

  return (
    <header className="h-12 bg-[#14181E] border-b border-[#2F343A] px-4 flex items-center justify-between select-none z-20 flex-shrink-0">
      {/* Left Section: Platform Brand + Contextual Dropdowns */}
      <div className="flex items-center gap-3">
        {/* Brand / Logo */}
        <Link href="/dashboard" className="flex items-center gap-2 group mr-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-purple-600 to-indigo-700 flex items-center justify-center shadow-md shadow-purple-600/30 group-hover:scale-105 transition-transform">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-sm bg-gradient-to-r from-white via-purple-100 to-purple-400 bg-clip-text text-transparent tracking-wide">
            GitOnBoard
          </span>
        </Link>

        {/* Project Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => {
              setIsProjectDropdownOpen(!isProjectDropdownOpen);
              setIsBranchDropdownOpen(false);
            }}
            className="flex items-center gap-2 bg-[#0A0D10] border border-[#2F343A] hover:border-purple-500/50 px-2.5 py-1 rounded text-xs transition-colors font-medium text-[#E6EDF3]"
          >
            <Folder className="w-3.5 h-3.5 text-purple-400" />
            <span className="truncate max-w-[140px] font-mono">{selectedProject}</span>
            <ChevronDown className="w-3 h-3 text-[#8B949E]" />
          </button>

          {isProjectDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 w-56 bg-[#14181E] border border-[#2F343A] rounded-md shadow-2xl py-1 z-50 text-xs">
              <div className="px-3 py-1 text-[10px] uppercase font-semibold text-[#8B949E] tracking-wider">
                Select Project
              </div>
              {repositories.map((repo) => (
                <button
                  key={repo.id}
                  onClick={() => handleSelectProject(repo.name)}
                  className="w-full text-left px-3 py-1.5 hover:bg-[#1E222A] flex items-center justify-between transition-colors font-mono"
                >
                  <span className="truncate">{repo.name}</span>
                  {repo.name === selectedProject && <Check className="w-3 h-3 text-purple-400" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Branch Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => {
              setIsBranchDropdownOpen(!isBranchDropdownOpen);
              setIsProjectDropdownOpen(false);
            }}
            className="flex items-center gap-2 bg-[#0A0D10] border border-[#2F343A] hover:border-purple-500/50 px-2.5 py-1 rounded text-xs transition-colors font-mono text-[#8B949E] hover:text-[#E6EDF3]"
          >
            <GitBranch className="w-3.5 h-3.5 text-indigo-400" />
            <span className="truncate max-w-[100px]">{selectedBranch}</span>
            <ChevronDown className="w-3 h-3 text-[#8B949E]" />
          </button>

          {isBranchDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 w-48 bg-[#14181E] border border-[#2F343A] rounded-md shadow-2xl py-1 z-50 text-xs">
              <div className="px-3 py-1 text-[10px] uppercase font-semibold text-[#8B949E] tracking-wider">
                Active Git Branch
              </div>
              <button
                onClick={() => setIsBranchDropdownOpen(false)}
                className="w-full text-left px-3 py-1.5 hover:bg-[#1E222A] flex items-center justify-between transition-colors font-mono text-[#E6EDF3]"
              >
                <span>{selectedBranch}</span>
                <Check className="w-3 h-3 text-purple-400" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Middle Section: Centralized Semantic / Symbol Search Bar */}
      <div className="flex-1 max-w-md mx-4 relative">
        <div className="relative flex items-center">
          <Search className="w-3.5 h-3.5 absolute left-3 text-[#8B949E] pointer-events-none" />
          <input
            id="global-search-input"
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => {
              if (searchResults.length > 0) setShowSearchDropdown(true);
            }}
            placeholder="Search files, symbols, AST entities (Ctrl+K)..."
            className="w-full bg-[#0A0D10] border border-[#2F343A] rounded-md py-1 pl-9 pr-12 text-xs text-[#E6EDF3] placeholder-[#8B949E] focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 transition-all font-mono"
          />
          <span className="absolute right-2.5 text-[10px] font-mono text-[#8B949E] bg-[#14181E] border border-[#2F343A] px-1.5 py-0.5 rounded pointer-events-none">
            Ctrl+K
          </span>
        </div>

        {/* Live Symbol Search Results Dropdown */}
        {showSearchDropdown && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-[#14181E] border border-[#2F343A] rounded-md shadow-2xl py-1 z-50 text-xs max-h-60 overflow-y-auto">
            {isSearching ? (
              <div className="p-2.5 text-slate-400 text-xs font-mono flex items-center gap-2">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-purple-400" />
                <span>Searching symbols...</span>
              </div>
            ) : searchResults.length > 0 ? (
              searchResults.map((sym, idx) => (
                <div
                  key={idx}
                  onClick={() => setShowSearchDropdown(false)}
                  className="px-3 py-1.5 hover:bg-[#1E222A] cursor-pointer flex items-center justify-between font-mono"
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="text-purple-400 font-semibold">{sym.name}</span>
                    <span className="text-[10px] text-[#8B949E] truncate">{sym.file_path}</span>
                  </div>
                  <span className="text-[9px] uppercase px-1 rounded bg-[#2F343A] text-[#8B949E]">
                    {sym.type || "symbol"}
                  </span>
                </div>
              ))
            ) : (
              <div className="p-2.5 text-slate-400 text-xs italic">No symbols found for "{searchQuery}"</div>
            )}
          </div>
        )}
      </div>

      {/* Right Section: View Ribbon + Run Verification & Actions */}
      <div className="flex items-center gap-2.5">
        {/* Top View Access Ribbon */}
        <div className="flex items-center gap-1 bg-[#0A0D10] border border-[#2F343A] p-0.5 rounded-lg">
          <button
            onClick={onToggleFileExplorer}
            className={`px-2 py-1 rounded flex items-center gap-1.5 text-xs font-medium transition-all ${
              isFileExplorerOpen
                ? "bg-purple-600/30 text-purple-300 border border-purple-500/40 shadow-sm"
                : "text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A]"
            }`}
            title="Toggle File Explorer (Ctrl+B)"
          >
            <FolderTree className="w-3.5 h-3.5" />
            <span className="hidden xl:inline text-[11px]">Explorer</span>
          </button>

          <button
            onClick={onToggleTerminal}
            className={`px-2 py-1 rounded flex items-center gap-1.5 text-xs font-medium transition-all ${
              isTerminalOpen
                ? "bg-purple-600/30 text-purple-300 border border-purple-500/40 shadow-sm"
                : "text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A]"
            }`}
            title="Toggle Terminal & Tests (Ctrl+` or Ctrl+J)"
          >
            <Terminal className="w-3.5 h-3.5" />
            <span className="hidden xl:inline text-[11px]">Terminal</span>
          </button>

          <button
            onClick={onToggleAIAgent}
            className={`px-2 py-1 rounded flex items-center gap-1.5 text-xs font-medium transition-all ${
              isAIAgentOpen
                ? "bg-purple-600/30 text-purple-300 border border-purple-500/40 shadow-sm"
                : "text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A]"
            }`}
            title="Toggle AI Agent Panel (Ctrl+L or Ctrl+I)"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span className="hidden xl:inline text-[11px]">AI Agent</span>
          </button>

          <div className="h-3 w-[1px] bg-[#2F343A] mx-0.5" />

          <button
            onClick={onOpenShortcuts}
            className="p-1 rounded text-[#8B949E] hover:text-purple-300 hover:bg-[#1E222A] transition-colors"
            title="Keyboard Shortcuts & Commands (? or Ctrl+Shift+P)"
          >
            <Keyboard className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Primary Action: Run Verification */}
        <button
          onClick={onRunVerification}
          disabled={runState?.isLoading}
          className="flex items-center gap-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-semibold px-3 py-1 rounded text-xs shadow-md shadow-purple-600/30 transition-all disabled:opacity-50"
        >
          {runState?.isLoading ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-purple-200" />
          ) : (
            <Play className="w-3.5 h-3.5 fill-current" />
          )}
          <span className="hidden sm:inline">Run Verification</span>
        </button>

        <button className="flex items-center gap-1.5 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 px-2 py-1 rounded text-xs font-medium transition-colors">
          <UserPlus className="w-3.5 h-3.5" />
          <span className="hidden md:inline">Invite</span>
        </button>

        <button className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Settings">
          <Settings className="w-4 h-4" />
        </button>

        <button className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors relative" title="Notifications">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1 right-1 w-1.5 h-1.5 bg-purple-500 rounded-full"></span>
        </button>

        {/* Profile Avatar */}
        <div className="relative pl-1 border-l border-[#2F343A]">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 text-white font-semibold text-xs flex items-center justify-center ring-1 ring-purple-400/40 shadow-sm cursor-pointer">
            V
          </div>
          <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 border-2 border-[#14181E] rounded-full"></span>
        </div>
      </div>
    </header>
  );
}
