"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useTaskStatus } from '../hooks/useTaskStatus';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MermaidViewer } from './common/MermaidViewer';
import {
  Code,
  FileCode2,
  Copy,
  Check,
  Sparkles,
  GitBranch,
  RefreshCw,
  XCircle,
  AlertCircle,
  Cpu,
  Layers,
  Terminal,
  Server
} from 'lucide-react';

/**
 * Custom CodeBlock component with copy-to-clipboard functionality
 * and clean syntax styling.
 */
function CodeBlock({ className, children }) {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const lang = match ? match[1] : '';
  const text = String(children || '').replace(/\n$/, '');

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error('Failed to copy code', e);
    }
  };

  return (
    <div className="relative group my-4 rounded-xl overflow-hidden border border-slate-700/60 dark:border-slate-800 bg-slate-900 shadow-md">
      <div className="flex items-center justify-between px-4 py-2 bg-slate-950/80 border-b border-slate-800/80 text-xs font-mono text-slate-400">
        <div className="flex items-center gap-1.5">
          <Terminal className="w-3.5 h-3.5 text-slate-400" />
          <span>{lang || 'code'}</span>
        </div>
        <button
          onClick={handleCopy}
          type="button"
          aria-label="Copy code"
          className="flex items-center gap-1.5 px-2 py-0.5 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition-colors text-xs"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400 font-medium">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <div className="p-4 overflow-x-auto text-xs font-mono text-slate-100 dark:text-slate-200 leading-relaxed">
        <pre className="!m-0 !p-0 !bg-transparent !border-none">
          <code>{text}</code>
        </pre>
      </div>
    </div>
  );
}

/**
 * Enhanced Markdown Component mapping for clean hierarchy, responsive tables,
 * alerts, and Mermaid diagram rendering.
 */
