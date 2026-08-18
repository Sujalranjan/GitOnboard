"use client";

import React, { useState, useEffect, useCallback } from "react";
import { HeaderGlobal } from "./HeaderGlobal";
import { SidebarNav } from "./SidebarNav";
import { FileExplorerPanel } from "./FileExplorerPanel";
import { CodeEditorPanel } from "./CodeEditorPanel";
import { TerminalPanel } from "./TerminalPanel";
import { AIAgentPanel } from "./AIAgentPanel";
import { KeyboardShortcutsModal } from "./KeyboardShortcutsModal";
import { useVerificationWorkspace } from "@/hooks/useVerificationWorkspace";

interface WorkspaceLayoutProps {
  initialRepoName?: string;
}

export function WorkspaceLayout({ initialRepoName = "default" }: WorkspaceLayoutProps) {
  const [activeNavTab, setActiveNavTab] = useState("editor");
  const [isFileExplorerOpen, setIsFileExplorerOpen] = useState(true);
  const [isTerminalOpen, setIsTerminalOpen] = useState(true);
  const [isAIAgentOpen, setIsAIAgentOpen] = useState(true);
  const [isShortcutsModalOpen, setIsShortcutsModalOpen] = useState(false);

  // Resizable panel dimensions with localStorage persistence
  const [explorerWidth, setExplorerWidth] = useState<number>(240);
  const [terminalHeight, setTerminalHeight] = useState<number>(224);
  const [aiAgentWidth, setAiAgentWidth] = useState<number>(340);
  const [activeResizer, setActiveResizer] = useState<"explorer" | "terminal" | "aiAgent" | null>(null);

  // Load saved preferences on client mount
  useEffect(() => {
    try {
      const savedExp = localStorage.getItem("gitonboard_explorer_width");
      if (savedExp) setExplorerWidth(Math.max(180, Math.min(500, parseInt(savedExp, 10))));

      const savedTerm = localStorage.getItem("gitonboard_terminal_height");
      if (savedTerm) setTerminalHeight(Math.max(120, Math.min(600, parseInt(savedTerm, 10))));

      const savedAgent = localStorage.getItem("gitonboard_ai_agent_width");
      if (savedAgent) setAiAgentWidth(Math.max(260, Math.min(650, parseInt(savedAgent, 10))));
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  // Explorer Resize Dragging
  const handleExplorerMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setActiveResizer("explorer");
    const startX = e.clientX;
    const startWidth = explorerWidth;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX;
      const newWidth = Math.max(180, Math.min(500, startWidth + delta));
      setExplorerWidth(newWidth);
      try {
        localStorage.setItem("gitonboard_explorer_width", newWidth.toString());
      } catch {}
    };

    const handleMouseUp = () => {
      setActiveResizer(null);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  // Terminal Resize Dragging
  const handleTerminalMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setActiveResizer("terminal");
    const startY = e.clientY;
    const startHeight = terminalHeight;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = startY - moveEvent.clientY;
      const newHeight = Math.max(120, Math.min(window.innerHeight * 0.75, startHeight + delta));
      setTerminalHeight(newHeight);
      try {
        localStorage.setItem("gitonboard_terminal_height", newHeight.toString());
      } catch {}
    };

    const handleMouseUp = () => {
      setActiveResizer(null);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  // AI Agent Resize Dragging
  const handleAIAgentMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setActiveResizer("aiAgent");
    const startX = e.clientX;
    const startWidth = aiAgentWidth;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = startX - moveEvent.clientX;
      const newWidth = Math.max(260, Math.min(650, startWidth + delta));
      setAiAgentWidth(newWidth);
      try {
        localStorage.setItem("gitonboard_ai_agent_width", newWidth.toString());
      } catch {}
    };

    const handleMouseUp = () => {
      setActiveResizer(null);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  // Consume custom verification workspace hook
  const {
    runState,
    activeFile,
    openTabs,
    editorMode,
    setEditorMode,
    logs,
    handleSelectFile,
    handleCloseTab,
    handleStartTaskPrompt,
    handleTriggerRepair,
  } = useVerificationWorkspace(initialRepoName);

  // Panel toggle callbacks
  const toggleFileExplorer = useCallback(() => setIsFileExplorerOpen((prev) => !prev), []);
  const toggleTerminal = useCallback(() => setIsTerminalOpen((prev) => !prev), []);
  const toggleAIAgent = useCallback(() => setIsAIAgentOpen((prev) => !prev), []);
  const toggleShortcutsModal = useCallback(() => setIsShortcutsModalOpen((prev) => !prev), []);

  // Global Keybindings Listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isCtrlOrMeta = e.ctrlKey || e.metaKey;
      const target = e.target as HTMLElement | null;
      const isInputFocused =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.isContentEditable;

      // 1. Toggle File Explorer: Ctrl+B / Cmd+B
      if (isCtrlOrMeta && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleFileExplorer();
        return;
      }

      // 2. Toggle Terminal: Ctrl+` or Ctrl+J / Cmd+` or Cmd+J
      if (isCtrlOrMeta && (e.key === "`" || e.key.toLowerCase() === "j")) {
        e.preventDefault();
        toggleTerminal();
        return;
      }

      // 3. Toggle AI Agent: Ctrl+L or Ctrl+I / Cmd+L or Cmd+I
      if (isCtrlOrMeta && (e.key.toLowerCase() === "l" || e.key.toLowerCase() === "i")) {
        e.preventDefault();
        toggleAIAgent();
        return;
      }

      // 4. Focus Global Search: Ctrl+K / Cmd+K
      if (isCtrlOrMeta && e.key.toLowerCase() === "k") {
        e.preventDefault();
        const searchInput = document.getElementById("global-search-input") as HTMLInputElement | null;
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
        return;
      }

      // 5. Run Verification: Ctrl+Enter / Cmd+Enter
      if (isCtrlOrMeta && e.key === "Enter") {
        e.preventDefault();
        if (!runState?.isLoading) {
          handleStartTaskPrompt(runState.taskPrompt);
        }
        return;
      }

      // 6. Keyboard Shortcuts Modal: ? (when not typing in input) or Ctrl+Shift+P
      if (
        (e.key === "?" && !isInputFocused) ||
        (isCtrlOrMeta && e.shiftKey && e.key.toLowerCase() === "p")
      ) {
        e.preventDefault();
        toggleShortcutsModal();
        return;
      }

      // 7. Escape: Close open modals
      if (e.key === "Escape") {
        if (isShortcutsModalOpen) {
          e.preventDefault();
          setIsShortcutsModalOpen(false);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleFileExplorer, toggleTerminal, toggleAIAgent, toggleShortcutsModal, runState, handleStartTaskPrompt, isShortcutsModalOpen]);

  return (
    <div className="h-screen w-screen bg-[#0A0D10] text-[#E6EDF3] flex flex-col overflow-hidden font-sans select-none antialiased">
      {/* Top Global Header Bar with Access Ribbon */}
      <HeaderGlobal
        runState={runState}
        onRunVerification={() => handleStartTaskPrompt(runState.taskPrompt)}
        isFileExplorerOpen={isFileExplorerOpen}
        onToggleFileExplorer={toggleFileExplorer}
        isTerminalOpen={isTerminalOpen}
        onToggleTerminal={toggleTerminal}
        isAIAgentOpen={isAIAgentOpen}
        onToggleAIAgent={toggleAIAgent}
        onOpenShortcuts={toggleShortcutsModal}
      />

      {/* Main 4-Column Layout with Interactive Resizers */}
      <div className="flex-1 flex overflow-hidden w-full h-[calc(100vh-48px)]">
        {/* Column 1 (Far Left): Narrow Sidebar Navigation */}
        <SidebarNav
          activeTab={activeNavTab}
          setActiveTab={setActiveNavTab}
          isFileExplorerOpen={isFileExplorerOpen}
          setIsFileExplorerOpen={setIsFileExplorerOpen}
          isTerminalOpen={isTerminalOpen}
          onToggleTerminal={toggleTerminal}
          isAIAgentOpen={isAIAgentOpen}
          onToggleAIAgent={toggleAIAgent}
          onOpenShortcuts={toggleShortcutsModal}
        />

        {/* Column 2: Collapsible & Resizable File Explorer Panel */}
        {isFileExplorerOpen && (
          <>
            <FileExplorerPanel
              activeFile={activeFile}
              onSelectFile={handleSelectFile}
              isOpen={isFileExplorerOpen}
              onClose={() => setIsFileExplorerOpen(false)}
              runState={runState}
              width={explorerWidth}
            />

            {/* Vertical Resize Handle (Explorer <-> Editor) */}
            <div
              onMouseDown={handleExplorerMouseDown}
              className={`w-1 cursor-col-resize hover:w-1.5 transition-all relative flex-shrink-0 group z-10 ${
                activeResizer === "explorer"
                  ? "bg-purple-500 shadow-sm shadow-purple-500/50"
                  : "bg-[#2F343A]/40 hover:bg-purple-500/60"
              }`}
              title="Drag to resize File Explorer"
            >
              <div className="absolute inset-y-0 -left-1 -right-1" />
            </div>
          </>
        )}

        {/* Column 3 (Middle): Primary Workspace Area (Code Editor + Terminal) */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[#0A0D10]">
          {/* Top Half: Code Editor Panel */}
          <CodeEditorPanel
            activeFile={activeFile}
            onSelectFile={handleSelectFile}
            openTabs={openTabs}
            onCloseTab={handleCloseTab}
            runState={runState}
            editorMode={editorMode}
            onSetEditorMode={setEditorMode}
          />

          {/* Bottom Half: Collapsible & Resizable Terminal Panel */}
          {isTerminalOpen && (
            <>
              {/* Horizontal Resize Handle (Editor <-> Terminal) */}
              <div
                onMouseDown={handleTerminalMouseDown}
                className={`h-1 cursor-row-resize hover:h-1.5 transition-all relative flex-shrink-0 group z-10 ${
                  activeResizer === "terminal"
                    ? "bg-purple-500 shadow-sm shadow-purple-500/50"
                    : "bg-[#2F343A]/60 hover:bg-purple-500/60"
                }`}
                title="Drag to resize Terminal"
              >
                <div className="absolute inset-x-0 -top-1 -bottom-1" />
              </div>

              <TerminalPanel
                isOpen={isTerminalOpen}
                onClose={() => setIsTerminalOpen(false)}
                runState={runState}
                height={terminalHeight}
              />
            </>
          )}
        </div>

        {/* Column 4 (Right): Collapsible & Resizable AI Agent Panel */}
        {isAIAgentOpen && (
          <>
            {/* Vertical Resize Handle (Editor <-> AI Agent) */}
            <div
              onMouseDown={handleAIAgentMouseDown}
              className={`w-1 cursor-col-resize hover:w-1.5 transition-all relative flex-shrink-0 group z-10 ${
                activeResizer === "aiAgent"
                  ? "bg-purple-500 shadow-sm shadow-purple-500/50"
                  : "bg-[#2F343A]/40 hover:bg-purple-500/60"
              }`}
              title="Drag to resize AI Agent panel"
            >
              <div className="absolute inset-y-0 -left-1 -right-1" />
            </div>

            <AIAgentPanel
              isOpen={isAIAgentOpen}
              onClose={() => setIsAIAgentOpen(false)}
              onSelectFile={handleSelectFile}
              runState={runState}
              onStartTaskPrompt={handleStartTaskPrompt}
              onTriggerRepair={handleTriggerRepair}
              width={aiAgentWidth}
            />
          </>
        )}
      </div>

      {/* Keyboard Shortcuts Cheat Sheet Modal */}
      <KeyboardShortcutsModal
        isOpen={isShortcutsModalOpen}
        onClose={() => setIsShortcutsModalOpen(false)}
      />
    </div>
  );
}


