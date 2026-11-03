'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Plus,
  Share2,
  ChevronDown,
  CheckCircle2,
  Clock,
  Sparkles,
  Paperclip,
  AtSign,
  Globe,
  Radio,
  FileCode2,
  ExternalLink,
  Bot,
  Eye,
  EyeOff,
  MessageCircle,
  Settings
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MermaidViewer } from '@/components/common/MermaidViewer';
import { ChatMessage, TaskItem, FindingItem } from '@/types/investigation';

interface ChatPanelProps {
  messages: ChatMessage[];
  running: boolean;
  onSendMessage: (query: string) => void;
  onNewInvestigation: () => void;
  selectedModel: string;
  onSelectModel: (m: string) => void;
  workerModel?: string;
  onSelectWorkerModel?: (m: string) => void;
  workerType?: 'local' | 'cloud';
  onSelectWorkerType?: (type: 'local' | 'cloud') => void;
  availableModels: Record<string, string>;
  tasks: TaskItem[];
  hasTriggeredBrain?: boolean;
  isBrainVisible?: boolean;
  onToggleBrain?: () => void;
  isFullScreenChat?: boolean;
}

interface ChatInputProps {
  running: boolean;
  onSendMessage: (query: string) => void;
  selectedModel: string;
  onSelectModel: (m: string) => void;
  workerModel: string;
  onSelectWorkerModel: (m: string) => void;
  workerType: 'local' | 'cloud';
  onSelectWorkerType: (type: 'local' | 'cloud') => void;
  modelOptions: Record<string, string>;
}

