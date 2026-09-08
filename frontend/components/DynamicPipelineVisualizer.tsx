import React, { useState, useEffect } from 'react';
import styled from 'styled-components';

interface PipelineEvent {
  type: string;
  icon: string;
  title: string;
  thinking: string;
  content: string;
}

const pipelineEvents: PipelineEvent[] = [
  {
    type: 'llm-receive',
    icon: '👤',
    title: 'User Question Received',
    thinking:
      'The user asked about authentication. Let me analyze what I need to understand this.',
    content: `Natural Language Input:
"How does authentication work in this repository? What are the main auth functions?"`,
  },
  {
    type: 'llm-decide',
    icon: '🧠',
    title: 'LLM Reasoning: Analyzing Question',
    thinking: `To answer this, I need:
1. Find all auth-related symbols (functions, classes)
2. Understand how they interact
3. Read the actual implementation

Best approach: Use Tool #3 to search and traverse graph, then Tool #2 to read code.`,
    content: `LLM Decision:
"I need Agent Tool #3 (Query Graph) to find auth components and their relationships.
Then Agent Tool #2 (Read File) to understand implementation."`,
  },
  {
    type: 'tool-request',
    icon: '🔧',
    title: 'Tool #3 Request: Search Auth Symbols',
    thinking:
      "Now I'll call the first tool to find all authentication-related symbols.",
    content: `REQUEST TO AGENT TOOL #3:
{
  "repo_hash": "30afa414-86ab-46ec-a90e-6b21f3ddfd0d",
  "query": "auth, current_user, verify, token",
  "filter": {"symbol_types": ["FUNCTION", "CLASS", "METHOD"]}
}`,
  },
  {
    type: 'tool-response',
    icon: '✅',
    title: 'Tool #3 Response: Symbols Found',
    thinking: `Great! The tool found 186 auth-related symbols. I can see get_current_user is a key function.
Let me examine the relationships.`,
    content: `RESPONSE FROM AGENT TOOL #3:
✅ 186 symbols found

Key symbols:
• get_current_user (FUNCTION)
• TokenUsage (CLASS)
• verify_token (FUNCTION)
• AuthenticationDetector (CLASS)
• github_oauth (MODULE)

Time: 87ms
Data: 8.2 KB`,
  },
  {
    type: 'llm-analyze',
    icon: '🔍',
    title: 'LLM Analysis: Process Response',
    thinking: `I found 186 symbols. get_current_user seems to be the central auth function.
Let me query its relationships to understand the architecture.`,
    content: `LLM Processing:
"I see get_current_user is the core function.
Let me find what calls it and what it calls.
This will show me the authentication flow."`,
  },
  {
    type: 'tool-request',
    icon: '🔗',
    title: 'Tool #3 Request: Query Relationships',
    thinking:
      'Now I need to understand how get_current_user fits into the architecture.',
    content: `REQUEST TO AGENT TOOL #3:
{
  "symbol_id": "get_current_user",
  "direction": "both",
  "depth": 2
}`,
  },
  {
    type: 'tool-response',
    icon: '✅',
    title: 'Tool #3 Response: Relationships',
    thinking: `Perfect! I can see get_current_user is called by 12+ route handlers and it calls
JWT decode and user database lookups.`,
    content: `RESPONSE FROM AGENT TOOL #3:

INCOMING EDGES (who calls it):
← execute_run() calls it
← 12+ route handlers depend on it

OUTGOING EDGES (what it calls):
→ jwt.decode()
→ User.query()
→ HTTPException
→ filter()
→ first()

Time: 94ms
Data: 4.1 KB`,
  },
  {
    type: 'llm-decide',
    icon: '🧠',
    title: 'LLM Decision: Need Code',
    thinking:
      'Now I understand the architecture. Let me read the actual implementation to explain how it works.',
    content: `LLM Reasoning:
"I understand the relationships now.
Let me read the actual source code to explain the implementation details."`,
  },
  {
    type: 'tool-request',
    icon: '📄',
    title: 'Tool #2 Request: Read Auth Files',
    thinking: 'I\'ll fetch the actual authentication code from blob storage.',
    content: `REQUEST TO AGENT TOOL #2:
{
  "repo_hash": "30afa414-86ab-46ec-a90e-6b21f3ddfd0d",
  "file_path": "backend/dependencies/auth.py",
  "start_line": 1,
  "end_line": 40
}`,
  },
  {
    type: 'tool-response',
    icon: '✅',
    title: 'Tool #2 Response: Source Code',
    thinking: `Excellent! I have the actual code. Now I understand the complete flow: token extraction,
JWT verification, database lookup, and error handling.`,
    content: `RESPONSE FROM AGENT TOOL #2:

def get_current_user(
    token: str,
    db: Session = Depends(get_db)
) -> User:
    payload = jwt.decode(
        token, SECRET_KEY, algorithms=['HS256']
    )
    user_id = payload.get('sub')
    user = db.query(User).filter(
        User.id == user_id
    ).first()
    if not user:
        raise HTTPException(status_code=401)
    return user

Time: 412ms
Data: 2.8 KB`,
  },
  {
    type: 'llm-final',
    icon: '✨',
    title: 'LLM Synthesis: Generate Answer',
    thinking: `Now I have all the information:
- 186 auth symbols
- Architecture relationships
- Actual implementation code

I can now generate a comprehensive answer.`,
    content: `LLM Final Analysis:
✓ 186 auth symbols analyzed
✓ get_current_user identified as core
✓ JWT verification flow understood
✓ Database validation pattern found
✓ FastAPI dependency injection mechanism clarified
✓ Error handling verified

Ready to synthesize comprehensive answer...`,
  },
];

