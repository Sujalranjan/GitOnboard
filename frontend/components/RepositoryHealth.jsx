"use client";

import React, { useState, useEffect } from 'react'

export default function RepositoryHealth({ repoName }) {
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await fetch(`/api/repos/${repoName}/health/scores`)
        if (!res.ok) throw new Error("Failed to fetch health scores.")
        const json = await res.json()
        setData(json)
      } catch (err) {
        setError(err.message)
      } finally {
        setIsLoading(false)
      }
    }
    fetchHealth()
  }, [repoName])

  if (isLoading) return <div className="text-gray-500 dark:text-slate-400 text-center py-10">Loading health data...</div>
  if (error) return <div className="text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-950/60 p-4 rounded-md border border-red-100 dark:border-red-900">Error: {error}</div>
  if (!data) return <div className="text-gray-500 dark:text-slate-400">No health data available.</div>

  const getStatusColor = (status) => {
    switch (status) {
      case 'Excellent': return 'bg-green-100 dark:bg-green-950/80 text-green-800 dark:text-green-300 border-green-200 dark:border-green-800'
      case 'Good': return 'bg-blue-100 dark:bg-blue-950/80 text-blue-800 dark:text-blue-300 border-blue-200 dark:border-blue-800'
      case 'Fair': return 'bg-yellow-100 dark:bg-yellow-950/80 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800'
      case 'Needs Work': return 'bg-red-100 dark:bg-red-950/80 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800'
      default: return 'bg-gray-100 dark:bg-slate-800 text-gray-800 dark:text-slate-200 border-gray-200 dark:border-slate-700'
    }
  }

  return (
    <div className="space-y-6 max-h-full overflow-y-auto pr-2 text-slate-900 dark:text-slate-100">
      <div className="bg-white dark:bg-slate-900 p-6 rounded-lg border border-gray-200 dark:border-slate-800 shadow-sm flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Overall Health Score</h2>
          <p className="text-gray-500 dark:text-slate-400 mt-1">Computed deterministically from repository metrics and findings.</p>
        </div>
        <div className="text-right flex items-center gap-4">
          <div className={`px-4 py-2 rounded-full border font-bold ${getStatusColor(data.status)}`}>
            {data.status}
          </div>
          <div className="text-5xl font-black text-gray-900 dark:text-slate-100">
            {data.health_score}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(data.categories || {}).map(([catName, catData]) => (
          <div key={catName} className="bg-white dark:bg-slate-900 p-5 rounded-lg border border-gray-200 dark:border-slate-800 shadow-sm">
            <div className="flex justify-between items-center mb-2 border-b border-gray-200 dark:border-slate-800 pb-2">
              <h3 className="text-lg font-bold text-gray-800 dark:text-slate-100 capitalize">{catName}</h3>
              <div className="text-xl font-black text-blue-600 dark:text-blue-400">{catData.score.toFixed(1)}</div>
            </div>
            <p className="text-sm text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2 font-semibold">Weight: {(catData.weight * 100).toFixed(0)}%</p>
            <p className="text-gray-700 dark:text-slate-300 text-sm">{catData.explanation}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
