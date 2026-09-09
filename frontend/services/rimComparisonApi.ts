/**
 * RIM Comparison Service - Frontend API wrapper for the comparison endpoint.
 */

import { fetchAPI, ApiError } from './api';

export interface RIMComparisonRequest {
  question: string;
}

export interface RetrievalMetrics {
  tool_call_count: number;
  files_retrieved: number;
  symbols_retrieved: number;
  rim_entities_accessed_count: number;
  rim_relationship_types_used: string[];
  retrieval_latency_ms: number;
}

export interface LLMEfficiencyMetrics {
  provider: string;
  model: string;
  actual_prompt_tokens: number;
  actual_completion_tokens: number;
  actual_total_tokens: number;
  estimated_system_tokens: number;
  estimated_rim_tokens: number;
  estimated_source_tokens: number;
  estimated_other_tokens: number;
  token_estimation_method: string;
  token_estimation_is_approximate: boolean;
  token_reconciliation_diff: number;
  llm_latency_ms: number;
  retrieval_latency_ms: number;
  token_counting_latency_ms: number;
  total_latency_ms: number;
}

export interface AnswerMetrics {
  correctness: string | null;
  grounding: string | null;
  notes: string;
}

export interface ToolCallTranscript {
  turn: number;
  tool_name: string;
  arguments: Record<string, unknown>;
  observation_summary: string;
}

export interface ComparisonSide {
  answer: string;
  retrieval_metrics: RetrievalMetrics;
  llm_efficiency_metrics: LLMEfficiencyMetrics;
  answer_metrics: AnswerMetrics;
  rim_metadata_block: string | null;
  source_context_block: string;
  tool_call_transcript: ToolCallTranscript[];
  stop_reason: string;
}

export interface ContextDiff {
  files_only_without_rim: string[];
  shared_files: string[];
  files_only_with_rim: string[];
}

export interface RIMTrace {
  rim_metadata_seed_entities: Record<string, unknown>[];
  rim_metadata_relationships: Record<string, unknown>[];
  query_rim_call_log: Record<string, unknown>[];
}

export interface RIMComparisonResponse {
  without_rim: ComparisonSide;
  with_rim: ComparisonSide;

  repository: string;
  branch: string | null;
  commit: string | null;
  analysis_id: number | null;

  context_diff: ContextDiff;
  trace: RIMTrace;
}

/**
 * Stream LLM analysis for RIM comparison.
 * Filters to only show final-answer messages.
 */
export async function streamRimAnalysis(
  repoHash: string,
  question: string,
  onMessage: (type: string, content: string) => void,
  onError: (error: string) => void
): Promise<void> {
  try {
    const response = await fetch('/api/llm/analyze/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: question,
        repo_hash: repoHash,
        model: localStorage.getItem('selectedModel') || 'qwen3:4b-instruct',
        show_tool_details: false,
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

            if (data.type === 'final-answer') {
              onMessage('final-answer', data.content);
            } else if (data.type === 'error') {
              onError(`Error: ${data.content}`);
            }
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }
      }
    }
  } catch (error) {
    onError(error instanceof Error ? error.message : 'Failed to analyze query');
  }
}

export async function streamRimComparison(
  repoName: string,
  question: string,
  onWithoutRim: (result: ComparisonSide) => void,
  onWithRim: (result: ComparisonSide, metricsDiff: Record<string, any>) => void,
  onError: (error: string) => void
): Promise<void> {
  try {
    const response = await fetch(`/api/repos/${encodeURIComponent(repoName)}/rim-comparison/compare-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    if (!response.ok) {
      throw new Error(`Failed to compare: ${response.statusText}`);
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

            if (data.type === 'without_rim_complete' && data.without_rim) {
              onWithoutRim(data.without_rim);
            } else if (data.type === 'with_rim_complete' && data.with_rim) {
              onWithRim(data.with_rim, data.metrics_diff || {});
            } else if (data.type === 'error') {
              onError(`Error: ${data.content}`);
            }
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }
      }
    }
  } catch (error) {
    onError(error instanceof Error ? error.message : 'Failed to run comparison');
  }
}

export async function compareRimVsBaseline(
  repoName: string,
  question: string
): Promise<RIMComparisonResponse> {
  const response = await fetchAPI(`/repos/${encodeURIComponent(repoName)}/rim-comparison/compare`, {
    method: 'POST',
    body: JSON.stringify({ question })
  });

  return response as RIMComparisonResponse;
}
