"use client";

import React from "react";
import { X, Keyboard, Command, Sparkles, Terminal, FolderTree, Play, Search } from "lucide-react";

interface KeyboardShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function KeyboardShortcutsModal({ isOpen, onClose }: KeyboardShortcutsModalProps) {
  if (!isOpen) return null;

  const shortcuts = [
    {
      category: "Panels & Views",
      items: [
        {
          label: "Toggle File Explorer",
          keys: ["Ctrl", "B"],
          macKeys: ["⌘", "B"],
          icon: FolderTree,
          desc: "Show or hide the repository file tree",
        },
        {
          label: "Toggle Terminal & Tests",
          keys: ["Ctrl", "`"],
          altKeys: ["Ctrl", "J"],
          macKeys: ["⌘", "`"],
          icon: Terminal,
          desc: "Open or close the worktree sandbox terminal & test output",
        },
        {
          label: "Toggle AI Agent Chat",
          keys: ["Ctrl", "L"],
          altKeys: ["Ctrl", "I"],
          macKeys: ["⌘", "L"],
          icon: Sparkles,
          desc: "Open or close the autonomous verification agent panel",
        },
      ],
    },
    {
      category: "Navigation & Actions",
      items: [
        {
          label: "Search Symbols & Files",
          keys: ["Ctrl", "K"],
          macKeys: ["⌘", "K"],
          icon: Search,
          desc: "Focus search bar for fast symbol & AST lookup",
        },
        {
          label: "Run Verification Pipeline",
          keys: ["Ctrl", "Enter"],
          macKeys: ["⌘", "Enter"],
          icon: Play,
          desc: "Start contract synthesis & sandboxed verification",
        },
        {
          label: "Keyboard Shortcuts Guide",
          keys: ["?"],
          altKeys: ["Ctrl", "Shift", "P"],
          macKeys: ["⌘", "Shift", "P"],
          icon: Keyboard,
          desc: "Show this cheat sheet modal",
        },
        {
          label: "Close Overlays & Modals",
          keys: ["Esc"],
          macKeys: ["Esc"],
          icon: X,
          desc: "Dismiss active dropdowns and dialogs",
        },
      ],
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="bg-[#14181E] border border-[#2F343A] rounded-xl shadow-2xl w-full max-w-xl overflow-hidden text-[#E6EDF3] flex flex-col max-h-[85vh]">
        {/* Modal Header */}
        <div className="px-5 py-3.5 border-b border-[#2F343A] flex items-center justify-between bg-[#0A0D10]/80">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-purple-600/20 text-purple-400 border border-purple-500/30">
              <Keyboard className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white tracking-wide">Keyboard Shortcuts & Access Ribbon</h2>
              <p className="text-[11px] text-[#8B949E]">Quickly toggle panels and trigger verification actions</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded-lg transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 overflow-y-auto space-y-5 scrollbar-thin">
          {shortcuts.map((section, sIdx) => (
            <div key={sIdx} className="space-y-2.5">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-purple-400 font-mono">
                {section.category}
              </div>
              <div className="space-y-1.5">
                {section.items.map((item, iIdx) => {
                  const Icon = item.icon;
                  return (
                    <div
                      key={iIdx}
                      className="flex items-center justify-between p-2 rounded-lg bg-[#0A0D10]/50 border border-[#2F343A]/40 hover:border-purple-500/30 transition-colors"
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className="w-4 h-4 text-purple-400/80 flex-shrink-0" />
                        <div>
                          <div className="text-xs font-medium text-white">{item.label}</div>
                          <div className="text-[10px] text-[#8B949E]">{item.desc}</div>
                        </div>
                      </div>

                      {/* Shortcut Badges */}
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <div className="flex items-center gap-1">
                          {item.keys.map((k, kIdx) => (
                            <kbd
                              key={kIdx}
                              className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-[#1E222A] text-purple-300 border border-[#2F343A] rounded shadow-sm"
                            >
                              {k}
                            </kbd>
                          ))}
                        </div>
                        {item.altKeys && (
                          <>
                            <span className="text-[10px] text-[#8B949E]">or</span>
                            <div className="flex items-center gap-1">
                              {item.altKeys.map((k, kIdx) => (
                                <kbd
                                  key={kIdx}
                                  className="px-1.5 py-0.5 text-[10px] font-mono text-[#8B949E] bg-[#1E222A]/80 border border-[#2F343A] rounded"
                                >
                                  {k}
                                </kbd>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-2.5 border-t border-[#2F343A] bg-[#0A0D10]/60 flex items-center justify-between text-[11px] text-[#8B949E]">
          <span>Tip: You can also use the top ribbon icons anytime</span>
          <button
            onClick={onClose}
            className="px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded text-xs font-semibold transition-colors"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
