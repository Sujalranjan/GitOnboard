import React, { useState, useEffect, useRef } from 'react';
import styled from 'styled-components';

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

const Container = styled.div`
  max-width: 1000px;
  margin: 0 auto;
`;

const Header = styled.div`
  text-align: center;
  margin-bottom: 40px;
  padding: 30px;
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.1) 0%, rgba(13, 182, 204, 0.1) 100%);
  border: 2px solid rgba(45, 53, 97, 0.5);
  border-radius: 12px;

  h1 {
    margin: 0 0 10px 0;
    font-size: 2em;
    background: linear-gradient(135deg, #00d4ff 0%, #a78bfa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  p {
    margin: 5px 0;
    color: #8b92b5;
  }
`;

const Controls = styled.div`
  display: flex;
  gap: 10px;
  justify-content: center;
  margin-bottom: 30px;
`;

const Button = styled.button<{ running?: boolean }>`
  padding: 12px 24px;
  background: ${(props) => (props.running ? '#00ff88' : '#1a1f3a')};
  border: 2px solid ${(props) => (props.running ? '#00ff88' : '#2d3561')};
  color: ${(props) => (props.running ? '#0a0e27' : '#e8eef7')};
  border-radius: 6px;
  cursor: ${(props) => (props.running ? 'not-allowed' : 'pointer')};
  font-weight: 600;
  transition: all 0.3s;

  &:hover:not(:disabled) {
    border-color: #00d4ff;
    background: rgba(0, 212, 255, 0.1);
  }
`;

const Status = styled.div<{ done?: boolean }>`
  text-align: center;
  margin-top: 20px;
  color: ${(props) => (props.done ? '#00ff88' : '#8b92b5')};
  font-size: 0.9em;
`;

const Conversation = styled.div`
  background: #1a1f3a;
  border: 2px solid #2d3561;
  border-radius: 12px;
  padding: 30px;
  font-size: 0.95em;
  line-height: 1.8;
  max-height: 65vh;
  overflow-y: auto;
  margin-bottom: 20px;
  font-family: 'Monaco', 'Courier New', monospace;
`;

const Message = styled.div<{ type: string }>`
  margin-bottom: 20px;
  opacity: 0;
  animation: fadeIn 0.4s ease forwards;
  border-left: 3px solid;
  padding-left: 15px;

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  ${(props) => {
    switch (props.type) {
      case 'user':
        return `
          color: #00d4ff;
          border-color: #00d4ff;
        `;
      case 'llm-call':
      case 'llm-processing':
        return `
          color: #a78bfa;
          border-color: #a78bfa;
          font-style: italic;
          opacity: 0.9;
        `;
      case 'tool-request':
        return `
          color: #06b6d4;
          border-color: #06b6d4;
          background: rgba(6, 182, 204, 0.05);
          padding: 12px;
          border-radius: 4px;
          margin: 10px 0;
          font-size: 0.9em;
          white-space: pre-wrap;
        `;
      case 'tool-response':
        return `
          color: #00ff88;
          border-color: #00ff88;
          background: rgba(0, 255, 136, 0.05);
          padding: 12px;
          border-radius: 4px;
          margin: 10px 0;
          font-size: 0.9em;
          white-space: pre-wrap;
        `;
      case 'final-answer':
        return `
          color: #00d4ff;
          border-color: #00d4ff;
          background: rgba(0, 212, 255, 0.1);
          padding: 15px;
          border-radius: 4px;
          margin-top: 20px;
          white-space: pre-wrap;
        `;
      default:
        return '';
    }
  }}
`;

const Metrics = styled.div<{ visible: boolean }>`
  display: ${(props) => (props.visible ? 'grid' : 'none')};
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
  margin-top: 30px;
`;

const MetricCard = styled.div`
  background: #1a1f3a;
  border: 1px solid #2d3561;
  border-radius: 6px;
  padding: 15px;
  text-align: center;
`;

const MetricValue = styled.div`
  font-size: 1.8em;
  font-weight: bold;
  color: #00d4ff;
  font-family: monospace;
`;

const MetricLabel = styled.div`
  font-size: 0.85em;
  color: #8b92b5;
  margin-top: 5px;
`;

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

  return (
    <Container>
      <Header>
        <h1>🤖 LLM Conversation Flow</h1>
        <p>Real query → tool calls → responses → final answer</p>
      </Header>

      <Controls>
        <Button onClick={startConversation} disabled={running} running={running}>
          ▶ Run Query
        </Button>
        <Button onClick={resetConversation}>↺ Reset</Button>
      </Controls>

      <Status done={done}>
        {running ? (
          <>
            <span style={{ marginRight: '8px' }}>●</span> Running conversation...
          </>
        ) : done ? (
          <>
            <span style={{ color: '#00ff88', marginRight: '8px' }}>✅</span> Conversation Complete!
          </>
        ) : (
          'Ready to run...'
        )}
      </Status>

      <Conversation ref={convRef}>
        {messages.map((msg, idx) => (
          <Message key={idx} type={msg.type}>
            {msg.text}
          </Message>
        ))}
      </Conversation>

      {(messages.length > 0 || done) && (
        <Metrics visible={true}>
          <MetricCard>
            <MetricValue>{toolCalls}</MetricValue>
            <MetricLabel>Tool Calls</MetricLabel>
          </MetricCard>
          <MetricCard>
            <MetricValue>{totalData.toFixed(1)} KB</MetricValue>
            <MetricLabel>Data Transferred</MetricLabel>
          </MetricCard>
          <MetricCard>
            <MetricValue>{elapsed.toFixed(2)}s</MetricValue>
            <MetricLabel>Total Time</MetricLabel>
          </MetricCard>
        </Metrics>
      )}
    </Container>
  );
};

export default LLMConversationFlow;
