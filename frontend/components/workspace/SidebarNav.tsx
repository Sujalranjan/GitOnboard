"use client";

import React, { useState } from "react";
import {
  Code2,
  GitBranch,
  FolderGit2,
  Blocks,
  Database,
  BookOpen,
  Settings2,
  User,
} from "lucide-react";

interface SidebarNavProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isFileExplorerOpen: boolean;
  setIsFileExplorerOpen: (open: boolean) => void;
}

export function SidebarNav({
  activeTab,
  setActiveTab,
  isFileExplorerOpen,
  setIsFileExplorerOpen,
}: SidebarNavProps) {
  const topNavItems = [
    { id: "editor", icon: Code2, label: "Code / Editor" },
    { id: "git", icon: GitBranch, label: "Source Control" },
    { id: "projects", icon: FolderGit2, label: "Projects / Files" },
    { id: "extensions", icon: Blocks, label: "API & Extensions" },
    { id: "database", icon: Database, label: "Database" },
  ];

  const bottomNavItems = [
    { id: "docs", icon: BookOpen, label: "Documentation" },
    { id: "settings", icon: Settings2, label: "Settings" },
    { id: "account", icon: User, label: "Account" },
  ];

  const handleItemClick = (id: string) => {
    setActiveTab(id);
    if (id === "editor" || id === "projects") {
      setIsFileExplorerOpen(!isFileExplorerOpen);
    }
  };

  return (
    <aside className="w-12 bg-[#0A0D10] border-r border-[#2F343A] flex flex-col justify-between items-center py-2 flex-shrink-0 select-none z-10">
      {/* Top Nav Group */}
      <div className="flex flex-col gap-1 w-full items-center">
        {topNavItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => handleItemClick(item.id)}
              title={item.label}
              className={`relative w-9 h-9 rounded-lg flex items-center justify-center transition-all group ${
                isActive
                  ? "bg-purple-600/20 text-purple-400 font-semibold shadow-sm"
                  : "text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#14181E]"
              }`}
            >
              {/* Purple Left Highlight Bar for Active State */}
              {isActive && (
                <span className="absolute left-0 top-1.5 bottom-1.5 w-1 bg-purple-500 rounded-r-md shadow-sm shadow-purple-500/50" />
              )}
              <Icon className={`w-5 h-5 transition-transform group-hover:scale-105 ${isActive ? "text-purple-400" : ""}`} />
            </button>
          );
        })}
      </div>

      {/* Bottom Nav Group */}
      <div className="flex flex-col gap-1 w-full items-center pt-2 border-t border-[#2F343A]/60">
        {bottomNavItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => handleItemClick(item.id)}
              title={item.label}
              className={`relative w-9 h-9 rounded-lg flex items-center justify-center transition-all group ${
                isActive
                  ? "bg-purple-600/20 text-purple-400 font-semibold shadow-sm"
                  : "text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#14181E]"
              }`}
            >
              {isActive && (
                <span className="absolute left-0 top-1.5 bottom-1.5 w-1 bg-purple-500 rounded-r-md shadow-sm shadow-purple-500/50" />
              )}
              <Icon className="w-5 h-5 transition-transform group-hover:scale-105" />
            </button>
          );
        })}
      </div>
    </aside>
  );
}
