/**
 * RIM Comparison Service - Frontend API wrapper for the comparison endpoint.
 */

import { fetchAPI, ApiError } from './api';

export interface RIMComparisonRequest {
  question: string;
}

export interface RetrievalMetrics {
  files_retrieved: number;
  symbols_retrieved: number;
  rim_relationships_count?: number;
  rim_discovered_files?: number;
  rim_discovered_symbols?: number;
  retrieval_latency_ms: number;
}

export interface LLMEfficiencyMetrics {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  context_size_chars: number;
  context_assembly_latency_ms: number;
  llm_latency_ms: number;
  total_latency_ms: number;
}

export interface AnswerMetrics {
  correctness: string | null;
  grounding: string | null;
  notes: string;
}

export interface ComparisonSide {
  answer: string;
  retrieval_metrics: RetrievalMetrics;
  llm_efficiency_metrics: LLMEfficiencyMetrics;
  answer_metrics: AnswerMetrics;
  retrieved_files: string[];
  retrieved_symbols: string[];
  context_block: string;
}

export interface ContextDiff {
  files_only_without_rim: string[];
  shared_files: string[];
  files_only_with_rim: string[];
}

export interface RIMExecutionTrace {
  query: string;
  baseline_candidates: Record<string, any>[];
  rim_seed_entities: Record<string, any>[];
  rim_relationships_traversed: Record<string, any>[];
  rim_discovered_entities: Record<string, any>[];
  files_added_by_rim: string[];

  context_without_rim: string;
  context_with_rim: string;

  llm_input_without_rim: Array<{ role: string; content: string }>;
  llm_input_with_rim: Array<{ role: string; content: string }>;

  llm_output_without_rim: string;
  llm_output_with_rim: string;

  token_usage_without_rim: { [key: string]: number } | null;
  token_usage_with_rim: { [key: string]: number } | null;

  latency_without_rim_ms: { [key: string]: number };
  latency_with_rim_ms: { [key: string]: number };
}

export interface RIMComparisonResponse {
  without_rim: ComparisonSide;
  with_rim: ComparisonSide;

  repository: string;
  branch: string | null;
  commit: string | null;
  analysis_id: number | null;

  context_diff: ContextDiff;
  trace: RIMExecutionTrace;
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
