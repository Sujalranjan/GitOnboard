"use client";

import React from "react";
import {
  Code2,
  FolderTree,
  Terminal,
  Sparkles,
  GitBranch,
  Database,
  Keyboard,
  BookOpen,
  Settings2,
  User,
} from "lucide-react";

interface SidebarNavProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isFileExplorerOpen: boolean;
  setIsFileExplorerOpen: (open: boolean) => void;
  isTerminalOpen?: boolean;
  onToggleTerminal?: () => void;
  isAIAgentOpen?: boolean;
  onToggleAIAgent?: () => void;
  onOpenShortcuts?: () => void;
}

export function SidebarNav({
  activeTab,
  setActiveTab,
  isFileExplorerOpen,
  setIsFileExplorerOpen,
  isTerminalOpen,
  onToggleTerminal,
  isAIAgentOpen,
  onToggleAIAgent,
  onOpenShortcuts,
}: SidebarNavProps) {
  const topNavItems = [
    { id: "editor", icon: Code2, label: "Code / Editor" },
    { id: "projects", icon: FolderTree, label: "Explorer (Ctrl+B)", isPanelToggle: true, isOpen: isFileExplorerOpen },
    { id: "terminal", icon: Terminal, label: "Terminal & Tests (Ctrl+`)", isPanelToggle: true, isOpen: isTerminalOpen },
    { id: "agent", icon: Sparkles, label: "AI Agent Chat (Ctrl+L)", isPanelToggle: true, isOpen: isAIAgentOpen },
    { id: "git", icon: GitBranch, label: "Source Control" },
    { id: "database", icon: Database, label: "Database" },
  ];

  const bottomNavItems = [
    { id: "shortcuts", icon: Keyboard, label: "Keyboard Shortcuts (?)" },
    { id: "docs", icon: BookOpen, label: "Documentation" },
    { id: "settings", icon: Settings2, label: "Settings" },
    { id: "account", icon: User, label: "Account" },
  ];

  const handleItemClick = (id: string) => {
    setActiveTab(id);
    if (id === "projects" || id === "editor") {
      setIsFileExplorerOpen(!isFileExplorerOpen);
    } else if (id === "terminal" && onToggleTerminal) {
      onToggleTerminal();
    } else if (id === "agent" && onToggleAIAgent) {
      onToggleAIAgent();
    } else if (id === "shortcuts" && onOpenShortcuts) {
      onOpenShortcuts();
    }
  };

  return (
    <aside className="w-12 bg-[#0A0D10] border-r border-[#2F343A] flex flex-col justify-between items-center py-2 flex-shrink-0 select-none z-10">
      {/* Top Nav Group */}
      <div className="flex flex-col gap-1 w-full items-center">
        {topNavItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id || (item.isPanelToggle && item.isOpen);
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