const ChatInput: React.FC<ChatInputProps> = React.memo(({
  running,
  onSendMessage,
  selectedModel,
  onSelectModel,
  workerModel,
  onSelectWorkerModel,
  workerType,
  onSelectWorkerType,
  modelOptions,
}) => {
  const [input, setInput] = useState('');
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || running) return;
    onSendMessage(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex-shrink-0 px-6 py-4 border-t border-slate-200/50 dark:border-slate-800/50 bg-white/40 dark:bg-slate-900/40 backdrop-blur-md">
      <div className="max-w-3xl mx-auto">
        <form onSubmit={handleSubmit} className="relative flex gap-2 items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your codebase..."
            disabled={running}
            className="flex-1 px-4 py-2.5 rounded-full glass-input text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-transparent transition-all disabled:opacity-50 text-sm"
          />

          {/* Model & Worker Pill / Settings Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
              className="p-2 rounded-full glass-panel-subtle hover:bg-slate-200/60 dark:hover:bg-slate-800/60 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors border border-slate-200/70 dark:border-slate-700/60"
              title="Execution & Model Settings"
            >
              <Settings className="w-5 h-5" />
            </button>

            {modelDropdownOpen && (
              <div className="absolute bottom-full right-0 mb-2 glass-panel border border-slate-200/80 dark:border-slate-800/80 rounded-xl shadow-2xl z-50 w-72 max-h-96 overflow-y-auto text-slate-800 dark:text-slate-200 py-2">
                {/* Planner Model Header */}
                <div className="px-3 py-1 text-xs font-semibold text-slate-400 dark:text-slate-400 uppercase tracking-wider flex items-center justify-between">
                  <span>Planner Model</span>
                  <span className="text-[10px] text-indigo-500 dark:text-indigo-400 font-mono">Brain</span>
                </div>
                <div className="px-1 mb-2">
                  {Object.entries(modelOptions).map(([key, name]) => (
                    <button
                      key={`planner-${key}`}
                      type="button"
                      onClick={() => onSelectModel(key)}
                      className={`w-full px-2.5 py-1.5 rounded-lg text-left text-xs hover:bg-slate-100/60 dark:hover:bg-slate-800/60 flex items-center justify-between transition-colors ${
                        selectedModel === key ? 'text-indigo-600 dark:text-indigo-400 font-semibold bg-indigo-50/50 dark:bg-indigo-950/40' : 'text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <span className="truncate">{name}</span>
                      {selectedModel === key && <CheckCircle2 className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 flex-shrink-0" />}
                    </button>
                  ))}
                </div>

                <div className="border-t border-slate-200/50 dark:border-slate-800/50 my-2" />

                {/* Worker Model Header */}
                <div className="px-3 py-1 text-xs font-semibold text-slate-400 dark:text-slate-400 uppercase tracking-wider flex items-center justify-between">
                  <span>Worker Model</span>
                  <span className="text-[10px] text-emerald-500 dark:text-emerald-400 font-mono">Execution</span>
                </div>
                <div className="px-1 mb-1">
                  {Object.entries(modelOptions).map(([key, name]) => (
                    <button
                      key={`worker-${key}`}
                      type="button"
                      onClick={() => onSelectWorkerModel(key)}
                      className={`w-full px-2.5 py-1.5 rounded-lg text-left text-xs hover:bg-slate-100/60 dark:hover:bg-slate-800/60 flex items-center justify-between transition-colors ${
                        workerModel === key ? 'text-emerald-600 dark:text-emerald-400 font-semibold bg-emerald-50/50 dark:bg-emerald-950/40' : 'text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <span className="truncate">{name}</span>
                      {workerModel === key && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Send Button */}
          <button
            type="submit"
            disabled={running || !input.trim()}
            className="p-2.5 rounded-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0 shadow-md shadow-violet-500/25"
          >
            {running ? (
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </form>
      </div>
    </div>
  );
});
ChatInput.displayName = 'ChatInput';

interface ChatMessageItemProps {
  msg: ChatMessage;
  hasTriggeredBrain?: boolean;
  isBrainVisible?: boolean;
  onToggleBrain?: () => void;
  tasks?: TaskItem[];
  planExpanded?: boolean;
  onTogglePlanExpanded?: () => void;
}

const markdownComponents = {
  pre: ({ children }: any) => {
    const childProps = (children as any)?.props;
    const className = childProps?.className || '';
    const rawCode = String(childProps?.children || '').trim();
    const isMermaid =
      className.includes('language-mermaid') ||
      /^graph\s+/i.test(rawCode) ||
      /^flowchart\s+/i.test(rawCode) ||
      /^sequenceDiagram/i.test(rawCode) ||
      /^classDiagram/i.test(rawCode) ||
      /^erDiagram/i.test(rawCode) ||
      /^stateDiagram/i.test(rawCode);

    if (isMermaid) {
      return <>{children}</>;
    }
    return (
      <pre className="overflow-x-auto max-w-full p-3.5 rounded-xl bg-slate-900/90 dark:bg-slate-950/80 text-slate-100 dark:text-slate-200 font-mono text-xs my-2.5 border border-slate-700/50 dark:border-slate-800/80 shadow-md">
        {children}
      </pre>
    );
  },
  code: ({ className, children, ...props }: any) => {
    const match = /language-(\w+)/.exec(className || '');
    const codeString = String(children).replace(/\n$/, '').trim();
    const isMermaid =
      (match && match[1]?.toLowerCase() === 'mermaid') ||
      /^graph\s+/i.test(codeString) ||
      /^flowchart\s+/i.test(codeString) ||
      /^sequenceDiagram/i.test(codeString) ||
      /^classDiagram/i.test(codeString) ||
      /^erDiagram/i.test(codeString) ||
      /^stateDiagram/i.test(codeString);

    if (isMermaid) {
      return <MermaidViewer chart={codeString} />;
    }

    const isMultiline = String(children).includes('\n');
    if (!isMultiline) {
      return (
        <code
          className="break-all font-mono text-xs px-1.5 py-0.5 rounded-md bg-indigo-50/80 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-800/50 font-medium"
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code className="block whitespace-pre font-mono text-xs" {...props}>
        {children}
      </code>
    );
  },
  table: ({ children }: any) => (
    <div className="overflow-x-auto my-3 border border-slate-700/70 dark:border-slate-800 rounded-xl bg-slate-950/70 shadow-lg backdrop-blur-sm">
      <table className="w-full text-xs font-sans border-collapse">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }: any) => (
    <thead className="bg-slate-900/90 text-slate-300 border-b border-slate-700/80 text-[11px] uppercase tracking-wider font-semibold">
      {children}
    </thead>
  ),
  th: ({ children }: any) => (
    <th className="py-2.5 px-3.5 text-left font-semibold text-slate-200">
      {children}
    </th>
  ),
  tbody: ({ children }: any) => (
    <tbody className="divide-y divide-slate-800/60 font-normal">
      {children}
    </tbody>
  ),
  tr: ({ children }: any) => (
    <tr className="hover:bg-slate-800/40 transition-colors">
      {children}
    </tr>
  ),
  td: ({ children }: any) => (
    <td className="py-2.5 px-3.5 text-slate-300 align-top leading-relaxed text-xs">
      {children}
    </td>
  ),
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-4 border-amber-500/80 bg-amber-50/50 dark:bg-amber-950/20 px-3 py-1.5 my-2 rounded-r text-xs text-slate-700 dark:text-slate-300 break-words overflow-hidden">
      {children}
    </blockquote>
  ),
};

const ChatMessageItem: React.FC<ChatMessageItemProps> = React.memo(({
  msg,
  hasTriggeredBrain,
  isBrainVisible,
  onToggleBrain,
  tasks = [],
  planExpanded,
  onTogglePlanExpanded,
}) => {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-2xl min-w-0 px-4 py-3 rounded-xl shadow-sm bg-blue-600 dark:bg-[#1E40AF] text-white rounded-br-none text-sm leading-relaxed whitespace-pre-wrap break-words border border-blue-500/30 dark:border-[#3B82F6]/30">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-4xl min-w-0 px-5 py-4 rounded-xl shadow-sm glass-panel text-slate-900 dark:text-slate-100 rounded-bl-none text-sm leading-relaxed space-y-3 break-words overflow-hidden border border-slate-200/60 dark:border-slate-800/60">
        <div className="prose dark:prose-invert max-w-none min-w-0 text-sm leading-relaxed text-slate-800 dark:text-slate-200 break-words">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={markdownComponents}
          >
            {msg.content}
          </ReactMarkdown>
        </div>

        {/* Action controls (Copy response) */}
        {msg.role === 'assistant' && msg.content && (
          <div className="pt-2 border-t border-slate-200/60 dark:border-slate-800/60 flex items-center justify-between text-xs text-slate-500">
            <div className="flex items-center gap-1 text-[11px] font-mono text-slate-400">
              {msg.timestamp && <span>{msg.timestamp}</span>}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(msg.content);
                }}
                className="px-2 py-1 rounded hover:bg-slate-100/60 dark:hover:bg-slate-800/60 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors flex items-center gap-1 text-xs"
                title="Copy response"
              >
                <Share2 className="w-3.5 h-3.5" />
                <span>Copy</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
});
ChatMessageItem.displayName = 'ChatMessageItem';

const InvestigationChatPanelComponent: React.FC<ChatPanelProps> = ({
  messages,
  running,
  onSendMessage,
  onNewInvestigation,
  selectedModel,
  onSelectModel,
  workerModel = 'qwen2.5-coder:3b',
  onSelectWorkerModel = () => {},
  workerType = 'local',
  onSelectWorkerType = () => {},
  availableModels,
  tasks,
  hasTriggeredBrain = false,
  isBrainVisible = true,
  onToggleBrain,
  isFullScreenChat = false,
}) => {
  const [planExpanded, setPlanExpanded] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleTogglePlan = React.useCallback(() => {
    setPlanExpanded((prev) => !prev);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, tasks]);

  const modelOptions = Object.keys(availableModels).length > 0
    ? availableModels
    : {
        'qwen3:4b-instruct': 'qwen3:4b-instruct',
        'qwen2.5-coder:7b': 'qwen2.5-coder:7b',
        'gemini-3.8-flash': 'gemini-3.8-flash',
      };

  const suggestedQueries = [
    'How does authentication work?',
    'What is the system architecture?',
    'How is data stored?',
    'What are the key components?',
  ];

  return (
    <div
      className={`flex flex-col h-full text-slate-900 dark:text-slate-100 transition-all duration-300 min-w-0 ${
        isFullScreenChat
          ? 'flex-1 w-full'
          : 'w-[420px] flex-shrink-0 border-r border-slate-200/70 dark:border-slate-800/70'
      }`}
    >
      {/* Top action header: New Conversation + Toggle Brain button */}
      <div className="px-6 py-3 border-b border-slate-200/70 dark:border-slate-800/70 flex items-center justify-between gap-2 flex-shrink-0 glass-nav">
        <button
          onClick={onNewInvestigation}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg glass-panel-subtle hover:bg-slate-200/60 dark:hover:bg-slate-800/60 border border-slate-200/70 dark:border-slate-700/60 text-xs font-medium text-slate-700 dark:text-slate-200 transition-colors shadow-sm"
        >
          <Plus className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
          <span>New Conversation</span>
        </button>

        <div className="flex items-center gap-2">
          {/* Toggle Brain button (always available once started or manually clicked) */}
          {onToggleBrain && (
            <button
              onClick={onToggleBrain}
              title={isBrainVisible ? 'Hide Brain' : 'Show Brain'}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all shadow-sm ${
                isBrainVisible
                  ? 'bg-indigo-50/80 dark:bg-indigo-950/40 border-indigo-300 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-950/60'
                  : 'glass-panel-subtle border-slate-200/70 dark:border-slate-700/60 text-slate-700 dark:text-slate-300 hover:bg-slate-200/60 dark:hover:bg-slate-800/60'
              }`}
            >
              <Bot className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
              <span>{isBrainVisible ? 'Hide Brain' : 'Show Brain'}</span>
              {isBrainVisible ? (
                <EyeOff className="w-3 h-3 text-slate-400 ml-0.5" />
              ) : (
                <Eye className="w-3 h-3 text-indigo-600 dark:text-indigo-400 ml-0.5" />
              )}
            </button>
          )}

          <button
            title="Share / Export"
            className="p-1.5 rounded-lg glass-panel-subtle border border-slate-200/70 dark:border-slate-700/60 hover:bg-slate-200/60 dark:hover:bg-slate-800/60 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors shadow-sm"
          >
            <Share2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Messages stream container (fills full available width, centers message column) */}
      <div className="flex-1 overflow-y-auto px-6 py-8">
        <div className="max-w-4xl mx-auto space-y-6 text-sm">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="w-16 h-16 rounded-2xl bg-indigo-50/80 dark:bg-indigo-950/40 border border-indigo-200/60 dark:border-indigo-800/60 flex items-center justify-center mb-6 text-indigo-600 dark:text-indigo-400 shadow-sm">
                <Bot className="w-9 h-9" />
              </div>
              <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-2">
                Ask about your codebase
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md mb-8">
                Get answers, trace features, explore architecture, and more with verified multi-agent analysis.
              </p>

              {/* Suggested Queries */}
              <div className="w-full max-w-2xl">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {suggestedQueries.slice(0, 3).map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        onSendMessage(q);
                      }}
                      className="px-4 py-2.5 rounded-full glass-panel-subtle hover:border-indigo-500/50 dark:hover:border-indigo-400/50 text-slate-700 dark:text-slate-200 text-xs font-medium transition-all shadow-sm hover:shadow-md truncate"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <ChatMessageItem
                key={msg.id}
                msg={msg}
                hasTriggeredBrain={hasTriggeredBrain}
                isBrainVisible={isBrainVisible}
                onToggleBrain={onToggleBrain}
                tasks={tasks}
                planExpanded={planExpanded}
                onTogglePlanExpanded={handleTogglePlan}
              />
            ))
          )}

          {running && messages.length > 0 && (
            <div className="flex justify-start">
              <div className="glass-panel border border-slate-200/60 dark:border-slate-800/60 shadow-sm px-4 py-3 rounded-xl rounded-bl-none max-w-sm">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-5 h-5 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
                    <Bot className="w-3.5 h-3.5" />
                  </div>
                  <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Investigation in progress...
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 dark:text-slate-400 mb-2">
                  Analyzing repository, collecting evidence, and synthesizing results.
                </p>
                <div className="flex gap-1.5 items-center">
                  <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce" />
                  <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Footer - Input Area (Clean integrated composer, isolated from chat panel state) */}
      <ChatInput
        running={running}
        onSendMessage={onSendMessage}
        selectedModel={selectedModel}
        onSelectModel={onSelectModel}
        workerModel={workerModel}
        onSelectWorkerModel={onSelectWorkerModel}
        workerType={workerType}
        onSelectWorkerType={onSelectWorkerType}
        modelOptions={modelOptions}
      />
    </div>
  );
};

export const InvestigationChatPanel = React.memo(InvestigationChatPanelComponent);
InvestigationChatPanel.displayName = 'InvestigationChatPanel';


