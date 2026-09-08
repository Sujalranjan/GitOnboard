'use client';

import React, { useState, useEffect, useRef } from 'react';

interface ConversationMessage {
  type: 'user' | 'llm-call' | 'tool-request' | 'tool-response' | 'llm-processing' | 'final-answer';
  text: string;
  dataSize?: number;
  toolCall?: boolean;
}

const conversationFlow: ConversationMessage[] = [
  {
    type: 'user',
    text: 'How does authentication work in this repository?',
  },
  {
    type: 'llm-call',
    text: '[LLM: I need to find auth-related symbols. Calling Tool #3...]',
  },
  {
    type: 'tool-request',
    text: `POST /api/v1/agent/repository-tools/query-graph
{
  "repo_hash": "30afa414-86ab-46ec-a90e-6b21f3ddfd0d",
  "query": "auth, current_user, verify, token"
}`,
  },
  {
    type: 'tool-response',
    text: `✅ RESPONSE (87ms, 8.2KB):
186 symbols found:
• get_current_user (FUNCTION)
• TokenUsage (CLASS)
• verify_token (FUNCTION)
• github_oauth (MODULE)
... 182 more`,
    dataSize: 8.2,
    toolCall: true,
  },
  {
    type: 'llm-processing',
    text: '[LLM: Good! get_current_user seems central. Need to understand its relationships...]',
  },
  {
    type: 'llm-call',
    text: '[LLM: Calling Tool #3 again for relationships...]',
  },
  {
    type: 'tool-request',
    text: `POST /api/v1/agent/repository-tools/query-graph
{
  "symbol_id": "get_current_user",
  "direction": "both",
  "depth": 2
}`,
  },
  {
    type: 'tool-response',
    text: `✅ RESPONSE (94ms, 4.1KB):
INCOMING: 12+ route handlers call it
OUTGOING:
→ jwt.decode()
→ User.query()
→ HTTPException`,
    dataSize: 4.1,
    toolCall: true,
  },
  {
    type: 'llm-processing',
    text: '[LLM: Perfect! Now I see the architecture. Need actual code to explain implementation...]',
  },
  {
    type: 'llm-call',
    text: '[LLM: Calling Tool #2 to read source code...]',
  },
  {
    type: 'tool-request',
    text: `POST /api/v1/agent/repository-tools/read-file
{
  "repo_hash": "30afa414-86ab-46ec-a90e-6b21f3ddfd0d",
  "file_path": "backend/dependencies/auth.py",
  "start_line": 1,
  "end_line": 40
}`,
  },
  {
    type: 'tool-response',
    text: `✅ RESPONSE (412ms, 2.8KB):
def get_current_user(token: str, db: Session):
    payload = jwt.decode(token, SECRET_KEY)
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401)
    return user`,
    dataSize: 2.8,
    toolCall: true,
  },
  {
    type: 'llm-processing',
    text: '[LLM: Complete! I have all the information. Generating comprehensive answer...]',
  },
  {
    type: 'final-answer',
    text: `✨ FINAL ANSWER:

Authentication in GitOnBoard uses JWT tokens with FastAPI dependency injection:

1. Token extracted from Authorization header
2. jwt.decode() verifies signature using SECRET_KEY (HS256)
3. User ID extracted from token payload
4. Database lookup validates the user exists
5. FastAPI injects User object into endpoint handler
6. 401 HTTPException raised for invalid tokens

Key Flow:
Request → Middleware → JWT verify → DB lookup → Dependency injection → Handler

Security:
✓ Stateless token-based auth
✓ Cryptographic verification
✓ Database validation prevents forgery
✓ Automatic enforcement before handler

Tools used: 3 | Data transferred: 15.1 KB | Time: 0.8 seconds`,
  },
];

