'use client';

import React, { useState, useCallback, useEffect } from 'react';
import { useParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { streamRimAnalysis } from '@/services/rimComparisonApi';
import { Card, CardHeader } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Loader2, Send } from 'lucide-react';

interface ComparisonResult {
  question: string;
  withRimAnswer: string;
  timestamp: number;
}

export default function RIMComparisonPage() {
  const params = useParams();
  const repoName = params?.repoName as string;

  const [question, setQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<ComparisonResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [repoHash, setRepoHash] = useState<string | null>(null);

  // Look up repo hash from repo name
  useEffect(() => {
    const lookupRepoHash = async () => {
      try {
        const response = await fetch(`/api/repos/lookup-hash?name=${encodeURIComponent(repoName)}`);
        if (response.ok) {
          const data = await response.json();
          if (data.repository_hash) {
            setRepoHash(data.repository_hash);
          }
        }
      } catch (error) {
        console.error('Failed to look up repository hash:', error);
      }
    };

    if (repoName) {
      lookupRepoHash();
    }
  }, [repoName]);

  const handleAnalyze = useCallback(async () => {
    if (!question.trim()) {
      setError('Please enter a question');
      return;
    }

    if (!repoHash) {
      setError('Repository information not available');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      let withRimAnswer = '';

      await streamRimAnalysis(
        repoHash,
        question,
        (type: string, content: string) => {
          if (type === 'final-answer') {
            withRimAnswer = content;
          }
        },
        (errorMsg: string) => {
          setError(errorMsg);
        }
      );

      if (withRimAnswer) {
        const newResult: ComparisonResult = {
          question,
          withRimAnswer,
          timestamp: Date.now(),
        };
        setResults([newResult, ...results]);
        setQuestion('');
      }
    } catch (err: any) {
      setError(err.message || 'Analysis failed. Please try again.');
      console.error('Analysis error:', err);
    } finally {
      setIsLoading(false);
    }
  }, [question, repoHash, results]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      handleAnalyze();
    }
  };

  const handleNewAnalysis = useCallback(() => {
    setQuestion('');
    setError(null);
  }, []);

  return (
    <div className="flex-1 overflow-y-auto bg-white dark:bg-slate-950 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-slate-900 dark:text-slate-100 mb-2">RIM Comparison</h1>
          <p className="text-slate-600 dark:text-slate-400">
            Compare repository-aware answers using LLM Conversation Flow with RIM enhancement.
          </p>
        </div>

        {/* Query Input */}
        <Card className="mb-8">
          <div className="p-6">
            <label className="block text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">
              Research Question
            </label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about this repository..."
              disabled={isLoading}
              className="w-full px-4 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4 disabled:opacity-50"
              rows={3}
            />

            <div className="flex items-center justify-between">
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Tip: Ctrl+Enter to submit
              </div>
              <Button
                onClick={handleAnalyze}
                disabled={isLoading || !question.trim() || !repoHash}
                className="flex items-center gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    Compare
                  </>
                )}
              </Button>
            </div>
          </div>
        </Card>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-50 dark:bg-red-950 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-800">
            {error}
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div className="grid grid-cols-2 gap-6 mb-8">
            <Card>
              <CardHeader title="WITHOUT RIM" subtitle="Standard Retrieval" />
              <div className="p-12">
                <div className="flex flex-col items-center justify-center">
                  <Loader2 className="w-12 h-12 animate-spin text-blue-600 dark:text-blue-400 mb-4" />
                  <p className="text-slate-600 dark:text-slate-400">Processing...</p>
                </div>
              </div>
            </Card>

            <Card>
              <CardHeader title="WITH RIM" subtitle="RIM-Enhanced Retrieval" />
              <div className="p-12">
                <div className="flex flex-col items-center justify-center">
                  <Loader2 className="w-12 h-12 animate-spin text-blue-600 dark:text-blue-400 mb-4" />
                  <p className="text-slate-600 dark:text-slate-400">Processing...</p>
                </div>
              </div>
            </Card>
          </div>
        )}

        {/* Results */}
        {results.map((result, idx) => (
          <div key={result.timestamp} className="mb-12">
            <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">
              Test {results.length - idx}: {result.question}
            </h2>

            <div className="grid grid-cols-2 gap-6 mb-8">
              {/* WITHOUT RIM (Placeholder) */}
              <Card>
                <CardHeader title="WITHOUT RIM" subtitle="Standard Retrieval" />
                <div className="p-6">
                  <div className="text-slate-500 dark:text-slate-400 italic text-sm">
                    <p className="mb-2">This page now uses LLM Conversation Flow for unified analysis.</p>
                    <p>The comparison requires the detailed RIM comparison endpoint.</p>
                  </div>
                </div>
              </Card>

              {/* WITH RIM */}
              <Card>
                <CardHeader title="WITH RIM" subtitle="RIM-Enhanced Retrieval" />
                <div className="p-6 space-y-4">
                  <div>
                    <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-2">Answer</h4>
                    <div className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed prose dark:prose-invert prose-sm max-w-none">
                      <ReactMarkdown
                        components={{
                          p: (props) => <p className="mb-3" {...props} />,
                          h1: (props) => <h1 className="text-lg font-bold mb-2" {...props} />,
                          h2: (props) => <h2 className="text-base font-bold mb-2" {...props} />,
                          h3: (props) => <h3 className="text-sm font-bold mb-2" {...props} />,
                          ul: (props) => <ul className="list-disc list-inside mb-3 space-y-1" {...props} />,
                          ol: (props) => <ol className="list-decimal list-inside mb-3 space-y-1" {...props} />,
                          li: (props) => <li className="mb-1" {...props} />,
                          code: (props: any) => props.inline
                            ? <code className="bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded text-xs font-mono" {...props} />
                            : <code className="bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded text-xs font-mono block mb-2 overflow-x-auto" {...props} />,
                          pre: (props) => <pre className="bg-slate-900 text-slate-100 p-3 rounded mb-3 overflow-x-auto text-xs" {...props} />,
                          blockquote: (props) => <blockquote className="border-l-4 border-slate-300 dark:border-slate-600 pl-3 italic text-slate-600 dark:text-slate-400 mb-3" {...props} />,
                          a: (props) => <a className="text-blue-600 dark:text-blue-400 underline" {...props} />,
                        }}
                      >
                        {result.withRimAnswer}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        ))}

        {/* New Analysis Button */}
        {results.length > 0 && (
          <div className="mt-8 text-center">
            <Button onClick={handleNewAnalysis} variant="secondary">
              + New Comparison
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
