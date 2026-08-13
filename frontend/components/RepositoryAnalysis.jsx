"use client";

import React, { useState, useEffect } from 'react'

export default function RepositoryAnalysis({ repoName }) {
  const [findings, setFindings] = useState([])
  const [smells, setSmells] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all') // all, deadcode, smells

  useEffect(() => {
    const fetchAnalysis = async () => {
      try {
        const [resFindings, resSmells] = await Promise.all([
          fetch(`/api/repos/${repoName}/health/findings`),
          fetch(`/api/repos/${repoName}/health/smells`)
        ])
        
        if (!resFindings.ok || !resSmells.ok) {
          throw new Error("Failed to fetch analysis data.")
        }
        
        const jsonFindings = await resFindings.json()
        const jsonSmells = await resSmells.json()
        
        setFindings(jsonFindings.findings || [])
        setSmells(jsonSmells.smells || [])
      } catch (err) {
        setError(err.message)
      } finally {
        setIsLoading(false)
      }
    }
    fetchAnalysis()
  }, [repoName])

  if (isLoading) return <div className="text-gray-500 dark:text-slate-400 text-center py-10">Running analysis...</div>
  if (error) return <div className="text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-950/60 p-4 rounded-md border border-red-100 dark:border-red-900">Error: {error}</div>

  const deadCode = findings.filter(f => f.title.includes('Unused') || f.title.includes('Unreachable'))
  
  let displayedItems = []
  if (filter === 'all') displayedItems = [...findings, ...smells]
  else if (filter === 'deadcode') displayedItems = deadCode
  else if (filter === 'smells') displayedItems = smells

  const getSeverityBadge = (severity) => {
    const sevStr = String(severity).toLowerCase()
    if (sevStr.includes('critical')) return <span className="bg-red-100 dark:bg-red-950/80 text-red-800 dark:text-red-300 text-xs font-bold px-2 py-1 rounded border border-red-200 dark:border-red-800">CRITICAL</span>
    if (sevStr.includes('error')) return <span className="bg-orange-100 dark:bg-orange-950/80 text-orange-800 dark:text-orange-300 text-xs font-bold px-2 py-1 rounded border border-orange-200 dark:border-orange-800">ERROR</span>
    return <span className="bg-yellow-100 dark:bg-yellow-950/80 text-yellow-800 dark:text-yellow-300 text-xs font-bold px-2 py-1 rounded border border-yellow-200 dark:border-yellow-800">WARNING</span>
  }

  return (
    <div className="flex flex-col h-full space-y-4 text-slate-900 dark:text-slate-100">
      <div className="flex space-x-2 bg-gray-50 dark:bg-slate-900 p-2 rounded-lg border border-gray-200 dark:border-slate-800">
        <button 
          onClick={() => setFilter('all')}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${filter === 'all' ? 'bg-white dark:bg-slate-800 shadow border border-gray-200 dark:border-slate-700 text-gray-900 dark:text-slate-100' : 'text-gray-600 dark:text-slate-400 hover:bg-gray-100 dark:hover:bg-slate-800'}`}
        >
          All Findings ({findings.length + smells.length})
        </button>
        <button 
          onClick={() => setFilter('deadcode')}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${filter === 'deadcode' ? 'bg-white dark:bg-slate-800 shadow border border-gray-200 dark:border-slate-700 text-gray-900 dark:text-slate-100' : 'text-gray-600 dark:text-slate-400 hover:bg-gray-100 dark:hover:bg-slate-800'}`}
        >
          Dead Code ({deadCode.length})
        </button>
        <button 
          onClick={() => setFilter('smells')}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${filter === 'smells' ? 'bg-white dark:bg-slate-800 shadow border border-gray-200 dark:border-slate-700 text-gray-900 dark:text-slate-100' : 'text-gray-600 dark:text-slate-400 hover:bg-gray-100 dark:hover:bg-slate-800'}`}
        >
          Architecture Smells ({smells.length})
        </button>
      </div>

      <div className="flex-grow overflow-y-auto space-y-3 pr-2">
        {displayedItems.length === 0 ? (
          <div className="text-gray-500 dark:text-slate-400 text-center py-10 italic">No findings to display for this category. Great job!</div>
        ) : (
          displayedItems.map((item, idx) => (
            <div key={idx} className="bg-white dark:bg-slate-900 p-4 rounded-lg border border-gray-200 dark:border-slate-800 shadow-sm flex flex-col space-y-2 hover:border-blue-300 dark:hover:border-blue-500 transition-colors">
              <div className="flex items-start justify-between">
                <h3 className="text-lg font-bold text-gray-900 dark:text-slate-100">{item.title || item.type}</h3>
                {getSeverityBadge(item.severity)}
              </div>
              <p className="text-sm text-gray-700 dark:text-slate-300">{item.description}</p>
              
              {item.file_path && (
                <div className="mt-2 text-xs font-mono text-gray-500 dark:text-slate-400 bg-gray-50 dark:bg-slate-800 p-2 rounded border border-gray-100 dark:border-slate-700 inline-block w-fit">
                  {item.file_path}
                </div>
              )}
              {item.members && (
                <div className="mt-2 text-xs font-mono text-gray-500 dark:text-slate-400 bg-gray-50 dark:bg-slate-800 p-2 rounded border border-gray-100 dark:border-slate-700">
                  <span className="font-bold uppercase text-gray-400 dark:text-slate-500 mr-2">Cycle Members:</span>
                  {item.members.join(' → ')}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
