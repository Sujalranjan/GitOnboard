"use client";

import React, { useState, useEffect } from 'react'

export default function RepositoryMetrics({ repoName }) {
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch(`/api/repos/${repoName}/health/metrics`)
        if (!res.ok) throw new Error("Failed to fetch metrics.")
        const json = await res.json()
        setData(json)
      } catch (err) {
        setError(err.message)
      } finally {
        setIsLoading(false)
      }
    }
    fetchMetrics()
  }, [repoName])

  if (isLoading) return <div className="text-gray-500 dark:text-slate-400 text-center py-10">Loading metrics...</div>
  if (error) return <div className="text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-950/60 p-4 rounded-md border border-red-100 dark:border-red-900">Error: {error}</div>
  if (!data) return <div className="text-gray-500 dark:text-slate-400">No metrics data available.</div>

  const formatNumber = (num) => num != null ? Number(num).toLocaleString() : 'N/A'

  return (
    <div className="space-y-6 max-h-full overflow-y-auto pr-2 text-slate-900 dark:text-slate-100">
      <div className="bg-white dark:bg-slate-900 p-6 rounded-lg border border-gray-200 dark:border-slate-800 shadow-sm">
        <h2 className="text-xl font-bold text-gray-900 dark:text-slate-100 mb-4 border-b border-gray-200 dark:border-slate-800 pb-2">Repository Overview</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Total Files</p>
            <p className="text-2xl font-black text-gray-800 dark:text-slate-100">{formatNumber(data.total_files)}</p>
          </div>
          <div>
            <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Lines of Code</p>
            <p className="text-2xl font-black text-blue-600 dark:text-blue-400">{formatNumber(data.lines_of_code)}</p>
          </div>
          <div>
            <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Functions</p>
            <p className="text-2xl font-black text-gray-800 dark:text-slate-100">{formatNumber(data.total_functions)}</p>
          </div>
          <div>
            <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Classes</p>
            <p className="text-2xl font-black text-gray-800 dark:text-slate-100">{formatNumber(data.total_classes)}</p>
          </div>
          <div>
            <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Test Coverage</p>
            <p className="text-2xl font-black text-green-600 dark:text-green-400">{data.test_coverage_approx_percent?.toFixed(1) || '0.0'}%</p>
          </div>
          <div>
            <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Doc Coverage</p>
            <p className="text-2xl font-black text-green-600 dark:text-green-400">{data.documentation_coverage_percent?.toFixed(1) || '0.0'}%</p>
          </div>
          <div>
            <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Avg Complexity</p>
            <p className="text-2xl font-black text-purple-600 dark:text-purple-400">{data.average_cyclomatic_complexity?.toFixed(2) || 'N/A'}</p>
          </div>
          <div>
            <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Modules</p>
            <p className="text-2xl font-black text-gray-800 dark:text-slate-100">{formatNumber(data.total_modules)}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-slate-900 p-6 rounded-lg border border-gray-200 dark:border-slate-800 shadow-sm">
          <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 mb-4 border-b border-gray-200 dark:border-slate-800 pb-2">Largest Files</h2>
          {data.largest_files && data.largest_files.length > 0 ? (
            <ul className="space-y-3">
              {data.largest_files.map((f, i) => (
                <li key={i} className="flex justify-between items-center text-sm">
                  <span className="font-mono text-gray-700 dark:text-slate-300 truncate w-3/4">{f.file}</span>
                  <span className="font-bold text-gray-900 dark:text-slate-100 bg-gray-100 dark:bg-slate-800 px-2 py-1 rounded">{formatNumber(f.size)} bytes</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-500 dark:text-slate-400 italic">No large files found.</p>
          )}
        </div>

        <div className="bg-white dark:bg-slate-900 p-6 rounded-lg border border-gray-200 dark:border-slate-800 shadow-sm">
          <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 mb-4 border-b border-gray-200 dark:border-slate-800 pb-2">Largest Modules</h2>
          {data.largest_modules && data.largest_modules.length > 0 ? (
            <ul className="space-y-3">
              {data.largest_modules.map((m, i) => (
                <li key={i} className="flex justify-between items-center text-sm">
                  <span className="font-mono text-gray-700 dark:text-slate-300 truncate w-3/4">{m.module}</span>
                  <span className="font-bold text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/60 border border-purple-100 dark:border-purple-900/60 px-2 py-1 rounded">{formatNumber(m.functions)} funcs</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-500 dark:text-slate-400 italic">No large modules found.</p>
          )}
        </div>
      </div>
    </div>
  )
}
