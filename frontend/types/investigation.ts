export interface AgentInfo {
  agent_id: string;
  role: string;
  model: string;
  provider: string;
  is_local: boolean;
  status: 'pending' | 'queued' | 'running' | 'waiting' | 'completed' | 'failed' | 'blocked' | 'cancelled';
  current_task?: string;
  task_id?: string;
  acceptance_criteria?: string;
  summary?: string;
  tool_calls_count?: number;
  tokens_used?: number;
  last_active?: string;
  temperature?: number;
  max_tokens?: number;
}

export interface TaskItem {
  id: string;
  title: string;
  description: string;
  target_entities?: string[];
  expected_output?: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'BLOCKED';
  dependencies?: string[];
  assigned_agent?: string;
  findings_count?: number;
  files_inspected?: string[];
  reason_failed?: string;
}

export interface FindingItem {
  id: string;
  task_id: string;
  file_path: string;
  line_start?: number | null;
  line_end?: number | null;
  symbol_name?: string | null;
  finding_type: string;
  summary: string;
  code_excerpt?: string | null;
  confidence: number;
}

export interface ToolActivityItem {
  id?: string;
  timestamp: number;
  agent_id?: string;
  task_id?: string;
  tool_name: string;
  arguments?: Record<string, any>;
  success?: boolean;
  result_summary?: any;
  duration_ms?: number;
  formatted_time?: string;
}

export interface TimelineEvent {
  id: string;
  timestamp: number;
  formatted_time: string;
  agent_id?: string;
  type: 
    | 'investigation-start'
    | 'agent-spawn'
    | 'agent-update'
    | 'plan-created'
    | 'task-update'
    | 'task-discovered'
    | 'tool-call'
    | 'tool-response'
    | 'finding-saved'
    | 'memory-update'
    | 'final-answer'
    | 'completed'
    | 'error'
    | 'status';
  title: string;
  description?: string;
  status?: 'running' | 'completed' | 'failed' | 'pending';
  tool_call_id?: string;
  tool_name?: string;
  arguments?: Record<string, any>;
  result_summary?: any;
  success?: boolean;
  error?: any;
  duration_s?: number;
  file_path?: string;
  line_start?: number | null;
  line_end?: number | null;
  code_excerpt?: string | null;
  finding?: FindingItem;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  plan?: TaskItem[];
  findings?: FindingItem[];
  isStreaming?: boolean;
}
