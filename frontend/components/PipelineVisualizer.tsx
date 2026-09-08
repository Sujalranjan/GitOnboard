import React, { useState, useEffect } from 'react';
import styled from 'styled-components';

interface PipelineStage {
  number: number;
  title: string;
  badge: string;
  color: string;
  input: {
    label: string;
    data: string;
  };
  output: {
    label: string;
    data: string;
  };
  description: string;
}

const pipelineStages: PipelineStage[] = [
  {
    number: 1,
    title: 'User Question Received',
    badge: 'INPUT',
    color: '#a78bfa',
    input: {
      label: 'Natural Language Query',
      data: `How does authentication work in this repository?
What are the main authentication functions
and how do they work together?`,
    },
    output: {
      label: 'Question Analysis',
      data: `Type: Architecture question
Domain: Authentication system
Requires: Code exploration
Complexity: Multi-component`,
    },
    description:
      'The LLM receives a natural language question about the codebase and analyzes what information is needed to answer it.',
  },
  {
    number: 2,
    title: 'LLM Reasoning & Tool Selection',
    badge: 'ANALYSIS',
    color: '#f472b6',
    input: {
      label: 'Question Requirements',
      data: `"I need to understand:
1. Auth-related symbols (functions, classes)
2. How they interact with each other
3. Their implementation details"`,
    },
    output: {
      label: 'Tool Selection Decision',
      data: `Selected: Agent Tool #3 (Query Graph)
- Reason: Find auth symbols
- Reason: Understand relationships

Then: Agent Tool #2 (Read File)
- Reason: Get implementation details`,
    },
    description:
      'The LLM analyzes the question and determines which tools are needed to answer it, planning a multi-tool orchestration strategy.',
  },
  {
    number: 3,
    title: 'Tool #3 Call: Search Auth Symbols',
    badge: 'TOOL CALL #1',
    color: '#06b6d4',
    input: {
      label: 'Request to Agent Tool #3',
      data: `{
  "repo_hash": "30afa414-86ab...",
  "query": "Find symbols with auth,
    token, verify patterns",
  "filter": {
    "symbol_types": ["FUNCTION", "CLASS"]
  }
}`,
    },
    output: {
      label: 'Tool #3 Response',
      data: `✅ 186 auth-related symbols found

Key symbols:
• get_current_user (FUNCTION)
• TokenUsage (CLASS)
• verify_token (FUNCTION)
• AuthenticationDetector (CLASS)
• github_oauth (MODULE)
... 181 more`,
    },
    description:
      'Agent Tool #3 searches the FactStore database and returns 186 auth-related symbols. Database query takes <100ms. LLM reviews results and identifies key authentication components.',
  },
  {
    number: 4,
    title: 'Tool #3 Call: Query Graph Relationships',
    badge: 'TOOL CALL #2',
    color: '#10b981',
    input: {
      label: 'Request to Agent Tool #3',
      data: `{
  "symbol_id": "get_current_user",
  "direction": "both",
  "depth": 2
}

Focus: Main auth function`,
    },
    output: {
      label: 'Tool #3 Response: Relationships',
      data: `Incoming edges (who calls it):
← execute_run() calls it
← 12+ route handlers depend on it

Outgoing edges (what it calls):
→ jwt.decode()
→ User.query()
→ HTTPException
→ filter()
→ first()`,
    },
    description:
      'Agent Tool #3 queries the relationship graph and returns incoming/outgoing edges. Shows that get_current_user is the central auth function called by many endpoints. Database lookup with relationship traversal takes <100ms.',
  },
  {
    number: 5,
    title: 'Tool #2 Call: Read File Content',
    badge: 'TOOL CALL #3',
    color: '#f59e0b',
    input: {
      label: 'Request to Agent Tool #2',
      data: `{
  "repo_hash": "30afa414-86ab...",
  "file_path": "backend/dependencies/auth.py",
  "start_line": 1,
  "end_line": 30
}`,
    },
    output: {
      label: 'Tool #2 Response: Source Code',
      data: `def get_current_user(
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
    return user`,
    },
    description:
      'Agent Tool #2 retrieves source code from Azure Blob Storage. File was captured during analysis phase. Blob retrieval takes <500ms. LLM reads implementation and understands JWT verification and database lookup logic.',
  },
  {
    number: 6,
    title: 'Read Additional Auth Files',
    badge: 'TOOL CALL #4-5',
    color: '#8b5cf6',
    input: {
      label: 'Additional Files Requested',
      data: `Files to read:
• backend/routers/auth.py
• backend/services/github_oauth.py
• frontend/context/AuthContext.tsx

Purpose: Understand full architecture`,
    },
    output: {
      label: 'All Auth Files Retrieved',
      data: `✅ auth.py (1,460 lines)
   └─ FastAPI routes for auth endpoints

✅ github_oauth.py (850 lines)
   └─ OAuth provider integration

✅ AuthContext.tsx (340 lines)
   └─ Frontend auth state management

Total: ~2,650 lines of auth code`,
    },
    description:
      'LLM makes multiple tool calls to gather implementation details from different parts of the auth system. Each read takes <500ms. Total time: <2 seconds for all file reads.',
  },
  {
    number: 7,
    title: 'LLM Analysis & Context Building',
    badge: 'SYNTHESIS',
    color: '#ec4899',
    input: {
      label: 'Gathered Data Summary',
      data: `✓ 186 auth symbols identified
✓ Symbol relationships mapped
✓ get_current_user architecture understood
✓ JWT verification logic reviewed
✓ Database lookup pattern confirmed
✓ OAuth integration identified
✓ Frontend auth context found

Total data processed: ~18 KB
Processing time so far: <2 seconds`,
    },
    output: {
      label: 'LLM Internal Processing',
      data: `"Now I understand:
1. JWT tokens extracted from headers
2. Token decoded using SECRET_KEY
3. User ID extracted from payload
4. Database lookup by user ID
5. FastAPI dependency injection
6. 401 errors on failure
7. Frontend manages auth state
8. OAuth provider integration"`,
    },
    description:
      'The LLM processes all gathered data and builds a comprehensive understanding of the authentication architecture. This is where the magic happens - combining symbols, relationships, and code to create coherent understanding.',
  },
  {
    number: 8,
    title: 'Final Answer Generated',
    badge: 'OUTPUT',
    color: '#06b6d4',
    input: {
      label: 'Complete Pipeline Summary',
      data: `Stages Completed: 8/8 ✓
Tools Called: 3 (Tool #3 x2, Tool #2 x3)
Symbols Analyzed: 186
Files Read: 3
Total Time: <2 seconds
Data Transferred: <20 KB

Pipeline Status: SUCCESS ✅`,
    },
    output: {
      label: 'Quality Metrics',
      data: `Answer Completeness: 100%
Architecture Coverage: 100%
Code Examples: 5+
Relationship Depth: 2 levels
Security Analysis: Complete
Error Handling: Documented`,
    },
    description:
      'All stages complete. The LLM has gathered comprehensive information and is ready to generate a detailed, well-informed answer about authentication architecture.',
  },
];