export const LLMConversationFlow: React.FC = () => {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [running, setRunning] = useState(false);
  const [toolCalls, setToolCalls] = useState(0);
  const [totalData, setTotalData] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [done, setDone] = useState(false);
  const convRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef<number>(0);

  const startConversation = async () => {
    setRunning(true);
    setMessages([]);
    setToolCalls(0);
    setTotalData(0);
    setElapsed(0);
    setDone(false);
    startTimeRef.current = Date.now();

    for (let i = 0; i < conversationFlow.length; i++) {
      const msg = conversationFlow[i];

      setMessages((prev) => [...prev, msg]);

      if (msg.toolCall) {
        setToolCalls((prev) => prev + 1);
        setTotalData((prev) => prev + (msg.dataSize || 0));
      }

      // Update elapsed time
      setElapsed((Date.now() - startTimeRef.current) / 1000);

      // Auto-scroll
      setTimeout(() => {
        if (convRef.current) {
          convRef.current.scrollTop = convRef.current.scrollHeight;
        }
      }, 0);

      await new Promise((resolve) => setTimeout(resolve, 600));
    }

    setRunning(false);
    setDone(true);
  };

  const resetConversation = () => {
    setMessages([]);
    setRunning(false);
    setToolCalls(0);
    setTotalData(0);
    setElapsed(0);
    setDone(false);
  };

  const getMessageClasses = (type: string): string => {
    const baseClasses = 'mb-5 opacity-0 animate-fade-in border-l-4 pl-4';
    switch (type) {
      case 'user':
        return `${baseClasses} border-blue-500 text-blue-600 dark:text-blue-400`;
      case 'llm-call':
      case 'llm-processing':
        return `${baseClasses} border-purple-500 text-purple-600 dark:text-purple-400 italic opacity-90`;
      case 'tool-request':
        return `${baseClasses} border-cyan-500 text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-950/30 p-3 rounded my-2 text-sm font-mono whitespace-pre-wrap`;
      case 'tool-response':
        return `${baseClasses} border-green-500 text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 p-3 rounded my-2 text-sm font-mono whitespace-pre-wrap`;
      case 'final-answer':
        return `${baseClasses} border-blue-500 text-slate-900 dark:text-slate-100 bg-blue-50 dark:bg-blue-950/30 p-4 rounded-lg mt-5 whitespace-pre-wrap`;
      default:
        return baseClasses;
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="text-center mb-10 p-8 bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-950/30 dark:to-blue-950/30 border border-slate-200 dark:border-slate-700 rounded-lg">
        <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent mb-2">
          🤖 LLM Conversation Flow
        </h1>
        <p className="text-slate-600 dark:text-slate-400">
          Real query → tool calls → responses → final answer
        </p>
      </div>

      {/* Controls */}
      <div className="flex gap-3 justify-center mb-6">
        <button
          onClick={startConversation}
          disabled={running}
          className={`px-6 py-2 rounded-lg font-semibold transition-all ${
            running
              ? 'bg-green-500 text-white cursor-not-allowed'
              : 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-200 border-2 border-slate-800 dark:border-slate-100'
          }`}
        >
          ▶ Run Query
        </button>
        <button
          onClick={resetConversation}
          className="px-6 py-2 rounded-lg font-semibold bg-slate-200 dark:bg-slate-700 text-slate-900 dark:text-slate-100 hover:bg-slate-300 dark:hover:bg-slate-600 transition-all border-2 border-slate-300 dark:border-slate-600"
        >
          ↺ Reset
        </button>
      </div>

      {/* Status */}
      <div className="text-center mb-6 text-sm text-slate-600 dark:text-slate-400 min-h-5">
        {running ? (
          <>
            <span className="inline-block w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse"></span>
            Running conversation...
          </>
        ) : done ? (
          <>
            <span className="text-green-600 dark:text-green-400">✅ Conversation Complete!</span>
          </>
        ) : (
          'Ready to run...'
        )}
      </div>

      {/* Conversation */}
      <div
        ref={convRef}
        className="bg-slate-50 dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-700 rounded-lg p-6 font-mono text-sm leading-relaxed max-h-96 overflow-y-auto mb-6"
      >
        {messages.map((msg, idx) => (
          <div key={idx} className={getMessageClasses(msg.type)}>
            {msg.text}
          </div>
        ))}
      </div>

      {/* Metrics */}
      {(messages.length > 0 || done) && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-slate-100 dark:bg-slate-800 p-4 rounded-lg text-center">
            <div className="text-2xl font-bold text-blue-600 dark:text-blue-400 font-mono">
              {toolCalls}
            </div>
            <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">Tool Calls</div>
          </div>
          <div className="bg-slate-100 dark:bg-slate-800 p-4 rounded-lg text-center">
            <div className="text-2xl font-bold text-green-600 dark:text-green-400 font-mono">
              {totalData.toFixed(1)} KB
            </div>
            <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">Data Transferred</div>
          </div>
          <div className="bg-slate-100 dark:bg-slate-800 p-4 rounded-lg text-center">
            <div className="text-2xl font-bold text-purple-600 dark:text-purple-400 font-mono">
              {elapsed.toFixed(2)}s
            </div>
            <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">Total Time</div>
          </div>
        </div>
      )}

      <style jsx>{`
        @keyframes fade-in {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        .animate-fade-in {
          animation: fade-in 0.4s ease-in-out forwards;
        }
      `}</style>
    </div>
  );
};

export default LLMConversationFlow;
