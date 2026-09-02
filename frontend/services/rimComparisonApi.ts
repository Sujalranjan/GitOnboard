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
