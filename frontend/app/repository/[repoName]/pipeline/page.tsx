"use client";

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import LoadingSpinner from '@/components/LoadingSpinner';

interface StageResult {
  status: string;
  time: number;
  details?: Record<string, any>;
  error?: string;
}

interface PipelineResponse {
  query: string;
  repository_id: number;
  stages: Record<string, StageResult>;
  total_time: number;
}

const STAGE_DESCRIPTIONS: Record<number, string> = {
  1: "Parse & Analyze - Scan repository and extract entities/relationships",
  2: "FactStore Persistence - Save model to database",
  3: "BM25 Indexing - Build keyword search index",
  4: "Semantic Indexing - Build embedding index (optional)",
  5: "Hybrid Retrieval - Find relevant files and symbols",
  6: "Graph Navigation - Expand from retrieval results via relationships",
  7: "Context Assembly - Select budgeted evidence",
  8: "LLM Grounding - Validate answer against evidence",
};

export default function PipelinePage() {
  const params = useParams();
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  const repoName = params.repoName as string;

  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [isExecuting, setIsExecuting] = useState(false);
  const [result, setResult] = useState<PipelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!isAuthenticated) {
      router.replace("/");
    }
  }, [authLoading, isAuthenticated, router]);

  const handleExecutePipeline = async () => {
    if (!query.trim()) {
      setError("Please enter a query");
      return;
    }

    setIsExecuting(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}/api/repos/${repoName}/pipeline/query`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${localStorage.getItem("token") || ""}`,
          },
          body: JSON.stringify({
            query,
            top_k: topK,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Pipeline execution failed");
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError((err as Error).message || "Failed to execute pipeline");
    } finally {
      setIsExecuting(false);
    }
  };

  const getStatusIcon = (status: string) => {
    if (status === "PASS") return "✓";
    if (status === "FAIL") return "✗";
    if (status === "SKIPPED") return "⊘";
    return "?";
  };

  const getStatusColor = (status: string): string => {
    if (status === "PASS") return "text-green-600";
    if (status === "FAIL") return "text-red-600";
    if (status === "SKIPPED") return "text-yellow-600";
    return "text-slate-600";
  };

  const getStageNumber = (key: string): number => {
    const match = key.match(/stage_(\d+)/);
    return match ? parseInt(match[1]) : 0;
  };

  if (authLoading) {
    return <LoadingSpinner />;
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h1 className="text-3xl font-bold mb-2 text-slate-900">8-Stage Pipeline</h1>
      <p className="text-slate-600 mb-8">
        Execute the complete intelligence pipeline: Parse → Index → Retrieve → Graph → Context → Ground
      </p>

      {/* Query Input */}
      <div className="bg-white rounded-lg border border-slate-200 p-6 mb-8">
        <label className="block text-sm font-semibold text-slate-700 mb-3">
          Query
        </label>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g., Where is authentication implemented? How does the analysis engine work?"
          className="w-full px-4 py-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4"
          rows={3}
          disabled={isExecuting}
        />

        <div className="flex gap-4 items-end">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-2">
              Top K Results
            </label>
            <input
              type="number"
              value={topK}
              onChange={(e) => setTopK(Math.max(1, parseInt(e.target.value) || 5))}
              min="1"
              max="20"
              className="px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={isExecuting}
            />
          </div>

          <button
            onClick={handleExecutePipeline}
            disabled={isExecuting || !query.trim()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-slate-400 font-medium transition-colors"
          >
            {isExecuting ? "Executing..." : "Execute Pipeline"}
          </button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-8 text-red-700">
          <p className="font-semibold">Error</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6">
          <div className="bg-slate-50 rounded-lg border border-slate-200 p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-2">Query</h2>
            <p className="text-slate-700">{result.query}</p>
            <p className="text-sm text-slate-500 mt-3">
              Total execution time: <span className="font-mono font-semibold">{result.total_time.toFixed(2)}s</span>
            </p>
          </div>

          {/* Stages Results */}
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-900">Pipeline Stages</h2>
            {Object.entries(result.stages)
              .sort(([a], [b]) => getStageNumber(a) - getStageNumber(b))
              .map(([key, stage]) => {
                const stageNum = getStageNumber(key);
                const description = STAGE_DESCRIPTIONS[stageNum];

                return (
                  <div
                    key={key}
                    className="bg-white border border-slate-200 rounded-lg p-6 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex-1">
                        <h3 className="text-base font-semibold text-slate-900">
                          <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full mr-2 ${getStatusColor(stage.status)}`}>
                            {getStatusIcon(stage.status)}
                          </span>
                          Stage {stageNum}: {key.replace(/_/g, " ")}
                        </h3>
                        <p className="text-sm text-slate-600 mt-1">{description}</p>
                      </div>
                      <div className="text-right ml-4">
                        <div className={`text-sm font-semibold ${getStatusColor(stage.status)}`}>
                          {stage.status}
                        </div>
                        <div className="text-xs text-slate-500 font-mono mt-1">
                          {stage.time.toFixed(3)}s
                        </div>
                      </div>
                    </div>

                    {/* Details */}
                    {stage.details && (
                      <div className="mt-4 bg-slate-50 rounded p-4 text-sm">
                        <div className="space-y-1">
                          {Object.entries(stage.details).map(([key, value]) => (
                            <div key={key} className="flex justify-between text-slate-700">
                              <span className="font-mono text-slate-600">{key}:</span>
                              <span className="font-semibold">
                                {typeof value === "object"
                                  ? JSON.stringify(value)
                                  : String(value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Error */}
                    {stage.error && (
                      <div className="mt-3 bg-red-50 border border-red-200 rounded p-3 text-xs text-red-700">
                        <p className="font-semibold">Error</p>
                        <p className="font-mono">{stage.error}</p>
                      </div>
                    )}
                  </div>
                );
              })}
          </div>

          {/* Summary */}
          <div className="bg-green-50 border border-green-200 rounded-lg p-6 mt-8">
            <h3 className="font-semibold text-green-900 mb-2">Pipeline Complete</h3>
            <p className="text-sm text-green-800">
              All stages executed successfully in {result.total_time.toFixed(2)} seconds
            </p>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isExecuting && (
        <div className="flex flex-col items-center justify-center py-12">
          <LoadingSpinner />
          <p className="mt-4 text-slate-600">Executing pipeline stages...</p>
        </div>
      )}
    </div>
  );
}
