'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Zap, MessageCircle, CheckCircle2, Eye, EyeOff, Send, Settings, Wrench, Clock, MessageSquare, Activity, Cpu } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Component to display tree structure
function TreeDisplay({ content }: { content: string }) {
  // Extract tree content from [get_tree] format or use directly
  let treeContent = content;
  const treeMatch = content.match(/\[get_tree\].*?"tree":\s*"((?:\\.|[^"\\])*)"/) ||
                    content.match(/tree":\s*"((?:\\.|[^"\\])*)"/) ||
                    content.match(/"tree":\s*"([^"]*)"/) ||
                    content.match(/\n([\s\S]*)/);  // Fallback: everything after first newline

  if (treeMatch && treeMatch[1]) {
    // Unescape the string if it contains escape sequences
    treeContent = treeMatch[1]
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, '\t')
      .replace(/\\\//g, '/')
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, '\\');
  }

  return (
    <div className="bg-slate-100 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded px-3 py-2 text-sm whitespace-pre font-mono text-slate-800 dark:text-slate-200 overflow-x-auto">
      {treeContent}
    </div>
  );
}

// Component to display code with line numbers
function CodeDisplay({ content }: { content: string }) {
  // Parse line range from header: "lines X-Y:"
  let startLine = 1;
  const lineRangeMatch = content.match(/lines\s+(\d+)-(\d+)/);
  if (lineRangeMatch) {
    startLine = parseInt(lineRangeMatch[1], 10);
  }

  const lines = content.split('\n');
  // Find where code starts (skip header)
  let codeStartIdx = 0;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes('lines') && lines[i].includes(':')) {
      codeStartIdx = i + 1;
      break;
    }
  }
  const codeLines = lines.slice(codeStartIdx);

  return (
    <div className="bg-slate-100 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded overflow-x-auto text-slate-800 dark:text-slate-200 font-mono text-sm">
      <div className="flex">
        {/* Line numbers column */}
        <div className="bg-slate-200/60 dark:bg-slate-950/50 px-3 py-2 text-right select-none text-slate-500 border-r border-slate-200 dark:border-slate-700 min-w-fit">
          {codeLines.map((_, idx) => (
            <div key={idx} className="h-5 leading-5">{startLine + idx}</div>
          ))}
        </div>
        {/* Code column */}
        <div className="px-3 py-2 flex-1 overflow-x-auto">
          {codeLines.map((line, idx) => (
            <div key={idx} className="h-5 leading-5 whitespace-pre">
              {line || ' '}
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

// Static fallback models (in case API is not available)
const FALLBACK_MODELS: ModelOption[] = [
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
  {
    id: 'openai/gpt-oss-120b',
    name: 'Groq (GPT-OSS 120B)',
    description: 'Ultra-fast 131K context inference via Groq, requires API key',
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
  const [availableModels, setAvailableModels] = useState<ModelOption[]>(FALLBACK_MODELS);
  const [deploymentType, setDeploymentType] = useState<string>('LOCAL');
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

  // Fetch available models from backend API
  useEffect(() => {
    const fetchAvailableModels = async () => {
      try {
        const response = await fetch('/api/llm/models');
        if (response.ok) {
          const data = await response.json();
          setDeploymentType(data.deployment_type);

          // Convert backend model dict to ModelOption array
          const models: ModelOption[] = Object.entries(data.models).map(([modelId, displayName]) => {
            // Determine category based on model ID
            let category: 'fast' | 'quality' | 'cloud' = 'cloud';
            if (modelId.includes('qwen3:4b')) {
              category = 'fast';
            } else if (modelId.includes('qwen2.5-coder')) {
              category = 'quality';
            } else if (modelId.includes('cloud')) {
              category = 'cloud';
            }

            return {
              id: modelId,
              name: displayName as string,
              description: category === 'cloud' ? 'Cloud-based model' : `${category} local model`,
              category,
            };
          });

          setAvailableModels(models);

          // Set model: prefer localStorage, then first available
          const savedModel = localStorage.getItem('selectedModel');
          if (savedModel && models.some((m) => m.id === savedModel)) {
            setSelectedModel(savedModel);
          } else if (models.length > 0) {
            setSelectedModel(models[0].id);
          }
        }
      } catch (error) {
        console.error('Failed to fetch available models:', error);
        // Fall back to static models and localStorage
        const savedModel = localStorage.getItem('selectedModel');
        if (savedModel) {
          setSelectedModel(savedModel);
        }
      }
    };

    fetchAvailableModels();
  }, []);

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
        // Persist model selection to localStorage
        localStorage.setItem('selectedModel', modelId);
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

              if (data.type === 'token-update') {
                // Update token count in real-time after each response
                setTotalTokens(data.total_tokens || 0);
              } else if (data.type === 'completed') {
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
    <div className="flex h-full w-full bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 overflow-hidden">
      {/* Left / Center Column: Chat Messages + Bottom Input */}
      <div className="flex-1 flex flex-col h-full min-w-0">
        {/* Chat Area - Full Height (Only this scrolls) */}
        <div className="flex-1 overflow-y-auto px-6 py-8 chat-scroll-area">
        <div className="max-w-3xl mx-auto">
          {/* Empty State */}
          {messages.length === 0 && !running && (
            <div className="flex flex-col items-center justify-center h-full">
              <MessageCircle className="w-20 h-20 text-slate-300 dark:text-slate-600 mb-6" />
              <p className="text-xl font-medium text-slate-700 dark:text-slate-300 mb-8">Ask a question to get started</p>

              {/* Suggested Queries */}
              <div className="w-full">
                <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-4 uppercase tracking-wider">Try asking about:</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {suggestedQueries.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setQuery(q);
                        setTimeout(() => simulateQuery(q), 0);
                      }}
                      className="text-left px-4 py-3 rounded-xl bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-sm transition-colors border border-slate-200 dark:border-slate-700 shadow-sm"
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
                    className={`max-w-2xl px-4 py-3 rounded-xl shadow-sm ${
                      msg.type === 'user-query'
                        ? 'bg-blue-600 text-white rounded-br-none'
                        : msg.type === 'tool-call'
                          ? 'bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-700/50 text-amber-900 dark:text-amber-100 rounded-bl-none'
                          : msg.type === 'tool-response'
                            ? 'bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 rounded-bl-none'
                            : msg.type === 'final-answer'
                              ? 'bg-white dark:bg-slate-900/90 border border-emerald-200 dark:border-emerald-700/60 text-slate-900 dark:text-slate-100 rounded-bl-none'
                              : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-300 rounded-bl-none'
                    }`}
                  >
                    {/* Tool Call Header */}
                    {msg.type === 'tool-call' && (
                      <div>
                        <div className="flex items-center gap-2 mb-3">
                          <Zap className="w-4 h-4 animate-pulse text-amber-600 dark:text-amber-400" />
                          <span className="text-xs font-semibold text-amber-700 dark:text-amber-300 uppercase">🔧 Tool Call</span>
                        </div>
                        {msg.toolName && (
                          <div className="space-y-2">
                            {/* Tool name chip */}
                            <div className="inline-block bg-amber-100 dark:bg-amber-600/40 border border-amber-300 dark:border-amber-500/50 rounded-full px-3 py-1 text-xs font-mono font-semibold text-amber-800 dark:text-amber-200">
                              {msg.toolName}
                            </div>
                            {/* Arguments */}
                            {msg.arguments && Object.keys(msg.arguments).length > 0 && (
                              <div className="bg-white/80 dark:bg-slate-900/50 border border-amber-200/60 dark:border-transparent rounded px-3 py-2 text-xs space-y-1">
                                {Object.entries(msg.arguments).map(([key, val]) => (
                                  <div key={key} className="text-slate-600 dark:text-slate-300">
                                    <span className="text-slate-500 dark:text-slate-400">{key}:</span>{' '}
                                    <span className="text-slate-800 dark:text-slate-200 font-mono">
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
                                <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-green-400" />
                                <span className="text-xs font-semibold text-emerald-700 dark:text-green-300 uppercase">✓ Success</span>
                              </>
                            ) : (
                              <>
                                <span className="w-4 h-4 rounded-full bg-red-500 flex items-center justify-center text-white text-xs font-bold">!</span>
                                <span className="text-xs font-semibold text-red-700 dark:text-red-300 uppercase">✗ Failed</span>
                              </>
                            )}
                          </div>
                          {msg.durationMs !== undefined && (
                            <span className="text-xs text-slate-500 dark:text-slate-400">({msg.durationMs.toFixed(0)}ms)</span>
                          )}
                        </div>

                        {/* Tool name and result count/total lines */}
                        {msg.toolName && (
                          <div className="mb-2 flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-mono text-slate-600 dark:text-slate-400">{msg.toolName}</span>
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
                          <div className="mb-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700/50 rounded px-3 py-2 text-xs">
                            <div className="text-red-700 dark:text-red-300 font-semibold mb-1">{msg.error.type}</div>
                            <div className="text-red-600 dark:text-red-200">{msg.error.message}</div>
                          </div>
                        )}

                        {/* Result summary */}
                        {msg.resultSummary && (
                          <div className="max-h-96 overflow-y-auto">
                            {msg.toolName === 'read_file' ? (
                              <CodeDisplay content={msg.resultSummary} />
                            ) : msg.toolName === 'get_tree' ? (
                              <TreeDisplay content={msg.resultSummary} />
                            ) : (
                              <div className="bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded px-3 py-2 text-sm whitespace-pre-wrap font-mono text-slate-800 dark:text-slate-200">
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
                          <div className="w-2 h-2 bg-slate-400 dark:bg-slate-500 rounded-full animate-pulse" />
                          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Thinking</span>
                        </div>
                        <p className="text-sm leading-relaxed italic text-slate-600 dark:text-slate-400">
                          {msg.content}
                        </p>
                      </div>
                    )}

                    {/* Final Answer */}
                    {msg.type === 'final-answer' && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-green-400" />
                          <span className="text-sm font-semibold text-emerald-700 dark:text-green-400">Answer</span>
                        </div>
                        <div className="text-sm leading-relaxed prose prose-slate dark:prose-invert max-w-none">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              h1: ({ children }) => <h1 className="text-xl font-bold mt-4 mb-2 text-slate-900 dark:text-white">{children}</h1>,
                              h2: ({ children }) => <h2 className="text-lg font-bold mt-3 mb-2 text-slate-900 dark:text-white">{children}</h2>,
                              h3: ({ children }) => <h3 className="text-base font-bold mt-2 mb-1 text-slate-800 dark:text-slate-200">{children}</h3>,
                              p: ({ children }) => <p className="mb-2 text-slate-700 dark:text-slate-300 leading-relaxed">{children}</p>,
                              ul: ({ children }) => <ul className="list-disc pl-6 mb-2 text-slate-700 dark:text-slate-300 space-y-1">{children}</ul>,
                              ol: ({ children }) => <ol className="list-decimal pl-6 mb-2 text-slate-700 dark:text-slate-300 space-y-1">{children}</ol>,
                              li: ({ children }) => <li className="mb-0.5 text-slate-700 dark:text-slate-300">{children}</li>,
                              code: ({ children }) => <code className="bg-slate-100 dark:bg-slate-800 text-indigo-700 dark:text-indigo-300 border border-slate-200 dark:border-slate-700/60 px-1.5 py-0.5 rounded font-mono text-xs">{children}</code>,
                              pre: ({ children }) => (
                                <pre className="bg-slate-900 text-slate-200 border border-slate-800 p-3 rounded-lg mb-2 overflow-x-auto font-mono text-xs leading-relaxed whitespace-pre-wrap break-words [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-slate-200 [&>code]:border-0">
                                  {children}
                                </pre>
                              ),
                              table: ({ children }) => (
                                <div className="overflow-x-auto my-3 rounded-lg border border-slate-200 dark:border-slate-700/60 bg-white dark:bg-slate-900/50 shadow-sm">
                                  <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700/60 text-xs">{children}</table>
                                </div>
                              ),
                              thead: ({ children }) => <thead className="bg-slate-50 dark:bg-slate-800/80 text-slate-700 dark:text-slate-200 font-semibold">{children}</thead>,
                              tbody: ({ children }) => <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60 text-slate-700 dark:text-slate-300">{children}</tbody>,
                              tr: ({ children }) => <tr className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">{children}</tr>,
                              th: ({ children }) => (
                                <th className="px-3.5 py-2.5 text-left text-xs font-semibold text-slate-700 dark:text-slate-200 uppercase tracking-wider">
                                  {children}
                                </th>
                              ),
                              td: ({ children }) => <td className="px-3.5 py-2 text-xs text-slate-700 dark:text-slate-300 leading-relaxed align-top">{children}</td>,
                              hr: () => <hr className="border-slate-200 dark:border-slate-800 my-4" />,
                              blockquote: ({ children }) => <blockquote className="border-l-4 border-slate-300 dark:border-slate-600 pl-4 italic text-slate-600 dark:text-slate-400 my-2">{children}</blockquote>,
                              strong: ({ children }) => <strong className="font-bold text-slate-900 dark:text-slate-100">{children}</strong>,
                              em: ({ children }) => <em className="italic text-slate-800 dark:text-slate-300">{children}</em>,
                            }}
                          >
                            {(() => {
                              // Extract clean answer from XML tags if present
                              let content = msg.content;
                              const answerMatch = content.match(/<parameter name="answer">([\s\S]*?)<\/parameter>/);
                              content = answerMatch ? answerMatch[1].trim() : content;

                              // If answer contains tool call XML, return error message
                              if (content.includes('<tool_call>') || content.includes('<invoke')) {
                                return `[LLM Response Issue] The model returned a tool call instead of an answer. This indicates the model did not complete its analysis properly.`;
                              }

                              return content;
                            })()}
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
                  <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm px-4 py-3 rounded-lg rounded-bl-none">
                    <div className="flex gap-2 items-center">
                      <div className="w-2 h-2 bg-slate-400 dark:bg-slate-500 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-slate-400 dark:bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                      <div className="w-2 h-2 bg-slate-400 dark:bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                      <span className="text-xs text-slate-500 dark:text-slate-400 ml-2">Processing...</span>
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
      <div className="flex-shrink-0 bg-white dark:bg-slate-950 px-6 py-4 border-t border-slate-200 dark:border-slate-800">
        <div className="max-w-3xl mx-auto">
          {/* Input Area */}
          <form onSubmit={handleSubmit} className="relative flex gap-2 items-center">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask about your codebase..."
              disabled={running}
              className="flex-1 px-4 py-3 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-blue-500 dark:focus:border-blue-500 transition-colors disabled:opacity-50"
            />

            {/* Settings Button */}
            <div className="relative" ref={settingsRef}>
              <button
                type="button"
                onClick={() => setSettingsOpen(!settingsOpen)}
                className="p-2.5 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 transition-colors border border-slate-200 dark:border-slate-700"
              >
                <Settings className="w-5 h-5" />
              </button>

              {/* Settings Dropdown */}
              {settingsOpen && (
                <div className="absolute bottom-full right-0 mb-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl z-50 min-w-56 text-slate-800 dark:text-slate-200">
                  {/* Tool Details Toggle */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowToolDetails(!showToolDetails);
                      setSettingsOpen(false);
                    }}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-700/80 transition-colors border-b border-slate-100 dark:border-slate-700 first:rounded-t-xl text-slate-700 dark:text-slate-300"
                  >
                    {showToolDetails ? (
                      <>
                        <Eye className="w-4 h-4 text-slate-500 dark:text-slate-400" />
                        <span className="text-sm font-medium">Hide Tool Details</span>
                      </>
                    ) : (
                      <>
                        <EyeOff className="w-4 h-4 text-slate-500 dark:text-slate-400" />
                        <span className="text-sm font-medium">Show Tool Details</span>
                      </>
                    )}
                  </button>

                  {/* Model Selector */}
                  <div className="px-4 py-3 last:rounded-b-xl">
                    <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2 block uppercase">
                      Select Model
                    </label>
                    <select
                      value={selectedModel}
                      onChange={(e) => {
                        handleModelChange(e.target.value);
                        setSettingsOpen(false);
                      }}
                      disabled={changingModel || running}
                      className="w-full px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-slate-900 dark:text-white text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                    >
                      {availableModels.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                      {availableModels.find((m) => m.id === selectedModel)?.description}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Send Button */}
            <button
              type="submit"
              disabled={running || !query.trim()}
              className="p-2.5 rounded-full bg-blue-600 hover:bg-blue-700 text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0 shadow-sm"
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

    {/* Right Column: Execution Stats Sidebar in One Unified Sticky Non-Scrolling Container */}
    <div className="w-80 flex-shrink-0 border-l border-slate-200 dark:border-slate-800/80 bg-slate-50/70 dark:bg-slate-950/50 p-5 flex flex-col justify-start overflow-hidden select-none">
      {/* The Unified Stats Card */}
      <div className="bg-white dark:bg-slate-900/70 border border-slate-200 dark:border-slate-800/90 rounded-2xl p-4 shadow-sm dark:shadow-xl backdrop-blur-sm flex flex-col gap-3.5">
        {/* Header with Live Status Badge */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800/80">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            <span className="text-xs font-bold tracking-wider uppercase text-slate-700 dark:text-slate-200">
              Execution Stats
            </span>
          </div>
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${
            done
              ? 'bg-emerald-50 dark:bg-emerald-950/60 border-emerald-200 dark:border-emerald-500/40 text-emerald-700 dark:text-emerald-300'
              : running
                ? 'bg-blue-50 dark:bg-blue-950/60 border-blue-200 dark:border-blue-500/40 text-blue-700 dark:text-blue-300 animate-pulse'
                : 'bg-slate-100 dark:bg-slate-800/60 border-slate-200 dark:border-slate-700/50 text-slate-600 dark:text-slate-400'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${
              done ? 'bg-emerald-500 dark:bg-emerald-400' : running ? 'bg-blue-500 dark:bg-blue-400 animate-ping' : 'bg-slate-400 dark:bg-slate-500'
            }`} />
            {done ? 'Completed' : running ? 'Running' : 'Ready'}
          </span>
        </div>

        {/* Stacked Stats Rows */}
        <div className="space-y-2">
          {/* Tools */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/80 dark:bg-slate-950/50 border border-amber-200/80 dark:border-amber-500/20 hover:border-amber-400 dark:hover:border-amber-500/40 transition-colors">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 rounded-lg bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400">
                <Wrench className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Tools</div>
                <div className="text-[10px] text-slate-500 dark:text-slate-500">Repository tools</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-base font-bold text-amber-600 dark:text-amber-400 font-mono">{toolCalls}</div>
              <div className="text-[10px] text-amber-700/70 dark:text-amber-300/60">{toolCalls === 1 ? '1 call' : `${toolCalls} calls`}</div>
            </div>
          </div>

          {/* Seconds */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/80 dark:bg-slate-950/50 border border-blue-200/80 dark:border-blue-500/20 hover:border-blue-400 dark:hover:border-blue-500/40 transition-colors">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 rounded-lg bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400">
                <Clock className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Seconds</div>
                <div className="text-[10px] text-slate-500 dark:text-slate-500">Wall clock</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-base font-bold text-blue-600 dark:text-blue-400 font-mono">{Math.floor(elapsed)}s</div>
              <div className="text-[10px] text-blue-700/70 dark:text-blue-300/60">Duration</div>
            </div>
          </div>

          {/* Messages */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/80 dark:bg-slate-950/50 border border-emerald-200/80 dark:border-emerald-500/20 hover:border-emerald-400 dark:hover:border-emerald-500/40 transition-colors">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <MessageSquare className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Messages</div>
                <div className="text-[10px] text-slate-500 dark:text-slate-500">Turns</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-base font-bold text-emerald-600 dark:text-emerald-400 font-mono">{messages.length}</div>
              <div className="text-[10px] text-emerald-700/70 dark:text-emerald-300/60">Total turns</div>
            </div>
          </div>

          {/* Tokens */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/80 dark:bg-slate-950/50 border border-purple-200/80 dark:border-purple-500/20 hover:border-purple-400 dark:hover:border-purple-500/40 transition-colors">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 rounded-lg bg-purple-100 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400">
                <Zap className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Tokens</div>
                <div className="text-[10px] text-slate-500 dark:text-slate-500">Prompt & response</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-base font-bold text-purple-600 dark:text-purple-400 font-mono">{totalTokens.toLocaleString()}</div>
              <div className="text-[10px] text-purple-700/70 dark:text-purple-300/60">Tokens</div>
            </div>
          </div>
        </div>

        {/* Model & Generation Rate Footer */}
        {(modelUsed || selectedModel) && (
          <div className="pt-2.5 border-t border-slate-100 dark:border-slate-800/80 text-xs flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-slate-400" />
                Model
              </span>
              <span className="font-mono text-slate-700 dark:text-slate-200 truncate max-w-[140px]" title={modelUsed || selectedModel}>
                {modelUsed || selectedModel}
              </span>
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-500 dark:text-slate-400">Rate</span>
              <span className="font-semibold text-slate-700 dark:text-slate-300 font-mono">
                {totalTokens > 0 && elapsed > 0 ? (Math.round((totalTokens / elapsed) * 10) / 10) : 0} tokens/sec
              </span>
            </div>
          </div>
        )}
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

        .chat-scroll-area::-webkit-scrollbar {
          width: 6px;
        }
        .chat-scroll-area::-webkit-scrollbar-track {
          background: transparent;
        }
        .chat-scroll-area::-webkit-scrollbar-thumb {
          background: rgba(100, 116, 139, 0.25);
          border-radius: 9999px;
        }
        .chat-scroll-area::-webkit-scrollbar-thumb:hover {
          background: rgba(100, 116, 139, 0.45);
        }
      `}</style>
    </div>
  );
};

export default LLMConversationFlow;