const summaryMarkdownComponents = {
  h1: ({ children }) => (
    <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 pb-3 border-b border-slate-200/80 dark:border-slate-800/80 mb-6 flex items-center gap-2">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-lg sm:text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100 mt-8 mb-3 pb-2 border-b border-slate-100 dark:border-slate-800/50 flex items-center gap-2">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base sm:text-lg font-semibold text-slate-800 dark:text-slate-200 mt-5 mb-2">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="text-slate-700 dark:text-slate-300 leading-relaxed text-sm my-3">
      {children}
    </p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc list-outside ml-5 space-y-1.5 text-sm text-slate-700 dark:text-slate-300 my-3">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal list-outside ml-5 space-y-1.5 text-sm text-slate-700 dark:text-slate-300 my-3">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="leading-relaxed">
      {children}
    </li>
  ),
  pre: ({ children }) => {
    const childProps = children?.props;
    const className = childProps?.className || '';
    const rawCode = String(childProps?.children || '').trim();
    const isMermaid =
      className.includes('language-mermaid') ||
      /^graph\s+/i.test(rawCode) ||
      /^flowchart\s+/i.test(rawCode) ||
      /^sequenceDiagram/i.test(rawCode) ||
      /^classDiagram/i.test(rawCode) ||
      /^erDiagram/i.test(rawCode) ||
      /^stateDiagram/i.test(rawCode);

    if (isMermaid) {
      return <>{children}</>;
    }
    return <CodeBlock className={className}>{childProps?.children}</CodeBlock>;
  },
  code: ({ className, children, ...props }) => {
    const match = /language-(\w+)/.exec(className || '');
    const codeString = String(children).replace(/\n$/, '').trim();
    const isMermaid =
      (match && match[1]?.toLowerCase() === 'mermaid') ||
      /^graph\s+/i.test(codeString) ||
      /^flowchart\s+/i.test(codeString) ||
      /^sequenceDiagram/i.test(codeString) ||
      /^classDiagram/i.test(codeString) ||
      /^erDiagram/i.test(codeString) ||
      /^stateDiagram/i.test(codeString);

    if (isMermaid) {
      return (
        <div className="my-6 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white/50 dark:bg-slate-900/40 p-4 shadow-sm backdrop-blur-sm overflow-x-auto">
          <MermaidViewer chart={codeString} />
        </div>
      );
    }

    const isMultiline = String(children).includes('\n');
    if (!isMultiline) {
      return (
        <code
          className="font-mono text-xs px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700/80 font-medium"
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code className="block whitespace-pre font-mono text-xs" {...props}>
        {children}
      </code>
    );
  },
  table: ({ children }) => (
    <div className="overflow-x-auto max-w-full my-4 border border-slate-200/80 dark:border-slate-700/80 rounded-xl overflow-hidden glass-panel-subtle shadow-sm">
      <table className="w-full text-xs font-mono border-collapse divide-y divide-slate-200 dark:divide-slate-700">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-slate-100/80 dark:bg-slate-800/80 text-slate-800 dark:text-slate-200 font-semibold">
      {children}
    </thead>
  ),
  th: ({ children }) => (
    <th className="px-4 py-2.5 text-left font-semibold border-b border-slate-200 dark:border-slate-700">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-4 py-2 text-slate-700 dark:text-slate-300 border-b border-slate-100 dark:border-slate-800/50">
      {children}
    </td>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-amber-500/80 bg-amber-50/50 dark:bg-amber-950/20 px-4 py-2.5 my-4 rounded-r-lg text-sm text-slate-700 dark:text-slate-300 break-words shadow-xs">
      {children}
    </blockquote>
  ),
};

export default function RepositorySummary({ repoName }) {
  const [summary, setSummary] = useState(null);
  const [meta, setMeta] = useState(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const taskStatus = useTaskStatus(repoName, 'summary');
  const [localIsGenerating, setLocalIsGenerating] = useState(false);
  const isGenerating = taskStatus === 'processing' || localIsGenerating;
  const [isOutdated, setIsOutdated] = useState(false);
  const [error, setError] = useState(null);
  const [isCancelling, setIsCancelling] = useState(false);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch(`/api/repos/${repoName}/summary`);
      if (res.status === 404) {
        setInitialLoading(false);
        return;
      }
      if (!res.ok) throw new Error("Failed to fetch summary");
      const data = await res.json();
      if (data.summary) {
        setSummary(typeof data.summary === 'string' ? data.summary : JSON.stringify(data.summary, null, 2));
        setIsOutdated(Boolean(data.outdated));
      }
      if (data.metadata) {
        setMeta(data.metadata);
      }
      if (data.status === 'completed' || data.status === 'idle') {
        setLocalIsGenerating(false);
        setIsCancelling(false);
      } else if (data.status === 'cancelled') {
        setLocalIsGenerating(false);
        setIsCancelling(false);
      } else if (data.status === 'failed') {
        setLocalIsGenerating(false);
        setIsCancelling(false);
        setError("Summary generation failed to complete. You can try again or view the static summary.");
      }
    } catch (err) {
      if (!err.message?.includes("Failed to fetch summary")) {
        console.error("fetchSummary error:", err);
      }
    } finally {
      setInitialLoading(false);
    }
  }, [repoName]);

  // Initial fetch on mount / repoName change
  useEffect(() => {
    setInitialLoading(true);
    fetchSummary();
  }, [fetchSummary]);

  // Handle SSE push task status updates
  const prevTaskStatus = useRef(taskStatus);
  useEffect(() => {
    if (taskStatus === 'completed') {
      setLocalIsGenerating(false);
      setIsCancelling(false);
      fetchSummary();
    } else if (taskStatus === 'failed') {
      setLocalIsGenerating(false);
      setIsCancelling(false);
      fetchSummary();
      setError("Summary generation failed. A static fallback has been provided if available.");
    } else if (taskStatus === 'cancelled') {
      setLocalIsGenerating(false);
      setIsCancelling(false);
      fetchSummary();
    } else if (taskStatus === 'processing') {
      setLocalIsGenerating(true);
    } else if (taskStatus === 'idle' || taskStatus === null) {
      if (prevTaskStatus.current === 'processing') {
        fetchSummary();
      }
    }
    prevTaskStatus.current = taskStatus;
  }, [taskStatus, fetchSummary]);

  // Active polling fallback while generating (guarantees recovery if SSE drops during long LLM runs)
  useEffect(() => {
    if (!isGenerating) return;

    const interval = setInterval(() => {
      fetchSummary();
    }, 3000);

    return () => clearInterval(interval);
  }, [isGenerating, fetchSummary]);

  const generateSummary = async () => {
    setError(null);
    setLocalIsGenerating(true);
    setIsCancelling(false);
    try {
      const res = await fetch(`/api/repos/${repoName}/summary/generate`, {
        method: 'POST'
      });
      if (!res.ok) throw new Error("Failed to start summary generation");
      const data = await res.json();
      if (data.summary) {
        setSummary(typeof data.summary === 'string' ? data.summary : JSON.stringify(data.summary, null, 2));
        setLocalIsGenerating(false);
      }
      setIsOutdated(false);
    } catch (err) {
      setError(err.message);
      setLocalIsGenerating(false);
    }
  };

  const cancelSummary = async () => {
    setIsCancelling(true);
    try {
      const res = await fetch(`/api/repos/${repoName}/summary/cancel`, {
        method: 'POST'
      });
      if (!res.ok) throw new Error("Failed to cancel summary generation");
      setLocalIsGenerating(false);
      await fetchSummary();
    } catch (err) {
      console.error("Cancel summary error:", err);
      setLocalIsGenerating(false);
    } finally {
      setIsCancelling(false);
    }
  };

  // 1. Initial component loading state
  if (initialLoading && !summary) {
    return (
      <div className="h-full flex flex-col items-center justify-center glass-panel rounded-xl p-12 text-slate-900 dark:text-slate-100">
        <RefreshCw className="animate-spin h-10 w-10 text-violet-500 mb-4" />
        <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Loading repository summary...</p>
      </div>
    );
  }

  // 2. Generating state when no summary exists yet
  if (isGenerating && !summary) {
    return (
      <div className="h-full flex flex-col items-center justify-center glass-panel rounded-xl p-12 text-slate-900 dark:text-slate-100">
        <div className="w-16 h-16 rounded-2xl bg-violet-100 dark:bg-violet-950/60 border border-violet-200 dark:border-violet-800 flex items-center justify-center mb-6 shadow-sm">
          <RefreshCw className="animate-spin h-8 w-8 text-violet-600 dark:text-violet-400" />
        </div>
        <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">Generating AI Summary...</h3>
        <p className="text-slate-500 dark:text-slate-400 mt-2 text-center max-w-md text-sm">
          The local LLM is synthesizing the repository metadata and verified documentation. This runs locally and will update automatically once complete.
        </p>
        
        <div className="flex items-center gap-3 mt-6">
          <button
            onClick={cancelSummary}
            disabled={isCancelling}
            className="px-4 py-2 text-xs font-semibold rounded-lg border border-rose-300 dark:border-rose-800/60 bg-rose-50/80 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 hover:bg-rose-100 dark:hover:bg-rose-900/50 transition-colors shadow-xs disabled:opacity-50"
          >
            {isCancelling ? "Cancelling..." : "Cancel Generation"}
          </button>
          <button
            onClick={fetchSummary}
            className="px-4 py-2 text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 underline"
          >
            Check status now
          </button>
        </div>
      </div>
    );
  }

  // 3. No summary available yet
  if (!summary) {
    return (
      <div className="h-full flex flex-col items-center justify-center glass-panel rounded-xl p-12 text-slate-900 dark:text-slate-100">
        <div className="w-16 h-16 rounded-2xl bg-indigo-50 dark:bg-indigo-950/50 border border-indigo-200/60 dark:border-indigo-800/60 flex items-center justify-center mb-5 shadow-xs">
          <Sparkles className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />
        </div>
        <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">No Summary Available</h3>
        <p className="text-slate-500 dark:text-slate-400 mb-6 text-center max-w-md text-sm">
          Generate an AI-powered, grounded summary of the repository architecture, key modules, and operational flows using verified facts and local Ollama.
        </p>
        <button
          onClick={generateSummary}
          className="px-6 py-2.5 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-medium rounded-lg shadow-md shadow-violet-500/25 transition-all flex items-center gap-2 text-sm"
        >
          <Sparkles className="w-4 h-4" />
          Generate Summary
        </button>
        {error && (
          <div className="mt-4 p-3 max-w-md rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>
    );
  }

  const displayName = meta?.display_name || repoName;
  const primaryLang = meta?.primary_language && meta.primary_language !== "Unknown" ? meta.primary_language : null;
  const allLanguages = (meta?.languages || []).filter(l => l && l !== primaryLang).slice(0, 5);

  // 4. Summary is available and rendered
  return (
    <div className="h-full flex flex-col glass-panel rounded-xl relative overflow-hidden text-slate-900 dark:text-slate-100">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 sm:px-6 border-b border-slate-200/60 dark:border-slate-800/60 glass-nav">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-3">
            <span className="text-2xl">📝</span>
            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
              Repository Overview
            </h2>
            {isOutdated && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 dark:bg-amber-950/80 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60">
                Outdated
              </span>
            )}
            {isGenerating && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 dark:bg-blue-950/80 text-blue-800 dark:text-blue-300 animate-pulse border border-blue-200 dark:border-blue-800/60">
                <RefreshCw className="animate-spin h-3 w-3 text-blue-600 dark:text-blue-400" />
                Updating in background...
              </span>
            )}
          </div>

          {/* Compact Quick Metadata Strip */}
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span className="font-semibold text-slate-700 dark:text-slate-300">
              {displayName}
            </span>
            {primaryLang && (
              <>
                <span>•</span>
                <span className="px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/50 text-blue-700 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/50 font-medium">
                  {primaryLang}
                </span>
              </>
            )}
            {allLanguages.map((lang) => (
              <span
                key={lang}
                className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-[11px]"
              >
                {lang}
              </span>
            ))}
            {meta?.routes_count > 0 && (
              <>
                <span>•</span>
                <span className="flex items-center gap-1 text-slate-600 dark:text-slate-300">
                  <Layers className="w-3.5 h-3.5 text-slate-400" />
                  {meta.routes_count} API route{meta.routes_count > 1 ? 's' : ''}
                </span>
              </>
            )}
            {meta?.total_files > 0 && (
              <>
                <span>•</span>
                <span>{meta.total_files} files</span>
              </>
            )}
          </div>
        </div>
        
        {/* Actions */}
        <div className="flex items-center gap-2 self-start sm:self-center shrink-0">
          {isGenerating && (
            <button
              onClick={cancelSummary}
              disabled={isCancelling}
              className="px-3 py-1.5 bg-rose-50 dark:bg-rose-950/40 border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 hover:bg-rose-100 dark:hover:bg-rose-900/50 text-xs font-semibold rounded-md shadow-xs transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              <XCircle className="w-3.5 h-3.5" />
              {isCancelling ? "Cancelling..." : "Cancel"}
            </button>
          )}

          <button
            onClick={generateSummary}
            disabled={isGenerating}
            className="px-3.5 py-1.5 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/80 text-slate-700 dark:text-slate-200 text-xs font-semibold rounded-md shadow-xs transition-colors flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isGenerating ? 'animate-spin text-blue-600' : ''}`} />
            {isOutdated ? "Update Summary" : isGenerating ? "Regenerating..." : "Regenerate"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center justify-between gap-2 shadow-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-rose-500 hover:text-rose-700 dark:hover:text-rose-200 text-xs underline ml-2">
            Dismiss
          </button>
        </div>
      )}
      
      {/* Markdown Content */}
      <div className="flex-grow overflow-y-auto p-6 sm:p-8 max-w-none">
        <div className="max-w-4xl mx-auto">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={summaryMarkdownComponents}
          >
            {summary}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