const Container = styled.div`
  max-width: 1400px;
  margin: 0 auto;
`;

const Header = styled.div`
  text-align: center;
  margin-bottom: 30px;
  padding: 25px;
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.1) 0%, rgba(13, 182, 204, 0.1) 100%);
  border: 2px solid rgba(45, 53, 97, 0.5);
  border-radius: 12px;

  h1 {
    margin: 0 0 10px 0;
    font-size: 2.2em;
    background: linear-gradient(135deg, #00d4ff 0%, #a78bfa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  p {
    margin: 5px 0;
    color: #8b92b5;
    font-size: 0.95em;
  }
`;

const Controls = styled.div`
  display: flex;
  gap: 10px;
  justify-content: center;
  margin: 20px 0;
  flex-wrap: wrap;
`;

const Button = styled.button<{ running?: boolean }>`
  padding: 12px 24px;
  background: ${(props) => (props.running ? '#00ff88' : '#1a1f3a')};
  border: 2px solid ${(props) => (props.running ? '#00ff88' : '#2d3561')};
  color: ${(props) => (props.running ? '#0a0e27' : '#e8eef7')};
  border-radius: 6px;
  cursor: ${(props) => (props.running ? 'not-allowed' : 'pointer')};
  font-size: 1em;
  font-weight: 600;
  transition: all 0.3s ease;

  &:hover:not(:disabled) {
    border-color: #00d4ff;
    background: rgba(0, 212, 255, 0.1);
  }
`;

const ProgressIndicator = styled.div`
  text-align: center;
  margin: 20px 0;
  font-size: 0.9em;
  color: #8b92b5;
  min-height: 20px;
`;

const PulseIcon = styled.span`
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #00ff88;
  margin-right: 8px;
  animation: pulse 1s infinite;

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }

  &.done {
    animation: none;
    opacity: 1;
  }
`;

const Timeline = styled.div`
  position: relative;
  padding: 20px 0;
`;

const Event = styled.div<{ delay: number }>`
  margin-bottom: 30px;
  opacity: 0;
  animation: slideIn 0.6s ease forwards;
  animation-delay: ${(props) => props.delay * 0.1}s;

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;

const EventMarker = styled.div`
  position: absolute;
  left: 20px;
  width: 16px;
  height: 16px;
  background: #00d4ff;
  border: 3px solid #1a1f3a;
  border-radius: 50%;
  top: 20px;
  box-shadow: 0 0 15px #00d4ff;
  z-index: 10;
