"use client";

import React, { useState } from "react";
import {
  Sparkles,
  Save,
  GitCommit,
  Rocket,
  MessageSquare,
  FileDiff,
  Layers,
  Paperclip,
  ClipboardCopy,
  Send,
  ChevronDown,
  CheckCircle2,
  FileCode,
  X,
  Bot,
  User,
} from "lucide-react";

interface AIAgentPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectFile: (filePath: string) => void;
}

export function AIAgentPanel({ isOpen, onClose, onSelectFile }: AIAgentPanelProps) {
  const [activeSubTab, setActiveSubTab] = useState<"chat" | "changes" | "context">("chat");
  const [selectedModel, setSelectedModel] = useState("GPT-4o");
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [promptInput, setPromptInput] = useState("");

  const models = ["GPT-4o", "Claude 3.5 Sonnet", "Gemini 1.5 Pro", "Local Ollama"];

  const [messages, setMessages] = useState<
    Array<{
      id: string;
      sender: "user" | "agent";
      text: string;
      codeBlock?: {
        fileName: string;
        code: string;
      };
      completionBadge?: string;
      followUpPrompt?: string;
      quickActions?: string[];
    }>
  >([
    {
      id: "1",
      sender: "user",
      text: "Add a new API route for managing user todos with GET and POST handlers.",
    },
    {
      id: "2",
      sender: "agent",
      text: "I'll create the new API endpoint in `src/pages/api/todos.ts` with TypeScript type safety and full REST method support.",
      codeBlock: {
        fileName: "src/pages/api/todos.ts",
        code: `import type { NextApiRequest, NextApiResponse } from 'next';

interface Todo {
  id: number;
  text: string;
  completed: boolean;
}

let todosList: Todo[] = [
  { id: 1, text: 'Initialize AI Workspace', completed: true },
  { id: 2, text: 'Configure Next.js 16 App Router', completed: true },
];

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method === 'GET') {
    return res.status(200).json(todosList);
  }
  if (req.method === 'POST') {
    const { text } = req.body;
    const newTodo: Todo = { id: Date.now(), text, completed: false };
    todosList.push(newTodo);
    return res.status(201).json(newTodo);
  }
  return res.status(405).end();
}`,
      },
      completionBadge: "Added new API route successfully",
      followUpPrompt: "Would you like me to add request validation using a Zod schema?",
      quickActions: ["Yes, add validation", "No, that's fine"],
    },
  ]);

  if (!isOpen) return null;

  const handleSendMessage = (textToSend?: string) => {
    const query = textToSend || promptInput;
    if (!query.trim()) return;

    const userMsgId = Date.now().toString();
    const userMsg = {
      id: userMsgId,
      sender: "user" as const,
      text: query,
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setPromptInput("");

    // Simulate Agent Response after 600ms
    setTimeout(() => {
      let agentResponseText = "I have analyzed your codebase and verified the requested changes.";
      let codeBlock;
      let badge = "Verified implementation";

      if (query.includes("validation")) {
        agentResponseText = "Updated `src/pages/api/todos.ts` with Zod schema validation for POST payloads.";
        codeBlock = {
          fileName: "src/pages/api/todos.ts",
          code: `import { z } from 'zod';\n\nconst createTodoSchema = z.object({\n  text: z.string().min(1, 'Task description required'),\n});`,
        };
        badge = "Added Zod validation schema";
      }

      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "agent",
          text: agentResponseText,
          codeBlock,
          completionBadge: badge,
        },
      ]);
    }, 600);
  };

  return (
    <div className="w-80 bg-[#14181E] border-l border-[#2F343A] flex flex-col h-full select-none flex-shrink-0 text-[#E6EDF3]">
      {/* Top Bar Header */}
      <div className="h-12 px-3 border-b border-[#2F343A] flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="relative flex items-center justify-center">
            <span className="w-2.5 h-2.5 bg-purple-500 rounded-full animate-ping absolute opacity-75" />
            <span className="w-2 h-2 bg-purple-500 rounded-full" />
          </div>
          <span className="font-bold text-xs tracking-wider text-white">AI AGENT</span>
        </div>

        {/* Action Buttons: Save, Commit, Deploy */}
        <div className="flex items-center gap-1">
          <button
            className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors"
            title="Save Changes"
          >
            <Save className="w-3.5 h-3.5" />
          </button>
          <button
            className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors"
            title="Commit Git"
          >
            <GitCommit className="w-3.5 h-3.5" />
          </button>

          {/* Active Highlighted Deploy Button */}
          <button className="flex items-center gap-1 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white px-2.5 py-1 rounded text-xs font-semibold shadow-md shadow-purple-600/30 transition-all">
            <Rocket className="w-3 h-3" />
            <span>Deploy</span>
          </button>

          <button
            onClick={onClose}
            className="p-1.5 text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors ml-1"
            title="Close Panel"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Sub-Tabs: Chat, Changes, Context */}
      <div className="h-9 bg-[#0A0D10] border-b border-[#2F343A] flex items-center px-2 text-xs flex-shrink-0">
        <button
          onClick={() => setActiveSubTab("chat")}
          className={`flex-1 py-1.5 flex items-center justify-center gap-1.5 font-medium transition-colors border-b-2 ${
            activeSubTab === "chat"
              ? "text-purple-400 border-purple-500 font-semibold"
              : "text-[#8B949E] border-transparent hover:text-[#E6EDF3]"
          }`}
        >
          <MessageSquare className="w-3.5 h-3.5" />
          <span>Chat</span>
        </button>

        <button
          onClick={() => setActiveSubTab("changes")}
          className={`flex-1 py-1.5 flex items-center justify-center gap-1.5 font-medium transition-colors border-b-2 ${
            activeSubTab === "changes"
              ? "text-purple-400 border-purple-500 font-semibold"
              : "text-[#8B949E] border-transparent hover:text-[#E6EDF3]"
          }`}
        >
          <FileDiff className="w-3.5 h-3.5" />
          <span>Changes</span>
          <span className="bg-purple-950 text-purple-300 text-[10px] px-1.5 rounded-full font-mono">
            +1
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab("context")}
          className={`flex-1 py-1.5 flex items-center justify-center gap-1.5 font-medium transition-colors border-b-2 ${
            activeSubTab === "context"
              ? "text-purple-400 border-purple-500 font-semibold"
              : "text-[#8B949E] border-transparent hover:text-[#E6EDF3]"
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Context</span>
          <span className="bg-[#2F343A] text-[#8B949E] text-[10px] px-1.5 rounded-full font-mono">
            3
          </span>
        </button>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4 text-xs bg-[#14181E]">
        {activeSubTab === "chat" && (
          <>
            {messages.map((msg) => (
              <div key={msg.id} className="space-y-2">
                {/* User Prompt */}
                {msg.sender === "user" ? (
                  <div className="flex items-start gap-2 justify-end">
                    <div className="bg-purple-600/25 border border-purple-500/40 text-[#E6EDF3] p-3 rounded-2xl rounded-tr-xs max-w-[85%] leading-relaxed shadow-sm">
                      {msg.text}
                    </div>
                    <div className="w-6 h-6 rounded-full bg-purple-600 text-white flex items-center justify-center text-[10px] font-bold flex-shrink-0">
                      U
                    </div>
                  </div>
                ) : (
                  /* Agent Response */
                  <div className="flex items-start gap-2">
                    <div className="w-6 h-6 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 text-white flex items-center justify-center flex-shrink-0 shadow-sm">
                      <Sparkles className="w-3.5 h-3.5" />
                    </div>

                    <div className="flex-1 space-y-2">
                      <div className="bg-[#0A0D10] border border-[#2F343A] p-3 rounded-2xl rounded-tl-xs text-[#E6EDF3] leading-relaxed shadow-sm">
                        {msg.text}
                      </div>

                      {/* Code Block Card */}
                      {msg.codeBlock && (
                        <div className="bg-[#0A0D10] border border-[#2F343A] rounded-lg overflow-hidden shadow-inner">
                          <div
                            onClick={() => onSelectFile(msg.codeBlock!.fileName)}
                            className="bg-[#1E222A] px-3 py-1.5 border-b border-[#2F343A] flex items-center justify-between cursor-pointer hover:bg-[#252A34] transition-colors"
                          >
                            <div className="flex items-center gap-1.5 font-mono text-[11px] text-purple-300">
                              <FileCode className="w-3.5 h-3.5 text-purple-400" />
                              <span>+ {msg.codeBlock.fileName}</span>
                            </div>
                            <span className="text-[10px] bg-emerald-950 text-emerald-300 px-1.5 py-0.5 rounded font-mono uppercase">
                              New File
                            </span>
                          </div>
                          <pre className="p-3 text-[11px] font-mono text-[#8B949E] overflow-x-auto leading-5 max-h-40 scrollbar-thin">
                            <code>{msg.codeBlock.code}</code>
                          </pre>
                        </div>
                      )}

                      {/* Completion Badge */}
                      {msg.completionBadge && (
                        <div className="flex items-center gap-1.5 text-[11px] text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 px-2.5 py-1 rounded-md font-medium">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          <span>{msg.completionBadge}</span>
                        </div>
                      )}

                      {/* Follow up & Action Buttons */}
                      {msg.followUpPrompt && (
                        <div className="pt-1 space-y-2">
                          <p className="text-[#8B949E] italic text-[11px]">{msg.followUpPrompt}</p>
                          {msg.quickActions && (
                            <div className="flex flex-wrap gap-1.5">
                              {msg.quickActions.map((action, idx) => (
                                <button
                                  key={idx}
                                  onClick={() => handleSendMessage(action)}
                                  className="bg-[#0A0D10] hover:bg-purple-600/20 text-purple-300 border border-purple-500/30 hover:border-purple-500 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all"
                                >
                                  {action}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        {activeSubTab === "changes" && (
          <div className="space-y-2">
            <div className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider">
              Staged Changes
            </div>
            <div
              onClick={() => onSelectFile("src/pages/api/todos.ts")}
              className="bg-[#0A0D10] border border-[#2F343A] p-2.5 rounded-lg flex items-center justify-between cursor-pointer hover:bg-[#1E222A] transition-colors"
            >
              <div className="flex items-center gap-2">
                <FileCode className="w-4 h-4 text-emerald-400" />
                <span className="font-mono text-xs text-[#E6EDF3]">src/pages/api/todos.ts</span>
              </div>
              <span className="text-[10px] text-emerald-400 font-mono font-bold">+28 lines</span>
            </div>
          </div>
        )}

        {activeSubTab === "context" && (
          <div className="space-y-2">
            <div className="text-xs font-semibold text-[#8B949E] uppercase tracking-wider">
              Active Context Files
            </div>
            {["src/pages/api/index.tsx", "src/pages/api/todos.ts", "package.json"].map(
              (file, idx) => (
                <div
                  key={idx}
                  onClick={() => onSelectFile(file)}
                  className="bg-[#0A0D10] border border-[#2F343A] p-2 rounded flex items-center justify-between cursor-pointer hover:bg-[#1E222A]"
                >
                  <span className="font-mono text-xs text-purple-300">{file}</span>
                  <span className="text-[10px] text-[#8B949E]">Indexed</span>
                </div>
              )
            )}
          </div>
        )}
      </div>

      {/* User Input Area at Bottom */}
      <div className="p-3 bg-[#0A0D10] border-t border-[#2F343A] space-y-2 flex-shrink-0">
        <textarea
          rows={2}
          value={promptInput}
          onChange={(e) => setPromptInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
            }
          }}
          placeholder="Ask anything about your codebase..."
          className="w-full bg-[#14181E] border border-[#2F343A] rounded-lg p-2.5 text-xs text-[#E6EDF3] placeholder-[#8B949E] focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 resize-none font-sans"
        />

        <div className="flex items-center justify-between">
          {/* Left Icons: Attach (@), Clipboard */}
          <div className="flex items-center gap-1.5 text-[#8B949E]">
            <button className="p-1.5 hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Attach Context File (@)">
              <Paperclip className="w-3.5 h-3.5" />
            </button>
            <button className="p-1.5 hover:text-[#E6EDF3] hover:bg-[#1E222A] rounded transition-colors" title="Copy Clipboard Prompt">
              <ClipboardCopy className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Right Side: Model Selector Dropdown & Send Button */}
          <div className="flex items-center gap-2">
            {/* Model Dropdown */}
            <div className="relative">
              <button
                onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}
                className="flex items-center gap-1 bg-[#14181E] hover:bg-[#1E222A] text-[11px] text-[#8B949E] hover:text-[#E6EDF3] px-2 py-1 rounded border border-[#2F343A] font-medium transition-colors"
              >
                <span>{selectedModel}</span>
                <ChevronDown className="w-3 h-3" />
              </button>

              {isModelDropdownOpen && (
                <div className="absolute right-0 bottom-full mb-1 w-36 bg-[#14181E] border border-[#2F343A] rounded shadow-xl py-1 z-50 text-xs">
                  {models.map((mod) => (
                    <button
                      key={mod}
                      onClick={() => {
                        setSelectedModel(mod);
                        setIsModelDropdownOpen(false);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-[#1E222A] text-[#E6EDF3]"
                    >
                      {mod}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Send Button */}
            <button
              onClick={() => handleSendMessage()}
              className="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white p-1.5 rounded-lg shadow-md shadow-purple-600/30 transition-all"
              title="Send Prompt"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
