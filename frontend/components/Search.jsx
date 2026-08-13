"use client";

import React, { useState, useEffect } from 'react';
import { useTaskStatus } from '../hooks/useTaskStatus';

export default function Search({ repoName }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const taskStatus = useTaskStatus(repoName, 'index');
  const [localIsIndexing, setLocalIsIndexing] = useState(false);
  const isIndexing = taskStatus === 'processing' || localIsIndexing;
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (taskStatus === 'completed' || taskStatus === 'failed') {
      setLocalIsIndexing(false);
    }
  }, [taskStatus]);

  useEffect(() => {
    let isMounted = true;
    
    const buildIndex = async () => {
      setError(null);
      setLocalIsIndexing(true);
      try {
        const res = await fetch(`/api/repos/${repoName}/index`, {
          method: 'POST'
        });
        if (!res.ok) {
          throw new Error("Failed to build metadata index");
        }
        const data = await res.json();
        if (data.status === 'completed') {
          if (isMounted) setLocalIsIndexing(false);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message);
          setLocalIsIndexing(false);
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
      const res = await fetch(`/api/repos/${repoName}/search?q=${encodeURIComponent(query)}`);
      if (!res.ok) {
        throw new Error("Search failed");
      }
      const data = await res.json();
      setResults(data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSearching(false);
    }
  };

  if (isIndexing) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-gray-500 dark:text-slate-400 bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-gray-200 dark:border-slate-800 p-8">
        <svg className="animate-spin h-10 w-10 text-indigo-500 dark:text-indigo-400 mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <p className="font-semibold text-lg text-slate-900 dark:text-slate-100">Building Metadata Index...</p>
        <p className="text-sm mt-2 max-w-sm text-center text-slate-500 dark:text-slate-400">We are traversing the repository to index files, functions, classes, imports, and docstrings.</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-gray-50 dark:bg-slate-950 rounded-lg shadow-sm border border-gray-200 dark:border-slate-800 overflow-hidden text-slate-900 dark:text-slate-100">
      
      {/* Search Header */}
      <div className="p-6 bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-800">
        <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4">Search Repository Metadata</h2>
        
        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="relative flex-grow">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg className="h-5 w-5 text-gray-400 dark:text-slate-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
              </svg>
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="block w-full pl-10 pr-3 py-3 border border-gray-300 dark:border-slate-700 rounded-md leading-5 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-gray-500 dark:placeholder-slate-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition duration-150 ease-in-out"
              placeholder="Search for functions, classes, files, imports..."
            />
          </div>
          <button
            type="submit"
            disabled={isSearching || !query.trim()}
            className="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 dark:bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:bg-indigo-400 transition duration-150 ease-in-out"
          >
            {isSearching ? 'Searching...' : 'Search'}
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>
      
      {/* Search Results */}
      <div className="flex-grow overflow-y-auto p-6">
        {!hasSearched ? (
          <div className="text-center py-12">
            <svg className="mx-auto h-12 w-12 text-gray-400 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-slate-200">No search yet</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">Enter a query above to search the repository metadata deterministically.</p>
          </div>
        ) : results.length === 0 ? (
          <div className="text-center py-12 bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-800">
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-slate-200">No results found</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">We couldn't find an exact match for "{query}".</p>
          </div>
        ) : (
          <div className="space-y-4">
            <h3 className="text-sm font-medium text-gray-500 dark:text-slate-400">Found {results.length} matching file{results.length === 1 ? '' : 's'}</h3>
            <ul className="space-y-3">
              {results.map((result, idx) => (
                <li key={idx} className="bg-white dark:bg-slate-900 px-4 py-4 sm:px-6 rounded-lg shadow-sm border border-gray-200 dark:border-slate-800 hover:border-indigo-300 dark:hover:border-indigo-500 transition duration-150 ease-in-out">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400 truncate font-mono">
                      {result.file_path}
                    </p>
                  </div>
                  <div className="mt-2 sm:flex sm:justify-between">
                    <div className="sm:flex">
                      <p className="flex items-center text-sm text-gray-500 dark:text-slate-400">
                        <svg className="flex-shrink-0 mr-1.5 h-4 w-4 text-gray-400 dark:text-slate-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                        </svg>
                        Matches:
                      </p>
                      <ul className="ml-2 list-disc list-inside text-sm text-gray-600 dark:text-slate-300">
                        {result.match_reasons.map((reason, i) => (
                          <li key={i}>{reason}</li>
                        ))}
                      </ul>
                    </div>
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
