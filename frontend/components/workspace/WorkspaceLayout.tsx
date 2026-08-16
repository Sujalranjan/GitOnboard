"use client";

import React, { useState } from "react";
import { HeaderGlobal } from "./HeaderGlobal";
import { SidebarNav } from "./SidebarNav";
import { FileExplorerPanel } from "./FileExplorerPanel";
import { CodeEditorPanel } from "./CodeEditorPanel";
import { TerminalPanel } from "./TerminalPanel";
import { AIAgentPanel } from "./AIAgentPanel";

export function WorkspaceLayout() {
  const [activeNavTab, setActiveNavTab] = useState("editor");
  const [isFileExplorerOpen, setIsFileExplorerOpen] = useState(true);
  const [isTerminalOpen, setIsTerminalOpen] = useState(true);
  const [isAIAgentOpen, setIsAIAgentOpen] = useState(true);

  const [activeFile, setActiveFile] = useState("src/pages/api/index.tsx");
  const [openTabs, setOpenTabs] = useState([
    "src/pages/api/index.tsx",
    "src/components/TodoItem.tsx",
  ]);

  const handleSelectFile = (filePath: string) => {
    setActiveFile(filePath);
    if (!openTabs.includes(filePath)) {
      setOpenTabs([...openTabs, filePath]);
    }
  };

  const handleCloseTab = (filePath: string) => {
    const newTabs = openTabs.filter((t) => t !== filePath);
    setOpenTabs(newTabs);
    if (activeFile === filePath && newTabs.length > 0) {
      setActiveFile(newTabs[newTabs.length - 1]);
    }
  };

  return (
    <div className="h-screen w-screen bg-[#0A0D10] text-[#E6EDF3] flex flex-col overflow-hidden font-sans select-none antialiased">
      {/* Top Global Header Bar Across Columns 2, 3, 4 */}
      <HeaderGlobal />

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
        />

        {/* Column 3 (Middle): Primary Workspace Area (Code Editor + Terminal) */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[#0A0D10]">
          {/* Top Half: Code Editor Panel */}
          <CodeEditorPanel
            activeFile={activeFile}
            onSelectFile={handleSelectFile}
            openTabs={openTabs}
            onCloseTab={handleCloseTab}
          />

          {/* Bottom Half: Horizontally Split Terminal Panel */}
          <TerminalPanel
            isOpen={isTerminalOpen}
            onClose={() => setIsTerminalOpen(false)}
          />
        </div>

        {/* Column 4 (Right): Collapsible AI Agent Panel */}
        <AIAgentPanel
          isOpen={isAIAgentOpen}
          onClose={() => setIsAIAgentOpen(false)}
          onSelectFile={handleSelectFile}
        />
      </div>
    </div>
  );
}