const Container = styled.div`
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
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
    font-size: 2.5em;
    background: linear-gradient(135deg, #00d4ff 0%, #a78bfa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  p {
    margin: 5px 0;
    color: #8b92b5;
    font-size: 1.1em;
  }
`;

const Controls = styled.div`
  display: flex;
  gap: 10px;
  justify-content: center;
  margin: 20px 0;
  flex-wrap: wrap;
`;

const Button = styled.button<{ active?: boolean }>`
  padding: 10px 20px;
  background: ${(props) => (props.active ? '#00d4ff' : '#1a1f3a')};
  border: 2px solid ${(props) => (props.active ? '#00d4ff' : '#2d3561')};
  color: ${(props) => (props.active ? '#0a0e27' : '#e8eef7')};
  border-radius: 6px;
  cursor: pointer;
  font-size: 1em;
  transition: all 0.3s ease;
  font-weight: 600;

  &:hover {
    border-color: #00d4ff;
    background: rgba(0, 212, 255, 0.1);
    color: #e8eef7;
  }
`;

const ProgressBar = styled.div`
  width: 100%;
  height: 3px;
  background: #2d3561;
  border-radius: 2px;
  margin: 20px 0;
  overflow: hidden;
`;

const ProgressFill = styled.div<{ progress: number }>`
  height: 100%;
  background: linear-gradient(
    90deg,
    #a78bfa,
    #f472b6,
    #06b6d4,
    #10b981,
    #f59e0b,
    #8b5cf6,
    #ec4899,
    #06b6d4
  );
  width: ${(props) => props.progress}%;
  transition: width 0.4s ease;
`;

