'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Zap, MessageCircle, CheckCircle2 } from 'lucide-react';

interface Message {
  type: 'user-query' | 'llm-thinking' | 'tool-searching' | 'tool-found' | 'tool-analyzing' | 'tool-reading' | 'final-answer';
  content: string;
  icon?: React.ReactNode;
}

export const LLMConversationFlow: React.FC = () => {
  const [query, setQuery] = useState('');
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [toolCalls, setToolCalls] = useState(0);
  const [totalData, setTotalData] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [done, setDone] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef<number>(0);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const simulateQuery = async (userQuery: string) => {
    setRunning(true);
    setMessages([]);
    setToolCalls(0);
    setTotalData(0);
    setElapsed(0);
    setDone(false);
    startTimeRef.current = Date.now();

    const flowSteps = [
      {
        type: 'user-query' as const,
        content: userQuery,
        delay: 0,
      },
      {
        type: 'llm-thinking' as const,
        content: 'Analyzing your question... I need to search for relevant code patterns and understand the architecture.',
        delay: 1000,
      },
      {
        type: 'tool-searching' as const,
        content: 'Searching repository for related symbols and components...',
        delay: 2000,
        toolCall: true,
        data: 8.2,
      },
      {
        type: 'tool-found' as const,
        content: '✓ Found 186 relevant symbols including key components and their relationships',
        delay: 3500,
      },
      {
        type: 'tool-analyzing' as const,
        content: 'Understanding how components interact with each other...',
        delay: 4500,
        toolCall: true,
        data: 4.1,
      },
      {
        type: 'tool-reading' as const,
        content: 'Reading implementation details and source code...',
        delay: 6000,
        toolCall: true,
        data: 2.8,
      },
      {
        type: 'final-answer' as const,
        content: generateAnswer(userQuery),
        delay: 8000,
      },
    ];

    for (const step of flowSteps) {
      await new Promise(resolve => setTimeout(resolve, step.delay));

      setMessages(prev => [...prev, {
        type: step.type,
        content: step.content,
      }]);

      if ('toolCall' in step && step.toolCall) {
        setToolCalls(prev => prev + 1);
        setTotalData(prev => prev + (step.data || 0));
      }

      setElapsed((Date.now() - startTimeRef.current) / 1000);
    }

    setRunning(false);
    setDone(true);
  };

  const generateAnswer = (userQuery: string) => {
    const answers: Record<string, string> = {
      auth: `Authentication is handled through JWT tokens with FastAPI dependency injection. Here's how it works:

1. Users send requests with JWT tokens in the Authorization header
2. The system verifies the token signature using a secret key
3. Valid tokens are decoded to extract the user ID
4. The system validates that the user exists in the database
5. The user object is automatically injected into request handlers

This creates a secure, stateless authentication system that validates on every request.`,

      architecture: `The repository uses a layered architecture:

Frontend Layer: React/Next.js handles the UI
API Layer: FastAPI provides REST endpoints
Business Logic: Python handles analysis and processing
Data Layer: PostgreSQL stores the repository data
Storage: Azure Blob Storage holds file contents

Components communicate through well-defined APIs with clear separation of concerns.`,

      database: `The database stores repository data in a normalized schema:

- Repositories: Core metadata and identification
- Symbols: Functions, classes, and variables discovered during analysis
- Relationships: How symbols call or reference each other
- Files: Source code file metadata and content pointers
- Analysis: Results from code parsing and analysis runs

This structure enables fast querying of code relationships.`,

      default: `Analysis of your query is complete! The system has:

• Searched through 186+ relevant code symbols
• Analyzed relationships and dependencies
• Retrieved source code implementations
• Built a comprehensive understanding

The codebase is well-structured with clear patterns and proper separation of concerns.`,
    };

    const lowerQuery = userQuery.toLowerCase();
    for (const [key, answer] of Object.entries(answers)) {
      if (lowerQuery.includes(key)) return answer;
    }
    return answers.default;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !running) {
      simulateQuery(query);
    }
  };

  const suggestedQueries = [
    'How does authentication work?',
    'What is the system architecture?',
    'How is data stored?',
    'What are the key components?',
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 dark:from-slate-900 dark:to-slate-800 p-4 sm:p-6">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <MessageCircle className="w-8 h-8 text-blue-600 dark:text-blue-400" />
            <h1 className="text-3xl sm:text-4xl font-bold text-slate-900 dark:text-white">
              Repository Assistant
            </h1>
          </div>
          <p className="text-slate-600 dark:text-slate-400 text-lg">
            Ask questions about your codebase and get instant answers
          </p>
        </div>

        {/* Chat Area */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-lg p-6 mb-6 min-h-96 max-h-96 overflow-y-auto space-y-4">
          {messages.length === 0 && !running && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <MessageCircle className="w-16 h-16 text-slate-300 dark:text-slate-600 mb-4" />
              <p className="text-slate-500 dark:text-slate-400">
                Ask a question to get started
              </p>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`animate-slide-up ${
                msg.type === 'user-query'
                  ? 'flex justify-end'
                  : 'flex justify-start'
              }`}
            >
              <div
                className={`max-w-xs sm:max-w-sm lg:max-w-md px-4 py-3 rounded-lg ${
                  msg.type === 'user-query'
                    ? 'bg-blue-600 text-white rounded-br-none'
                    : msg.type === 'final-answer'
                      ? 'bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/30 dark:to-emerald-950/30 border-2 border-green-200 dark:border-green-800 text-slate-900 dark:text-white rounded-bl-none'
                      : 'bg-slate-100 dark:bg-slate-700 text-slate-900 dark:text-white rounded-bl-none'
                }`}
              >
                {msg.type === 'tool-searching' && (
                  <div className="flex items-center gap-2 mb-1">
                    <Zap className="w-4 h-4 animate-pulse" />
                    <span className="text-xs font-semibold">Searching</span>
                  </div>
                )}
                {msg.type === 'tool-analyzing' && (
                  <div className="flex items-center gap-2 mb-1">
                    <Zap className="w-4 h-4 animate-pulse" />
                    <span className="text-xs font-semibold">Analyzing</span>
                  </div>
                )}
                {msg.type === 'tool-reading' && (
                  <div className="flex items-center gap-2 mb-1">
                    <Zap className="w-4 h-4 animate-pulse" />
                    <span className="text-xs font-semibold">Reading Code</span>
                  </div>
                )}
                {msg.type === 'final-answer' && (
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
                    <span className="text-sm font-semibold text-green-700 dark:text-green-400">Answer</span>
                  </div>
                )}
                <p className="text-sm leading-relaxed whitespace-pre-wrap">
                  {msg.content}
                </p>
              </div>
            </div>
          ))}

          {running && messages.length > 0 && (
            <div className="flex justify-start">
              <div className="bg-slate-100 dark:bg-slate-700 px-4 py-3 rounded-lg rounded-bl-none">
                <div className="flex gap-2">
                  <div className="w-2 h-2 bg-slate-400 dark:bg-slate-500 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-slate-400 dark:bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  <div className="w-2 h-2 bg-slate-400 dark:bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Metrics */}
        {done && (
          <div className="grid grid-cols-3 gap-3 mb-6">
            <div className="bg-blue-100 dark:bg-blue-950/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{toolCalls}</div>
              <div className="text-xs text-blue-700 dark:text-blue-300">Searches</div>
            </div>
            <div className="bg-green-100 dark:bg-green-950/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-green-600 dark:text-green-400">{totalData.toFixed(1)} KB</div>
              <div className="text-xs text-green-700 dark:text-green-300">Data Analyzed</div>
            </div>
            <div className="bg-purple-100 dark:bg-purple-950/50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">{elapsed.toFixed(2)}s</div>
              <div className="text-xs text-purple-700 dark:text-purple-300">Response Time</div>
            </div>
          </div>
        )}

        {/* Input Area */}
        <form onSubmit={handleSubmit} className="mb-6">
          <div className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask about your codebase..."
              disabled={running}
              className="flex-1 px-4 py-3 rounded-lg border-2 border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-500 dark:placeholder-slate-400 focus:outline-none focus:border-blue-500 dark:focus:border-blue-400 transition-colors disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={running || !query.trim()}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white font-semibold rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {running ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span className="hidden sm:inline">Analyzing</span>
                </>
              ) : (
                <>
                  <span className="hidden sm:inline">Ask</span>
                  <span className="sm:hidden">→</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Suggested Queries */}
        {messages.length === 0 && !running && (
          <div className="bg-white dark:bg-slate-800 rounded-lg p-4">
            <p className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-3 uppercase">
              Try asking about:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {suggestedQueries.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    setQuery(q);
                    setTimeout(() => simulateQuery(q), 0);
                  }}
                  className="text-left px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-600 text-sm transition-colors"
                >
                  → {q}
                </button>
              ))}
            </div>
          </div>
        )}
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
