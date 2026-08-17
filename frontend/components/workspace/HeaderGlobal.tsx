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
} from "lucide-react";
import { RunState } from "@/types/workspace";

interface HeaderGlobalProps {
  runState?: RunState;
  onRunVerification?: () => void;
}

export function HeaderGlobal({ runState, onRunVerification }: HeaderGlobalProps) {
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
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, currentRepo]);

  return (
    <header className="h-12 bg-[#14181E] border-b border-[#2F343A] flex items-center justify-between px-3 text-[#E6EDF3] select-none z-20 flex-shrink-0">
      {/* Left Section: Logo & Dynamic Project / Branch Selectors */}
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2 pr-2 border-r border-[#2F343A] hover:opacity-90 transition-opacity">
          <div className="w-6 h-6 rounded-md bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center shadow-sm shadow-purple-500/20">
            <Sparkles className="w-3.5 h-3.5 text-white animate-pulse" />
          </div>
          <span className="font-semibold text-sm tracking-wide text-white flex items-center gap-1.5">
            AI Workspace
          </span>
        </Link>

        {/* Dynamic Project Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => {
              setIsProjectDropdownOpen(!isProjectDropdownOpen);
              setIsBranchDropdownOpen(false);
            }}
            className="flex items-center gap-1.5 text-xs bg-[#0A0D10] hover:bg-[#1E222A] px-2.5 py-1 rounded border border-[#2F343A] transition-colors text-[#E6EDF3]"
          >
            <span className="text-[#8B949E]">project:</span>
            <span className="font-medium text-purple-400 truncate max-w-[120px]">{currentRepo}</span>
            <ChevronDown className="w-3 h-3 text-[#8B949E]" />
          </button>

          {isProjectDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 w-52 bg-[#14181E] border border-[#2F343A] rounded shadow-xl py-1 z-50 text-xs">
              <div className="px-2 py-1 text-[10px] uppercase font-bold text-[#8B949E] border-b border-[#2F343A]">
                Registered Repositories ({repositories.length})
              </div>
              {repositories.length > 0 ? (
                repositories.map((repo) => (
                  <button
                    key={repo.id}
                    onClick={() => handleSelectProject(repo.name)}
                    className="w-full text-left px-3 py-1.5 hover:bg-[#1E222A] flex items-center justify-between transition-colors text-[#E6EDF3]"
                  >
                    <span className="truncate">{repo.name}</span>
                    {currentRepo === repo.name && <Check className="w-3 h-3 text-purple-400 flex-shrink-0" />}
                  </button>
                ))
              ) : (
                <button
                  onClick={() => handleSelectProject(currentRepo)}
                  className="w-full text-left px-3 py-1.5 hover:bg-[#1E222A] text-[#E6EDF3]"
                >
                  {currentRepo}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Dynamic Branch Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => {
              setIsBranchDropdownOpen(!isBranchDropdownOpen);
              setIsProjectDropdownOpen(false);
            }}
            className="flex items-center gap-1.5 text-xs bg-[#0A0D10] hover:bg-[#1E222A] px-2.5 py-1 rounded border border-[#2F343A] transition-colors text-[#E6EDF3]"
          >
            <GitBranch className="w-3 h-3 text-[#8B949E]" />
            <span className="font-mono text-[#E6EDF3]">{selectedBranch}</span>
            <ChevronDown className="w-3 h-3 text-[#8B949E]" />
          </button>

          {isBranchDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 w-44 bg-[#14181E] border border-[#2F343A] rounded shadow-xl py-1 z-50 text-xs">
              <div className="px-2 py-1 text-[10px] uppercase font-bold text-[#8B949E] border-b border-[#2F343A]">
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
      <div className="flex-1 max-w-md mx-6 relative">
        <div className="relative flex items-center">
          <Search className="w-3.5 h-3.5 absolute left-3 text-[#8B949E] pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => {
              if (searchResults.length > 0) setShowSearchDropdown(true);
            }}
            placeholder="Search files, symbols, AST entities (⌘ K)..."
            className="w-full bg-[#0A0D10] border border-[#2F343A] rounded-md py-1 pl-9 pr-12 text-xs text-[#E6EDF3] placeholder-[#8B949E] focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 transition-all font-mono"
          />
          <span className="absolute right-2.5 text-[10px] font-mono text-[#8B949E] bg-[#14181E] border border-[#2F343A] px-1.5 py-0.5 rounded pointer-events-none">
            ⌘ K
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

      {/* Right Section: Prominent Run Verification & Actions */}
      <div className="flex items-center gap-2">
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
          <span>Run Verification</span>
        </button>

        <button className="flex items-center gap-1.5 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/40 px-2.5 py-1 rounded text-xs font-medium transition-colors">
          <UserPlus className="w-3.5 h-3.5" />
          <span>Invite</span>
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