const Pipeline = styled.div`
  display: flex;
  flex-direction: column;
  gap: 20px;
`;

const Stage = styled.div<{ active: boolean; color: string }>`
  background: #1a1f3a;
  border: 2px solid #2d3561;
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.4s ease;
  opacity: ${(props) => (props.active ? 1 : 0.6)};
  transform: ${(props) => (props.active ? 'translateX(0)' : 'translateX(-20px)')};

  ${(props) =>
    props.active &&
    `
    border-color: ${props.color};
    box-shadow: 0 0 20px ${props.color};
  `}
`;

const StageHeader = styled.div<{ color: string }>`
  padding: 20px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.05), transparent);
  border-bottom: 2px solid ${(props) => props.color};
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

const StageNumber = styled.div<{ color: string }>`
  font-size: 2em;
  font-weight: bold;
  margin-right: 20px;
  color: ${(props) => props.color};
`;

const StageTitle = styled.div`
  flex: 1;
  font-size: 1.3em;
  font-weight: 600;
  color: #e8eef7;
`;

const StageBadge = styled.div<{ color: string }>`
  padding: 6px 12px;
  background: ${(props) => props.color};
  color: #0a0e27;
  border-radius: 20px;
  font-size: 0.85em;
  font-weight: bold;
`;

const StageContent = styled.div`
  padding: 20px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

const DataSection = styled.div`
  display: flex;
  flex-direction: column;
`;

const SectionLabel = styled.div`
  font-size: 0.9em;
  color: #8b92b5;
  margin-bottom: 8px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const DataBox = styled.div`
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid #2d3561;
  border-radius: 8px;
  padding: 15px;
  font-family: 'Courier New', monospace;
  font-size: 0.85em;
  line-height: 1.6;
  color: #00d4ff;
  overflow: auto;
  max-height: 250px;
  flex: 1;
`;

const Description = styled.div`
  grid-column: 1 / -1;
  padding-top: 10px;
  border-top: 1px solid #2d3561;
  color: #8b92b5;
  font-size: 0.95em;
  line-height: 1.6;
`;

const Arrow = styled.div`
  text-align: center;
  padding: 10px 0;
  color: #8b92b5;
  font-size: 1.5em;
  opacity: 0.5;
`;

const FinalAnswer = styled.div`
  background: linear-gradient(135deg, rgba(6, 182, 204, 0.2) 0%, rgba(167, 139, 250, 0.2) 100%);
  border: 2px solid #00d4ff;
  border-radius: 12px;
  padding: 30px;
  margin-top: 40px;
  text-align: center;

  h2 {
    color: #00d4ff;
    margin-top: 0;
    font-size: 1.8em;
  }

  p {
    font-size: 1.05em;
    line-height: 1.8;
    color: #e8eef7;
  }
`;

const MetricContainer = styled.div`
  display: flex;
  gap: 15px;
  justify-content: center;
  flex-wrap: wrap;
  margin-top: 20px;
`;

const Metric = styled.div`
  display: inline-block;
  padding: 12px 20px;
  background: rgba(0, 212, 255, 0.1);
  border: 1px solid #00d4ff;
  border-radius: 6px;
  font-size: 0.9em;

  strong {
    color: #00d4ff;
  }
`;

const MetricValue = styled.span`
  color: #00ff88;
  font-weight: bold;
  font-family: monospace;
