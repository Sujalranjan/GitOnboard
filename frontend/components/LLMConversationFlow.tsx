'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Zap, MessageCircle, CheckCircle2, Eye, EyeOff, Send, Settings } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

// Component to display code with line numbers
function CodeDisplay({ content }: { content: string }) {
  const lines = content.split('\n');
  return (
    <div className="bg-slate-900/50 rounded overflow-x-auto text-slate-200 font-mono text-sm">
      <div className="flex">
        {/* Line numbers column */}
        <div className="bg-slate-950/50 px-3 py-2 text-right select-none text-slate-500 border-r border-slate-700 min-w-fit">
          {lines.map((_, idx) => (
            <div key={idx} className="h-5 leading-5">{idx + 1}</div>
          ))}
        </div>
        {/* Code column */}
        <div className="px-3 py-2 flex-1 overflow-x-auto">
          {lines.map((line, idx) => (
            <div key={idx} className="h-5 leading-5 whitespace-pre">
              {line || ' '}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

interface ToolArguments {
  [key: string]: string | number | boolean | null | undefined;
}

interface Message {
  type: 'user-query' | 'llm-thinking' | 'tool-call' | 'tool-response' | 'final-answer';
  content: string;
  icon?: React.ReactNode;
  // Structured tool event fields
  toolName?: string;
  arguments?: ToolArguments;
  success?: boolean;
  resultSummary?: string;
  resultCount?: number | null;
  error?: { type: string; message: string } | null;
  durationMs?: number;
  totalLines?: number;  // For read_file tool - total lines in the file
}

interface ModelOption {
  id: string;
  name: string;
  description: string;
  category: 'fast' | 'quality' | 'cloud';
}

const AVAILABLE_MODELS: ModelOption[] = [
  {
    id: 'qwen3:4b-instruct',
    name: 'Qwen 3 4B (Fast)',
    description: 'Quick responses, limited reasoning',
    category: 'fast',
  },
  {
    id: 'qwen2.5-coder:7b',
    name: 'Qwen 2.5 Coder 7B (Quality)',
    description: 'Better reasoning, slower',
    category: 'quality',
  },
  {
    id: 'cloud-gemini',
    name: 'Gemini (Cloud)',
    description: 'Best quality, requires API key',
    category: 'cloud',
  },
  {
    id: 'cloud-openrouter',
    name: 'OpenRouter (Cloud)',
    description: 'Multiple models (Claude, GPT-4), requires API key',
    category: 'cloud',
  },
];

interface LLMConversationFlowProps {
  repoName: string;
}

export const LLMConversationFlow: React.FC<LLMConversationFlowProps> = ({ repoName }) => {
  const [query, setQuery] = useState('');
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [toolCalls, setToolCalls] = useState(0);
  const [totalData, setTotalData] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [done, setDone] = useState(false);
  const [showToolDetails, setShowToolDetails] = useState(true);
  const [selectedModel, setSelectedModel] = useState<string>('qwen3:4b-instruct');
  const [changingModel, setChangingModel] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [totalTokens, setTotalTokens] = useState(0);
  const [modelUsed, setModelUsed] = useState('');
  const [repoHash, setRepoHash] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef<number>(0);
  const settingsRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Close settings menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(event.target as Node)) {
        setSettingsOpen(false);
      }
    };

    if (settingsOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [settingsOpen]);

  // Look up repo hash from repo name
  useEffect(() => {
    const lookupRepoHash = async () => {
      try {
        const response = await fetch(`/api/repos/lookup-hash?name=${encodeURIComponent(repoName)}`);
        if (response.ok) {
          const data = await response.json();
          if (data.repository_hash) {
            setRepoHash(data.repository_hash);
          }
        } else {
          console.error('Failed to look up repository hash:', response.statusText);
        }
      } catch (error) {
        console.error('Failed to look up repository hash:', error);
      }
    };

    if (repoName) {
      lookupRepoHash();
    }
  }, [repoName]);

  const handleModelChange = async (modelId: string) => {
    setChangingModel(true);
    try {
      const response = await fetch('/api/llm/set-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: modelId }),
      });
      if (response.ok) {
        setSelectedModel(modelId);
      } else {
        console.error('Failed to change model');
      }
    } catch (error) {
      console.error('Error changing model:', error);
    } finally {
      setChangingModel(false);
    }
  };

  const simulateQuery = async (userQuery: string) => {
    setRunning(true);
    setToolCalls(0);
    setTotalData(0);
    setElapsed(0);
    setDone(false);
    startTimeRef.current = Date.now();

    // Append to existing conversation (don't clear history)
    // Backend will send user-query via SSE, so don't duplicate it here
    setMessages(prev => [...prev, {
      type: 'llm-thinking' as const,
      content: 'Sending your query to the LLM...',
    }]);

    try {
      if (!repoHash) {
        setMessages(prev => [...prev, {
          type: 'final-answer' as const,
          content: '❌ No repository selected.\n\nPlease:\n1. Go to Dashboard\n2. Import a repository\n3. Then come back to ask questions\n\nOnce a repository is imported and indexed, you\'ll be able to analyze its codebase here.',
        }]);
        setRunning(false);
        setDone(true);
        return;
      }

      // Call real backend endpoint with streaming
      const response = await fetch('/api/llm/analyze/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userQuery,
          repo_hash: repoHash,
          model: selectedModel,
          show_tool_details: showToolDetails,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to analyze: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines[lines.length - 1];

        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i].trim();
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === 'completed') {
                // Stream finished - capture metrics
                setDone(true);
                setTotalTokens(data.total_tokens || 0);
                setModelUsed(data.model_used || selectedModel);
              } else if (data.type === 'error') {
                setMessages(prev => [...prev, {
                  type: 'final-answer' as const,
                  content: `Error: ${data.content}`,
                }]);
              } else if (data.type === 'tool-call') {
                // Structured tool-call event from backend
                setToolCalls(prev => prev + 1);
                setMessages(prev => [...prev, {
                  type: 'tool-call' as const,
                  content: `${data.tool_name}(${JSON.stringify(data.arguments)})`,
                  toolName: data.tool_name,
                  arguments: data.arguments,
                }]);
              } else if (data.type === 'tool-response') {
                // Structured tool-response event from backend
                // Extract total_lines from result_summary for read_file (e.g., "[read_file] path lines 1-100: 4522 chars\n")
                let totalLines: number | undefined;
                if (data.tool_name === 'read_file' && data.result_summary) {
                  const match = data.result_summary.match(/\[read_file\].*total:\s*(\d+)/);
                  if (match) {
                    totalLines = parseInt(match[1], 10);
                  }
                }

                setMessages(prev => [...prev, {
                  type: 'tool-response' as const,
                  content: data.result_summary || 'Tool execution completed',
                  toolName: data.tool_name,
                  success: data.success,
                  resultSummary: data.result_summary,
                  resultCount: data.result_count,
                  error: data.error,
                  durationMs: data.duration_ms,
                  totalLines: totalLines,
                }]);
              } else {
                setMessages(prev => [...prev, {
                  type: data.type as Message['type'],
                  content: data.content,
                }]);
              }

              setElapsed((Date.now() - startTimeRef.current) / 1000);
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          }
        }
      }

      setRunning(false);
    } catch (error) {
      console.error('Error analyzing query:', error);
      setMessages(prev => [...prev, {
        type: 'final-answer' as const,
        content: `Error: ${error instanceof Error ? error.message : 'Failed to analyze query'}`,
      }]);
      setRunning(false);
      setDone(true);
    }
  };


  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !running) {
      const userQuery = query;
      setQuery(''); // Clear input immediately for UX feedback
      simulateQuery(userQuery);
    }
  };

  const suggestedQueries = [
    'How does authentication work?',
    'What is the system architecture?',
    'How is data stored?',
    'What are the key components?',
  ];

  return (
    <div className="flex flex-col h-full bg-slate-950 text-white overflow-hidden">
      {/* Chat Area - Full Height */}
      <div className="flex-1 overflow-y-auto px-6 py-8">
        <div className="max-w-3xl mx-auto">
          {/* Empty State */}
          {messages.length === 0 && !running && (
            <div className="flex flex-col items-center justify-center h-full">
              <MessageCircle className="w-20 h-20 text-slate-600 mb-6" />
              <p className="text-xl text-slate-400 mb-8">Ask a question to get started</p>

              {/* Suggested Queries */}
              <div className="w-full">
                <p className="text-xs font-semibold text-slate-500 mb-4 uppercase">Try asking about:</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {suggestedQueries.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setQuery(q);
                        setTimeout(() => simulateQuery(q), 0);
                      }}
                      className="text-left px-4 py-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm transition-colors border border-slate-700"
                    >
                      → {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.length > 0 && (
            <div className="space-y-4">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`animate-slide-up ${
                    msg.type === 'user-query' ? 'flex justify-end' : 'flex justify-start'
                  }`}
                >
                  <div
                    className={`max-w-2xl px-4 py-3 rounded-lg ${
                      msg.type === 'user-query'
                        ? 'bg-blue-600 text-white rounded-br-none'
                        : msg.type === 'tool-call'
                          ? 'bg-amber-900/40 border border-amber-700/50 text-amber-100 rounded-bl-none'
                          : msg.type === 'tool-response'
                            ? 'bg-slate-700/50 border border-slate-600 text-slate-200 rounded-bl-none'
                            : msg.type === 'final-answer'
                              ? 'bg-green-900/30 border border-green-700 text-slate-100 rounded-bl-none'
                              : 'bg-slate-800 text-slate-300 rounded-bl-none'
                    }`}
                  >
                    {/* Tool Call Header */}
                    {msg.type === 'tool-call' && (
                      <div>
                        <div className="flex items-center gap-2 mb-3">
                          <Zap className="w-4 h-4 animate-pulse text-amber-400" />
                          <span className="text-xs font-semibold text-amber-300 uppercase">🔧 Tool Call</span>
                        </div>
                        {msg.toolName && (
                          <div className="space-y-2">
                            {/* Tool name chip */}
                            <div className="inline-block bg-amber-600/40 border border-amber-500/50 rounded-full px-3 py-1 text-xs font-mono font-semibold text-amber-200">
                              {msg.toolName}
                            </div>
                            {/* Arguments */}
                            {msg.arguments && Object.keys(msg.arguments).length > 0 && (
                              <div className="bg-slate-900/50 rounded px-3 py-2 text-xs space-y-1">
                                {Object.entries(msg.arguments).map(([key, val]) => (
                                  <div key={key} className="text-slate-300">
                                    <span className="text-slate-400">{key}:</span>{' '}
                                    <span className="text-slate-200 font-mono">
                                      {typeof val === 'string' ? `"${val}"` : JSON.stringify(val)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Tool Response Header */}
                    {msg.type === 'tool-response' && (
                      <div>
                        <div className="flex items-center gap-3 mb-3">
                          <div className="flex items-center gap-2">
                            {msg.success ? (
                              <>
                                <CheckCircle2 className="w-4 h-4 text-green-400" />
                                <span className="text-xs font-semibold text-green-300 uppercase">✓ Success</span>
                              </>
                            ) : (
                              <>
                                <span className="w-4 h-4 rounded-full bg-red-500 flex items-center justify-center text-white text-xs font-bold">!</span>
                                <span className="text-xs font-semibold text-red-300 uppercase">✗ Failed</span>
                              </>
                            )}
                          </div>
                          {msg.durationMs !== undefined && (
                            <span className="text-xs text-slate-400">({msg.durationMs.toFixed(0)}ms)</span>
                          )}
                        </div>

                        {/* Tool name and result count/total lines */}
                        {msg.toolName && (
                          <div className="mb-2 flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-mono text-slate-400">{msg.toolName}</span>
                            {msg.toolName === 'read_file' && msg.totalLines !== undefined && (
                              <span className="text-xs text-slate-500">(total_lines: {msg.totalLines})</span>
                            )}
                            {msg.resultCount !== undefined && msg.resultCount !== null && msg.toolName !== 'read_file' && (
                              <span className="text-xs text-slate-500">({msg.resultCount} results)</span>
                            )}
                          </div>
                        )}

                        {/* Error state */}
                        {msg.error && (
                          <div className="mb-2 bg-red-900/30 border border-red-700/50 rounded px-3 py-2 text-xs">
                            <div className="text-red-300 font-semibold mb-1">{msg.error.type}</div>
                            <div className="text-red-200">{msg.error.message}</div>
                          </div>
                        )}

                        {/* Result summary */}
                        {msg.resultSummary && (
                          <div className="max-h-96 overflow-y-auto">
                            {msg.toolName === 'read_file' ? (
                              <CodeDisplay content={msg.resultSummary} />
                            ) : (
                              <div className="bg-slate-900/50 rounded px-3 py-2 text-sm whitespace-pre-wrap font-mono text-slate-200">
                                {msg.resultSummary}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* LLM Thinking */}
                    {msg.type === 'llm-thinking' && (
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <div className="w-2 h-2 bg-slate-400 rounded-full animate-pulse" />
                          <span className="text-xs font-semibold text-slate-400">Thinking</span>
                        </div>
                        <p className="text-sm leading-relaxed italic text-slate-400">
                          {msg.content}
                        </p>
                      </div>
                    )}

                    {/* Final Answer */}
                    {msg.type === 'final-answer' && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <CheckCircle2 className="w-5 h-5 text-green-400" />
                          <span className="text-sm font-semibold text-green-400">Answer</span>
                        </div>
                        <div className="text-sm leading-relaxed prose prose-invert max-w-none">
                          <ReactMarkdown
                            components={{
                              h1: ({ children }) => <h1 className="text-xl font-bold mt-4 mb-2 text-white">{children}</h1>,
                              h2: ({ children }) => <h2 className="text-lg font-bold mt-3 mb-2 text-white">{children}</h2>,
                              h3: ({ children }) => <h3 className="text-base font-bold mt-2 mb-1 text-slate-200">{children}</h3>,
                              p: ({ children }) => <p className="mb-2 text-slate-300">{children}</p>,
                              ul: ({ children }) => <ul className="list-disc pl-6 mb-2 text-slate-300">{children}</ul>,
                              ol: ({ children }) => <ol className="list-decimal pl-6 mb-2 text-slate-300">{children}</ol>,
                              li: ({ children }) => <li className="mb-1 text-slate-300">{children}</li>,
                              code: ({ children }) => <code className="bg-slate-800 px-2 py-1 rounded text-slate-200 font-mono text-xs">{children}</code>,
                              pre: ({ children }) => <pre className="bg-slate-900 p-3 rounded mb-2 overflow-x-auto text-slate-200 text-xs">{children}</pre>,
                              blockquote: ({ children }) => <blockquote className="border-l-4 border-slate-600 pl-4 italic text-slate-400 my-2">{children}</blockquote>,
                              strong: ({ children }) => <strong className="font-bold text-slate-100">{children}</strong>,
                              em: ({ children }) => <em className="italic text-slate-300">{children}</em>,
                            }}
                          >
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                      </div>
                    )}

                    {/* User Query */}
                    {msg.type === 'user-query' && (
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">
                        {msg.content}
                      </p>
                    )}
                  </div>
                </div>
              ))}

              {running && messages.length > 0 && (
                <div className="flex justify-start">
                  <div className="bg-slate-800 px-4 py-3 rounded-lg rounded-bl-none">
                    <div className="flex gap-2 items-center">
                      <div className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                      <div className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                      <span className="text-xs text-slate-400 ml-2">Processing...</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Footer - Input Area (Sticky) */}
      <div className="flex-shrink-0 bg-slate-950 px-6 py-6 border-t border-slate-800">
        <div className="max-w-3xl mx-auto">
          {/* Metrics */}
          {(done || running) && (
            <>
              <div className="grid grid-cols-5 gap-2 mb-4">
                <div className="bg-amber-900/30 border border-amber-700/50 rounded-lg p-2 text-center">
                  <div className="text-lg font-bold text-amber-400">{toolCalls}</div>
                  <div className="text-xs text-amber-300">Tools</div>
                </div>
                <div className="bg-blue-900/30 border border-blue-700/50 rounded-lg p-2 text-center">
                  <div className="text-lg font-bold text-blue-400">{Math.floor(elapsed)}</div>
                  <div className="text-xs text-blue-300">Seconds</div>
                </div>
                <div className="bg-green-900/30 border border-green-700/50 rounded-lg p-2 text-center">
                  <div className="text-lg font-bold text-green-400">{messages.length}</div>
                  <div className="text-xs text-green-300">Messages</div>
                </div>
                <div className="bg-purple-900/30 border border-purple-700/50 rounded-lg p-2 text-center">
                  <div className="text-lg font-bold text-purple-400">{totalTokens.toLocaleString()}</div>
                  <div className="text-xs text-purple-300">Tokens</div>
                </div>
                <div className={`rounded-lg p-2 text-center border ${done ? 'bg-green-900/30 border-green-700/50' : 'bg-slate-700/30 border-slate-600/50'}`}>
                  <div className={`text-sm font-bold ${done ? 'text-green-400' : 'text-slate-400'}`}>
                    {done ? '✓ Done' : 'Running'}
                  </div>
                  <div className={`text-xs ${done ? 'text-green-300' : 'text-slate-400'}`}>Status</div>
                </div>
              </div>
              {modelUsed && (
                <div className="text-center text-xs text-slate-400 mb-3">
                  Model: <span className="text-slate-300 font-semibold">{modelUsed}</span> •
                  Rate: <span className="text-slate-300 font-semibold">{totalTokens > 0 && elapsed > 0 ? Math.round((totalTokens / elapsed) * 10) / 10 : 0} tokens/sec</span>
                </div>
              )}
            </>
          )}

          {/* Input Area */}
          <form onSubmit={handleSubmit} className="relative flex gap-2 items-center">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask about your codebase..."
              disabled={running}
              className="flex-1 px-4 py-3 rounded-full bg-slate-800 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors disabled:opacity-50"
            />

            {/* Settings Button */}
            <div className="relative" ref={settingsRef}>
              <button
                type="button"
                onClick={() => setSettingsOpen(!settingsOpen)}
                className="p-2 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-300 transition-colors"
              >
                <Settings className="w-5 h-5" />
              </button>

              {/* Settings Dropdown */}
              {settingsOpen && (
                <div className="absolute bottom-full right-0 mb-2 bg-slate-800 border border-slate-700 rounded-lg shadow-lg z-50 min-w-56">
                  {/* Tool Details Toggle */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowToolDetails(!showToolDetails);
                      setSettingsOpen(false);
                    }}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-700 transition-colors border-b border-slate-700 first:rounded-t-lg"
                  >
                    {showToolDetails ? (
                      <>
                        <Eye className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-300">Hide Tool Details</span>
                      </>
                    ) : (
                      <>
                        <EyeOff className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-300">Show Tool Details</span>
                      </>
                    )}
                  </button>

                  {/* Model Selector */}
                  <div className="px-4 py-3 last:rounded-b-lg">
                    <label className="text-xs font-semibold text-slate-400 mb-2 block uppercase">
                      Select Model
                    </label>
                    <select
                      value={selectedModel}
                      onChange={(e) => {
                        handleModelChange(e.target.value);
                        setSettingsOpen(false);
                      }}
                      disabled={changingModel || running}
                      className="w-full px-3 py-2 rounded-lg bg-slate-700 border border-slate-600 text-white text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed appearance-none cursor-pointer"
                    >
                      {AVAILABLE_MODELS.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-slate-400 mt-2">
                      {AVAILABLE_MODELS.find((m) => m.id === selectedModel)?.description}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Send Button */}
            <button
              type="submit"
              disabled={running || !query.trim()}
              className="p-2 rounded-full bg-blue-600 hover:bg-blue-700 text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
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

      <style jsx>{`
        @keyframes slide-up {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-slide-up {
          animation: slide-up 0.3s ease-out;
        }
      `}</style>
    </div>
  );
};

export default LLMConversationFlow;
