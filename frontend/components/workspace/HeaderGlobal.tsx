"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Sparkles,
  ChevronDown,
  Search,
  UserPlus,
  Settings,
  Bell,
  Check,
  GitBranch,
  Home,
} from "lucide-react";

export function HeaderGlobal() {
  const [selectedProject, setSelectedProject] = useState("my-project");
  const [selectedBranch, setSelectedBranch] = useState("main");
  const [isProjectDropdownOpen, setIsProjectDropdownOpen] = useState(false);
  const [isBranchDropdownOpen, setIsBranchDropdownOpen] = useState(false);

  const projects = ["my-project", "gitonboard-core", "ai-backend-service"];
  const branches = ["main", "feature/ai-verification", "dev", "fix/auth-flow"];

  return (
    <header className="h-12 bg-[#14181E] border-b border-[#2F343A] flex items-center justify-between px-3 text-[#E6EDF3] select-none z-20 flex-shrink-0">
      {/* Left Section: Logo & Selectors */}
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2 pr-2 border-r border-[#2F343A] hover:opacity-90 transition-opacity">
          <div className="w-6 h-6 rounded-md bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center shadow-sm shadow-purple-500/20">
            <Sparkles className="w-3.5 h-3.5 text-white animate-pulse" />
          </div>
          <span className="font-semibold text-sm tracking-wide text-white flex items-center gap-1.5">
            AI Workspace
          </span>
        </Link>

        {/* Project Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => {
              setIsProjectDropdownOpen(!isProjectDropdownOpen);
              setIsBranchDropdownOpen(false);
            }}
            className="flex items-center gap-1.5 text-xs bg-[#0A0D10] hover:bg-[#1E222A] px-2.5 py-1 rounded border border-[#2F343A] transition-colors text-[#E6EDF3]"
          >
            <span className="text-[#8B949E]">project:</span>
            <span className="font-medium text-purple-400">{selectedProject}</span>
            <ChevronDown className="w-3 h-3 text-[#8B949E]" />
          </button>

          {isProjectDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 w-44 bg-[#14181E] border border-[#2F343A] rounded shadow-xl py-1 z-50 text-xs">
              <div className="px-2 py-1 text-[10px] uppercase font-bold text-[#8B949E] border-b border-[#2F343A]">
                Switch Project
              </div>
              {projects.map((proj) => (
                <button
                  key={proj}
                  onClick={() => {
                    setSelectedProject(proj);
                    setIsProjectDropdownOpen(false);
                  }}
                  className="w-full text-left px-3 py-1.5 hover:bg-[#1E222A] flex items-center justify-between transition-colors text-[#E6EDF3]"
                >
                  <span>{proj}</span>
                  {selectedProject === proj && <Check className="w-3 h-3 text-purple-400" />}
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
            className="flex items-center gap-1.5 text-xs bg-[#0A0D10] hover:bg-[#1E222A] px-2.5 py-1 rounded border border-[#2F343A] transition-colors text-[#E6EDF3]"
          >
            <GitBranch className="w-3 h-3 text-[#8B949E]" />
            <span className="font-mono text-[#E6EDF3]">{selectedBranch}</span>
            <ChevronDown className="w-3 h-3 text-[#8B949E]" />
          </button>

          {isBranchDropdownOpen && (
            <div className="absolute top-full left-0 mt-1 w-48 bg-[#14181E] border border-[#2F343A] rounded shadow-xl py-1 z-50 text-xs">
              <div className="px-2 py-1 text-[10px] uppercase font-bold text-[#8B949E] border-b border-[#2F343A]">
                Switch Branch
              </div>
              {branches.map((branch) => (
                <button
                  key={branch}
                  onClick={() => {
                    setSelectedBranch(branch);
                    setIsBranchDropdownOpen(false);
                  }}
                  className="w-full text-left px-3 py-1.5 hover:bg-[#1E222A] flex items-center justify-between transition-colors font-mono text-[#E6EDF3]"
                >
                  <span>{branch}</span>
                  {selectedBranch === branch && <Check className="w-3 h-3 text-purple-400" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Middle Section: Centralized Search Bar */}
      <div className="flex-1 max-w-md mx-6">
        <div className="relative flex items-center">
          <Search className="w-3.5 h-3.5 absolute left-3 text-[#8B949E] pointer-events-none" />
          <input
            type="text"
            placeholder="Search files, symbols, commands..."
            className="w-full bg-[#0A0D10] border border-[#2F343A] rounded-md py-1 pl-9 pr-12 text-xs text-[#E6EDF3] placeholder-[#8B949E] focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 transition-all"
          />
          <span className="absolute right-2.5 text-[10px] font-mono text-[#8B949E] bg-[#14181E] border border-[#2F343A] px-1.5 py-0.5 rounded pointer-events-none">
            ⌘ K
          </span>
        </div>
      </div>

      {/* Right Section: Invite, Settings, Notifications, Profile */}
      <div className="flex items-center gap-2">
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
