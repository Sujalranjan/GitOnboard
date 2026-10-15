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
  availableModels: Record<string, string>;
  tasks: TaskItem[];
  hasTriggeredBrain?: boolean;
  isBrainVisible?: boolean;
  onToggleBrain?: () => void;
  isFullScreenChat?: boolean;
}

export const InvestigationChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  running,
  onSendMessage,
  onNewInvestigation,
  selectedModel,
  onSelectModel,
  availableModels,
  tasks,
  hasTriggeredBrain = false,
  isBrainVisible = true,
  onToggleBrain,
  isFullScreenChat = false,
}) => {
  const [input, setInput] = useState('');
  const [planExpanded, setPlanExpanded] = useState(true);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, tasks]);

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
          {/* Unhide / Hide Agent Brain button if triggered */}
          {hasTriggeredBrain && onToggleBrain && (
            <button
              onClick={onToggleBrain}
              title={isBrainVisible ? 'Hide Agent Brain & Visualizer' : 'Show Agent Brain & Visualizer'}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                isBrainVisible
                  ? 'bg-indigo-50/70 dark:bg-indigo-950/40 border-indigo-300 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-950/60'
                  : 'glass-panel-subtle border-slate-200/70 dark:border-slate-700/60 text-slate-600 dark:text-slate-300 hover:bg-slate-200/60 dark:hover:bg-slate-800/60'
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
        <div className="max-w-3xl mx-auto space-y-6 text-sm">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <MessageCircle className="w-16 h-16 text-slate-300 dark:text-slate-600 mb-6" />
              <p className="text-xl font-medium text-slate-700 dark:text-slate-300 mb-8">
                Ask a question to get started
              </p>

              {/* Suggested Queries */}
              <div className="w-full">
                <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-4 uppercase tracking-wider text-left">
                  Try asking about:
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {suggestedQueries.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        onSendMessage(q);
                      }}
                      className="text-left px-4 py-3 rounded-xl glass-panel-subtle hover:border-violet-500/50 dark:hover:border-violet-400/50 text-slate-700 dark:text-slate-200 text-sm transition-all shadow-sm hover:shadow-md"
                    >
                      → {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div key={msg.id} className="space-y-2">
                {/* User message */}
                {msg.role === 'user' ? (
                  <div className="flex justify-end">
                    <div className="max-w-2xl min-w-0 px-4 py-3 rounded-xl shadow-sm bg-blue-600 dark:bg-[#1E40AF] text-white rounded-br-none text-sm leading-relaxed whitespace-pre-wrap break-words border border-blue-500/30 dark:border-[#3B82F6]/30">
                      {msg.content}
                    </div>
                  </div>
                ) : (
                  /* Assistant message */
                  <div className="flex justify-start">
                    <div className="w-full max-w-2xl min-w-0 px-4 py-3 rounded-xl shadow-sm glass-panel text-slate-900 dark:text-slate-100 rounded-bl-none text-sm leading-relaxed space-y-3 break-words overflow-hidden border border-slate-200/60 dark:border-slate-800/60">
                      <div className="prose dark:prose-invert max-w-none min-w-0 text-sm leading-relaxed text-slate-800 dark:text-slate-200 break-words">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            pre: ({ children }: any) => {
                              // If children contains a Mermaid block, avoid wrapping in styled <pre> box
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
                            table: ({ children }) => (
                              <div className="overflow-x-auto max-w-full my-2.5 border border-slate-200/80 dark:border-slate-700/80 rounded-xl overflow-hidden glass-panel-subtle shadow-sm">
                                <table className="w-full text-xs font-mono border-collapse">
                                  {children}
                                </table>
                              </div>
                            ),
                            blockquote: ({ children }) => (
                              <blockquote className="border-l-4 border-amber-500/80 bg-amber-50/50 dark:bg-amber-950/20 px-3 py-1.5 my-2 rounded-r text-xs text-slate-700 dark:text-slate-300 break-words overflow-hidden">
                                {children}
                              </blockquote>
                            ),
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </div>

                      {/* Notice if agents were spawned for this query */}
                      {hasTriggeredBrain && !isBrainVisible && onToggleBrain && (
                        <div className="pt-2 border-t border-slate-200/80 dark:border-slate-800/80 flex items-center justify-between text-xs">
                          <div className="flex items-center gap-1.5 text-indigo-600 dark:text-indigo-400 font-medium">
                            <Bot className="w-3.5 h-3.5" />
                            <span>Multi-agent brain investigated this query</span>
                          </div>
                          <button
                            onClick={onToggleBrain}
                            className="text-indigo-600 dark:text-indigo-400 hover:underline font-mono"
                          >
                            Show Agent Brain &rarr;
                          </button>
                        </div>
                      )}

                      {/* Collapsible Multi-agent investigation plan card if present */}
                      {tasks.length > 0 && isBrainVisible && (
                        <div className="rounded-xl glass-panel-subtle border border-slate-200/80 dark:border-slate-800/80 overflow-hidden shadow-sm">
                          <button
                            onClick={() => setPlanExpanded(!planExpanded)}
                            className="w-full px-3 py-2 flex items-center justify-between text-left text-xs font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-100/60 dark:hover:bg-slate-800/50 transition-colors"
                          >
                            <div className="flex items-center gap-2">
                              <Sparkles className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
                              <span>Multi-agent investigation plan</span>
                            </div>
                            <ChevronDown
                              className={`w-3.5 h-3.5 text-slate-400 transition-transform ${
                                planExpanded ? 'transform rotate-180' : ''
                              }`}
                            />
                          </button>

                          {planExpanded && (
                            <div className="px-3 pb-3 pt-1 space-y-2 text-xs border-t border-slate-200/60 dark:border-slate-800/60">
                              {tasks.map((t, idx) => {
                                const isDone = t.status === 'COMPLETED';
                                const isRun = t.status === 'RUNNING';
                                return (
                                  <div key={t.id || idx} className="flex items-start gap-2 text-slate-700 dark:text-slate-300">
                                    <div className="mt-0.5">
                                      {isDone ? (
                                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                      ) : isRun ? (
                                        <div className="w-3.5 h-3.5 rounded-full border-2 border-indigo-600 dark:border-indigo-400 border-t-transparent animate-spin" />
                                      ) : (
                                        <div className="w-3.5 h-3.5 rounded-full border border-slate-400 dark:border-slate-600" />
                                      )}
                                    </div>
                                    <div className="flex-1 truncate">
                                      <span className={isDone ? 'line-through text-slate-400 dark:text-slate-500' : ''}>
                                        {idx + 1}. {t.title}
                                      </span>
                                      {t.assigned_agent && (
                                        <span className="ml-2 text-[10px] text-indigo-600 dark:text-indigo-400 font-mono px-1.5 py-0.5 rounded bg-indigo-50/70 dark:bg-indigo-950/50 border border-indigo-200/50 dark:border-indigo-800/50">
                                          @{t.assigned_agent}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}

          {running && messages.length > 0 && (
            <div className="flex justify-start">
              <div className="glass-panel border border-slate-200/60 dark:border-slate-800/60 shadow-sm px-4 py-3 rounded-lg rounded-bl-none">
                <div className="flex gap-2 items-center">
                  <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                  <span className="text-xs text-slate-500 dark:text-slate-400 ml-2">Investigating codebase...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Footer - Input Area (Clean integrated composer) */}
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

            {/* Model Pill / Settings Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
                className="p-2 rounded-full glass-panel-subtle hover:bg-slate-200/60 dark:hover:bg-slate-800/60 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors border border-slate-200/70 dark:border-slate-700/60"
                title="Model Settings"
              >
                <Settings className="w-5 h-5" />
              </button>

              {modelDropdownOpen && (
                <div className="absolute bottom-full right-0 mb-2 glass-panel border border-slate-200/80 dark:border-slate-800/80 rounded-xl shadow-2xl z-50 min-w-56 text-slate-800 dark:text-slate-200 py-2">
                  <div className="px-3 py-1.5 text-xs font-semibold text-slate-400 dark:text-slate-400 uppercase tracking-wider">
                    Select Model
                  </div>
                  {Object.entries(modelOptions).map(([key, name]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => {
                        onSelectModel(key);
                        setModelDropdownOpen(false);
                      }}
                      className={`w-full px-3 py-2 text-left text-xs hover:bg-slate-100/60 dark:hover:bg-slate-800/60 flex items-center justify-between ${
                        selectedModel === key ? 'text-indigo-600 dark:text-indigo-400 font-semibold' : 'text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <span className="truncate">{name}</span>
                      {selectedModel === key && <CheckCircle2 className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />}
                    </button>
                  ))}
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
     </div>
   );
 };
