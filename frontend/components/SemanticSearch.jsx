"use client";

import React, { useState, useEffect } from 'react';
import { useTaskStatus } from '../hooks/useTaskStatus';

export default function SemanticSearch({ repoName }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  
  const [indexState, setIndexState] = useState('checking');
  const [indexMessage, setIndexMessage] = useState("");
  const taskStatus = useTaskStatus(repoName, 'semantic_index');
  
  useEffect(() => {
    if (taskStatus === 'processing') {
      setIndexState('building');
      setIndexMessage('Building the semantic index... This may take a moment.');
    } else if (taskStatus === 'completed' && indexState === 'building') {
      setIndexState('ready');
      setIndexMessage('Semantic index up to date.');
      setTimeout(() => setIndexMessage(''), 4000);
    }
  }, [taskStatus, indexState]);
  
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    
    const buildIndex = async () => {
      setError(null);
      
      try {
        const statusRes = await fetch(`/api/repos/${repoName}/semantic-status`);
        if (!statusRes.ok) throw new Error("Failed to check index status");
        const statusData = await statusRes.json();
        
        if (isMounted) {
          if (statusData.has_index) {
            setIndexState('updating');
            setIndexMessage("Checking for changed files to incrementally update the semantic index...");
          } else {
            setIndexState('building');
            setIndexMessage("Building the semantic index for the first time. This may take a moment.");
          }
        }
        
        const res = await fetch(`/api/repos/${repoName}/semantic-index`, {
          method: 'POST'
        });
        
        if (!res.ok) {
          throw new Error("Failed to build semantic index");
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message);
          setIndexState('ready');
        }
      }
    };
    
    buildIndex();
    
    return () => {
      isMounted = false;
    };
  }, [repoName]);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setError(null);
    setHasSearched(true);

    try {
      const res = await fetch(`/api/repos/${repoName}/semantic-search?q=${encodeURIComponent(query)}`);
      if (!res.ok) {
        throw new Error("Semantic search failed");
      }
      const data = await res.json();
      setResults(data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSearching(false);
    }
  };

  if (indexState === 'checking' || indexState === 'building' || indexState === 'updating') {
    return (
      <div className="h-full flex flex-col items-center justify-center text-gray-500 dark:text-slate-400 bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-gray-200 dark:border-slate-800 p-8">
        <svg className="animate-spin h-10 w-10 text-purple-500 dark:text-purple-400 mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <p className="font-semibold text-lg text-slate-900 dark:text-slate-100">
          {indexState === 'checking' && "Checking Index Status..."}
          {indexState === 'building' && "Building Semantic Index"}
          {indexState === 'updating' && "Updating Changed Files"}
        </p>
        <p className="text-sm mt-2 max-w-sm text-center text-slate-500 dark:text-slate-400">{indexMessage}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-purple-50/30 dark:bg-slate-950 rounded-lg shadow-sm border border-purple-100 dark:border-slate-800 overflow-hidden relative text-slate-900 dark:text-slate-100">
      
      {/* Status Toast */}
      {indexMessage && (
        <div className="absolute top-4 right-4 z-50 bg-green-50 dark:bg-green-950/80 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-300 px-4 py-3 rounded shadow-sm text-sm font-medium animate-fade-in-down">
          <div className="flex items-center gap-2">
            <span className="text-green-500 dark:text-green-400">✓</span>
            {indexMessage}
          </div>
        </div>
      )}
      
      {/* Search Header */}
      <div className="p-6 bg-white dark:bg-slate-900 border-b border-purple-100 dark:border-slate-800 shadow-sm z-10">
        <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-2 flex items-center gap-2">
          <span className="text-2xl">✨</span> Semantic Search
        </h2>
        <p className="text-sm text-gray-500 dark:text-slate-400 mb-4">Search by concepts and natural language instead of exact keywords.</p>
        
        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="relative flex-grow">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <span className="text-purple-400 dark:text-purple-400 font-bold font-mono">?</span>
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="block w-full pl-10 pr-3 py-3 border border-purple-200 dark:border-slate-700 rounded-md leading-5 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:placeholder-gray-300 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 sm:text-sm transition duration-150 ease-in-out shadow-inner"
              placeholder="e.g. 'handle user login' or 'JWT authentication'"
            />
          </div>
          <button
            type="submit"
            disabled={isSearching || !query.trim()}
            className="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-purple-600 dark:bg-purple-600 hover:bg-purple-700 dark:hover:bg-purple-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:bg-purple-400 transition duration-150 ease-in-out"
          >
            {isSearching ? 'Searching...' : 'Ask AI'}
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>
      
      {/* Search Results */}
      <div className="flex-grow overflow-y-auto p-6 relative">
        <div className="absolute inset-0 pointer-events-none flex items-center justify-center opacity-[0.03] dark:opacity-[0.05]">
          <svg className="w-96 h-96" viewBox="0 0 100 100" fill="currentColor">
            <path d="M50 0L60.9789 39.0211L100 50L60.9789 60.9789L50 100L39.0211 60.9789L0 50L39.0211 39.0211L50 0Z" />
          </svg>
        </div>

        {!hasSearched ? (
          <div className="text-center py-12 relative z-10">
            <div className="mx-auto h-12 w-12 text-purple-200 dark:text-purple-400 text-5xl mb-4">🧠</div>
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-slate-200">Semantic AI Search</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">Enter a concept to discover related code using embeddings.</p>
          </div>
        ) : results.length === 0 ? (
          <div className="text-center py-12 bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-800 relative z-10">
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-slate-200">No results found</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">Try rephrasing your concept.</p>
          </div>
        ) : (
          <div className="space-y-4 relative z-10">
            <h3 className="text-sm font-medium text-gray-500 dark:text-slate-400">Found {results.length} semantic matche{results.length === 1 ? '' : 's'}</h3>
            <ul className="space-y-3">
              {results.map((result, idx) => (
                <li key={idx} className="bg-white dark:bg-slate-900 px-4 py-4 sm:px-6 rounded-lg shadow-sm border border-purple-100 dark:border-slate-800 hover:border-purple-300 dark:hover:border-purple-500 transition duration-150 ease-in-out relative overflow-hidden group">
                  <div className="absolute bottom-0 left-0 h-1 bg-purple-500" style={{ width: `${Math.max(10, 100 - (result.distance * 50))}%` }}></div>
                  
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-purple-700 dark:text-purple-400 truncate font-mono">
                      {result.file_path}
                    </p>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 dark:bg-purple-950/80 text-purple-800 dark:text-purple-300 uppercase tracking-wide">
                      {result.match_type}
                    </span>
                  </div>
                  <div className="mt-2">
                    <p className="text-base text-gray-800 dark:text-slate-100 font-bold font-mono">
                      {result.match_name}()
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