`;

export const PipelineVisualizer: React.FC = () => {
  const [currentStage, setCurrentStage] = useState(0);
  const [autoplay, setAutoplay] = useState(false);

  useEffect(() => {
    if (!autoplay) return;

    const timer = setTimeout(() => {
      if (currentStage < pipelineStages.length) {
        setCurrentStage((prev) => prev + 1);
      } else {
        setAutoplay(false);
      }
    }, 1500);

    return () => clearTimeout(timer);
  }, [autoplay, currentStage]);

  const handleReset = () => {
    setCurrentStage(0);
    setAutoplay(false);
  };

  const handleNext = () => {
    if (currentStage < pipelineStages.length) {
      setCurrentStage((prev) => prev + 1);
    }
  };

  const toggleAutoplay = () => {
    setAutoplay(!autoplay);
  };

  const progress = (currentStage / pipelineStages.length) * 100;

  return (
    <Container>
      <Header>
        <h1>🚀 8-Stage LLM Agent Pipeline</h1>
        <p>Real-time visualization of how LLM queries your codebase</p>
        <p style={{ fontSize: '0.9em', marginTop: '15px' }}>
          Question: "How does authentication work in this repository?"
        </p>
      </Header>

      <Controls>
        <Button onClick={handleNext} active={!autoplay}>
          ▶ Next Stage
        </Button>
        <Button onClick={handleReset}>↺ Reset</Button>
        <Button onClick={toggleAutoplay} active={autoplay}>
          {autoplay ? '⏸ Pause' : '▶ Auto-play'}
        </Button>
      </Controls>

      <ProgressBar>
        <ProgressFill progress={progress} />
      </ProgressBar>

      <Pipeline>
        {pipelineStages.map((stage, index) => (
          <React.Fragment key={stage.number}>
            <Stage active={index < currentStage} color={stage.color}>
              <StageHeader color={stage.color}>
                <StageNumber color={stage.color}>{stage.number}</StageNumber>
                <StageTitle>{stage.title}</StageTitle>
                <StageBadge color={stage.color}>{stage.badge}</StageBadge>
              </StageHeader>
              <StageContent>
                <DataSection>
                  <SectionLabel>{stage.input.label}</SectionLabel>
                  <DataBox>{stage.input.data}</DataBox>
                </DataSection>
                <DataSection>
                  <SectionLabel>{stage.output.label}</SectionLabel>
                  <DataBox>{stage.output.data}</DataBox>
                </DataSection>
                <Description>{stage.description}</Description>
              </StageContent>
            </Stage>
            {index < pipelineStages.length - 1 && <Arrow>↓</Arrow>}
          </React.Fragment>
        ))}
      </Pipeline>

      <FinalAnswer>
        <h2>✨ LLM's Comprehensive Answer</h2>
        <p>
          <strong>How Authentication Works in GitOnBoard:</strong>
        </p>

        <div
          style={{
            background: 'rgba(0, 0, 0, 0.3)',
            padding: '15px',
            borderRadius: '8px',
            fontFamily: 'monospace',
            textAlign: 'left',
            display: 'inline-block',
            margin: '15px 0',
          }}
        >
          <div>Request with JWT Token</div>
          <div>↓</div>
          <div>[Middleware extracts from Authorization header]</div>
          <div>↓</div>
          <div>[JWT verification: decode token using SECRET_KEY]</div>
          <div>↓</div>
          <div>[Extract user_id from token payload]</div>
          <div>↓</div>
          <div>[Database lookup: User.query.filter(User.id == user_id)]</div>
          <div>↓</div>
          <div>[FastAPI dependency injection into endpoint]</div>
          <div>↓</div>
          <div>✅ User object available to handler</div>
        </div>

        <p style={{ textAlign: 'left', display: 'inline-block', marginTop: '20px' }}>
          <strong>Key Components:</strong>
          <ul>
            <li>
              <strong>get_current_user()</strong> - Core authentication function in
              backend/dependencies/auth.py
            </li>
            <li>
              <strong>JWT Verification</strong> - Uses HS256 algorithm with SECRET_KEY
            </li>
            <li>
              <strong>Database Lookup</strong> - Validates token claims against User
              table
            </li>
            <li>
              <strong>FastAPI Integration</strong> - Automatic dependency injection
              via Depends()
            </li>
            <li>
              <strong>OAuth Support</strong> - GitHub OAuth provider for alternative
              auth
            </li>
            <li>
              <strong>Frontend State</strong> - AuthContext.tsx manages user session
            </li>
          </ul>
        </p>

        <MetricContainer>
          <Metric>
            <strong>Total Stages:</strong> <MetricValue>8</MetricValue>
          </Metric>
          <Metric>
            <strong>Tool Calls:</strong> <MetricValue>5</MetricValue>
          </Metric>
          <Metric>
            <strong>Time Taken:</strong> <MetricValue>&lt;2 sec</MetricValue>
          </Metric>
          <Metric>
            <strong>Data Size:</strong> <MetricValue>&lt;20 KB</MetricValue>
          </Metric>
          <Metric>
            <strong>vs Re-parse:</strong> <MetricValue>100x faster</MetricValue>
          </Metric>
        </MetricContainer>
      </FinalAnswer>
    </Container>
  );
};

export default PipelineVisualizer;