`;

const EventLine = styled.div`
  position: absolute;
  left: 27px;
  top: 40px;
  width: 2px;
  height: calc(100% + 10px);
  background: linear-gradient(to bottom, #00d4ff, transparent);
  z-index: 1;
`;

const EventContent = styled.div`
  margin-left: 60px;
  padding: 20px;
  background: #1a1f3a;
  border: 2px solid #2d3561;
  border-radius: 8px;
  position: relative;
  transition: all 0.3s ease;

  &:hover {
    border-color: #00d4ff;
    box-shadow: 0 0 15px rgba(0, 212, 255, 0.2);
  }
`;

const EventHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 1.05em;
`;

const EventIcon = styled.span`
  font-size: 1.3em;
  width: 24px;
`;

const EventTitle = styled.span`
  flex: 1;
  color: #e8eef7;
`;

const EventTypeBadge = styled.span<{ type: string }>`
  padding: 4px 10px;
  background: ${(props) => {
    switch (props.type) {
      case 'tool-request':
        return '#06b6d4';
      case 'tool-response':
        return '#00ff88';
      case 'llm-decide':
      case 'llm-final':
        return '#a78bfa';
      default:
        return '#00d4ff';
    }
  }};
  color: ${(props) =>
    props.type === 'tool-response' ? '#0a0e27' : props.type === 'llm-decide' ? '#0a0e27' : '#0a0e27'};
  border-radius: 4px;
  font-size: 0.75em;
  font-weight: bold;
`;

const ThinkingBlock = styled.div`
  background: rgba(255, 165, 0, 0.1);
  border-left: 3px solid #ffa500;
  padding: 12px;
  margin: 12px 0;
  border-radius: 4px;
  font-style: italic;
  color: #8b92b5;
  line-height: 1.6;
  white-space: pre-wrap;
`;

const CodeBlock = styled.div`
  background: rgba(0, 0, 0, 0.4);
  border-left: 3px solid #00d4ff;
  padding: 12px;
  margin: 12px 0;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.85em;
  overflow-x: auto;
  line-height: 1.4;
  color: #00d4ff;
  white-space: pre-wrap;
`;

const Metrics = styled.div<{ visible: boolean }>`
  display: ${(props) => (props.visible ? 'grid' : 'none')};
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
  margin-top: 40px;
  padding: 20px;
  background: #1a1f3a;
  border: 1px solid #2d3561;
  border-radius: 8px;
`;

const MetricCard = styled.div`
  text-align: center;
  padding: 15px;
  background: rgba(0, 212, 255, 0.05);
  border: 1px solid #2d3561;
  border-radius: 6px;
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

const FinalAnswer = styled.div<{ visible: boolean }>`
  display: ${(props) => (props.visible ? 'block' : 'none')};
  margin-top: 40px;
  padding: 30px;
  background: linear-gradient(135deg, rgba(6, 182, 204, 0.2) 0%, rgba(167, 139, 250, 0.2) 100%);
  border: 2px solid #00d4ff;
  border-radius: 12px;

  h2 {
    color: #00d4ff;
    margin-top: 0;
    font-size: 1.8em;
  }

  ul {
    text-align: left;
    display: inline-block;
    line-height: 1.8;
  }

  li {
    margin: 8px 0;
  }
`;

const AnswerCodeBlock = styled.div`
  background: rgba(0, 0, 0, 0.3);
  padding: 15px;
  border-radius: 8px;
  font-family: monospace;
  font-size: 0.85em;
  line-height: 1.6;
  color: #00d4ff;
  text-align: left;
  white-space: pre-wrap;
  margin: 15px 0;
`;

const Highlight = styled.span`
  color: #00d4ff;
  font-weight: bold;
`;

export const DynamicPipelineVisualizer: React.FC = () => {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [toolCalls, setToolCalls] = useState(0);
  const [totalData, setTotalData] = useState(0);
  const [totalTime, setTotalTime] = useState(0);
  const [showMetrics, setShowMetrics] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);
  const [startTime, setStartTime] = useState<number | null>(null);

  const startPipeline = async () => {
    setRunning(true);
    setEvents([]);
    setToolCalls(0);
    setTotalData(0);
    setTotalTime(0);
    setShowMetrics(true);
    setShowAnswer(false);
    setStartTime(Date.now());

    for (let i = 0; i < pipelineEvents.length; i++) {
      const event = pipelineEvents[i];

      // Calculate metrics
      let calls = toolCalls;
      let data = totalData;

      if (event.type.includes('tool-request')) {
        calls += 1;
      }
      if (event.content.includes('8.2 KB')) {
        data += 8.2;
      }
      if (event.content.includes('4.1 KB')) {
        data += 4.1;
      }
      if (event.content.includes('2.8 KB')) {
        data += 2.8;
      }

      setToolCalls(calls);
      setTotalData(data);

      setEvents((prev) => [...prev, event]);

      // Wait before showing next event
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }

    setRunning(false);
    setShowAnswer(true);
    if (startTime) {
      setTotalTime((Date.now() - startTime) / 1000);
    }
  };

  const resetPipeline = () => {
    setEvents([]);
    setRunning(false);
    setToolCalls(0);
    setTotalData(0);
    setTotalTime(0);
    setShowMetrics(false);
    setShowAnswer(false);
  };

  const getBadgeType = (type: string) => {
    if (type.includes('tool-request')) return 'TOOL REQUEST';
    if (type.includes('tool-response')) return 'TOOL RESPONSE';
    if (type.includes('llm')) return 'LLM';
    return 'PROCESS';
  };

  return (
    <Container>
      <Header>
        <h1>🚀 Dynamic LLM Pipeline - Live Execution</h1>
        <p>Watch how the LLM thinks and responds at each step</p>
        <p style={{ fontSize: '0.85em', marginTop: '15px' }}>
          Question: "How does authentication work?"
        </p>
      </Header>

      <Controls>
        <Button onClick={startPipeline} disabled={running} running={running}>
          ▶ Start Pipeline
        </Button>
        <Button onClick={resetPipeline}>↺ Reset</Button>
      </Controls>

      <ProgressIndicator>
        {running ? (
          <>
            <PulseIcon />
            Step {events.length + 1}/{pipelineEvents.length}:{' '}
            {events[events.length - 1]?.title || 'Initializing...'}
          </>
        ) : events.length > 0 ? (
          <>
            <PulseIcon className="done" />✅ Pipeline Complete!
          </>
        ) : (
          'Ready to start...'
        )}
      </ProgressIndicator>

      <Timeline>
        {events.map((event, idx) => (
          <Event key={idx} delay={idx}>
            <EventMarker />
            <EventLine />
            <EventContent>
              <EventHeader>
                <EventIcon>{event.icon}</EventIcon>
                <EventTitle>{event.title}</EventTitle>
                <EventTypeBadge type={event.type}>{getBadgeType(event.type)}</EventTypeBadge>
              </EventHeader>
              {event.thinking && <ThinkingBlock>💭 LLM Thinking:\n{event.thinking}</ThinkingBlock>}
              <CodeBlock>{event.content}</CodeBlock>
            </EventContent>
          </Event>
        ))}
      </Timeline>

      <Metrics visible={showMetrics}>
        <MetricCard>
          <MetricValue>{toolCalls}</MetricValue>
          <MetricLabel>Tool Calls</MetricLabel>
        </MetricCard>
        <MetricCard>
          <MetricValue>{totalTime.toFixed(2)}s</MetricValue>
          <MetricLabel>Total Time</MetricLabel>
        </MetricCard>
        <MetricCard>
          <MetricValue>{totalData.toFixed(1)} KB</MetricValue>
          <MetricLabel>Data Transferred</MetricLabel>
        </MetricCard>
        <MetricCard>
          <MetricValue>
            {events.length}/{pipelineEvents.length}
          </MetricValue>
          <MetricLabel>Stages Complete</MetricLabel>
        </MetricCard>
      </Metrics>

      <FinalAnswer visible={showAnswer}>
        <h2>✨ Final Comprehensive Answer</h2>

        <p>
          <strong>How Authentication Works in GitOnBoard:</strong>
        </p>

        <p>Based on analyzing {toolCalls} tool calls and retrieving {totalData.toFixed(1)} KB of data, here&apos;s the complete authentication architecture:</p>

        <AnswerCodeBlock>
Request with JWT Token
       ↓
[Middleware extracts from Authorization header]
       ↓
[jwt.decode(token, SECRET_KEY) - HS256 verification]
       ↓
[Extract user_id from token payload via payload.get('sub')]
       ↓
[Database lookup: db.query(User).filter(User.id == user_id).first()]
       ↓
[FastAPI dependency injection - User object into endpoint]
       ↓
✅ Handler executes with authenticated user context
        </AnswerCodeBlock>

        <p>
          <strong>Key Architecture Components:</strong>
        </p>
        <ul>
          <li>
            <Highlight>get_current_user()</Highlight> - Core auth function (called by 12+ endpoints)
          </li>
          <li>
            <Highlight>JWT Verification</Highlight> - HS256 algorithm with SECRET_KEY
          </li>
          <li>
            <Highlight>Database Validation</Highlight> - User lookup prevents token forgery
          </li>
          <li>
            <Highlight>FastAPI Integration</Highlight> - Depends() decorator for automatic injection
          </li>
          <li>
            <Highlight>Error Handling</Highlight> - 401 HTTPException on invalid tokens
          </li>
          <li>
            <Highlight>OAuth Support</Highlight> - GitHub OAuth provider for alternative auth
          </li>
        </ul>

        <p>
          <strong>Performance Summary:</strong>
        </p>
        <ul>
          <li>
            Total Pipeline Time: <Highlight>{totalTime.toFixed(2)}s</Highlight>
          </li>
          <li>
            Data Retrieved: <Highlight>{totalData.toFixed(1)} KB</Highlight>
          </li>
          <li>
            Tool Calls: <Highlight>{toolCalls}</Highlight>
          </li>
          <li>
            vs Re-parsing: <Highlight>~100x faster</Highlight>
          </li>
        </ul>
      </FinalAnswer>
    </Container>
  );
};

export default DynamicPipelineVisualizer;
