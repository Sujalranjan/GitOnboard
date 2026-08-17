"use client";

import React, { useState } from "react";
import { HeaderGlobal } from "./HeaderGlobal";
import { SidebarNav } from "./SidebarNav";
import { FileExplorerPanel } from "./FileExplorerPanel";
import { CodeEditorPanel } from "./CodeEditorPanel";
import { TerminalPanel } from "./TerminalPanel";
import { AIAgentPanel } from "./AIAgentPanel";
import { useVerificationWorkspace } from "@/hooks/useVerificationWorkspace";

export function WorkspaceLayout() {
  const [activeNavTab, setActiveNavTab] = useState("editor");
  const [isFileExplorerOpen, setIsFileExplorerOpen] = useState(true);
  const [isTerminalOpen, setIsTerminalOpen] = useState(true);
  const [isAIAgentOpen, setIsAIAgentOpen] = useState(true);

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
  } = useVerificationWorkspace();

  return (
    <div className="h-screen w-screen bg-[#0A0D10] text-[#E6EDF3] flex flex-col overflow-hidden font-sans select-none antialiased">
      {/* Top Global Header Bar Across Columns 2, 3, 4 */}
      <HeaderGlobal
        runState={runState}
        onRunVerification={() => handleStartTaskPrompt(runState.taskPrompt)}
      />

      {/* Main 4-Column Layout */}
      <div className="flex-1 flex overflow-hidden w-full h-[calc(100vh-48px)]">
        {/* Column 1 (Far Left): Narrow Sidebar Navigation */}
        <SidebarNav
          activeTab={activeNavTab}
          setActiveTab={setActiveNavTab}
          isFileExplorerOpen={isFileExplorerOpen}
          setIsFileExplorerOpen={setIsFileExplorerOpen}
        />

        {/* Column 2: Collapsible File Explorer Panel */}
        <FileExplorerPanel
          activeFile={activeFile}
          onSelectFile={handleSelectFile}
          isOpen={isFileExplorerOpen}
          onClose={() => setIsFileExplorerOpen(false)}
          runState={runState}
        />

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

          {/* Bottom Half: Horizontally Split Terminal Panel */}
          <TerminalPanel
            isOpen={isTerminalOpen}
            onClose={() => setIsTerminalOpen(false)}
            runState={runState}
          />
        </div>

        {/* Column 4 (Right): Collapsible AI Agent Panel */}
        <AIAgentPanel
          isOpen={isAIAgentOpen}
          onClose={() => setIsAIAgentOpen(false)}
          onSelectFile={handleSelectFile}
          runState={runState}
          onStartTaskPrompt={handleStartTaskPrompt}
          onTriggerRepair={handleTriggerRepair}
        />
      </div>
    </div>
  );
}
