"use client";

import React, { useState, useEffect } from 'react'

export default function SymbolExplorer({ repoName }) {
  const [symbols, setSymbols] = useState([])
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedSymbol, setSelectedSymbol] = useState(null)

  useEffect(() => {
    fetchSymbols()
  }, [repoName])

  const fetchSymbols = async (query = '') => {
    setIsLoading(true)
    setError(null)
    try {
      let url = `/api/repos/${repoName}/symbols`
      if (query) {
        url = `/api/repos/${repoName}/symbols/search?q=${encodeURIComponent(query)}`
      }
      const res = await fetch(url)
      if (!res.ok) throw new Error("Failed to fetch symbols")
      const json = await res.json()
      setSymbols(json.symbols || json.results || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSearch = (e) => {
    e.preventDefault()
    fetchSymbols(searchQuery)
  }

  const handleClear = () => {
    setSearchQuery('')
    fetchSymbols('')
    setSelectedSymbol(null)
  }

  const getSymbolIcon = (type) => {
    switch(type) {
      case 'Class': return '📦'
      case 'Function': return '⚡'
      case 'Method': return '🔧'
      case 'Variable': return '🔤'
      default: return '📄'
    }
  }

  return (
    <div className="flex h-full flex-col lg:flex-row gap-6 text-slate-900 dark:text-slate-100">
      {/* Left Pane: Search & List */}
      <div className="w-full lg:w-1/3 flex flex-col bg-gray-50 dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-lg overflow-hidden h-full max-h-[80vh]">
        <div className="p-4 border-b border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <form onSubmit={handleSearch} className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search symbols..."
              className="flex-grow px-3 py-2 border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button type="submit" className="px-4 py-2 bg-blue-600 dark:bg-blue-600 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-500">
              Search
            </button>
            {searchQuery && (
              <button type="button" onClick={handleClear} className="px-4 py-2 bg-gray-200 dark:bg-slate-800 text-gray-700 dark:text-slate-200 rounded-md hover:bg-gray-300 dark:hover:bg-slate-700">
                Clear
              </button>
            )}
          </form>
        </div>
        
        <div className="flex-grow overflow-y-auto p-2">
          {isLoading ? (
            <div className="text-center py-8 text-gray-500 dark:text-slate-400">Loading symbols...</div>
          ) : error ? (
            <div className="text-center py-8 text-red-500 dark:text-red-400">{error}</div>
          ) : symbols.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-slate-400">No symbols found.</div>
          ) : (
            <div className="space-y-1">
              {symbols.map(sym => (
                <div 
                  key={sym.id}
                  onClick={() => setSelectedSymbol(sym)}
                  className={`p-2 rounded cursor-pointer flex items-center hover:bg-blue-50 dark:hover:bg-slate-800/80 ${selectedSymbol?.id === sym.id ? 'bg-blue-100 dark:bg-slate-800 border-blue-200 dark:border-slate-700' : ''}`}
                >
                  <span className="mr-3" title={sym.type}>{getSymbolIcon(sym.type)}</span>
                  <div className="overflow-hidden">
                    <div className="font-medium text-gray-900 dark:text-slate-100 truncate">{sym.name}</div>
                    <div className="text-xs text-gray-500 dark:text-slate-400 truncate">{sym.file_path}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right Pane: Details */}
      <div className="w-full lg:w-2/3 flex flex-col bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-lg overflow-hidden h-full max-h-[80vh]">
        {selectedSymbol ? (
          <div className="p-6 overflow-y-auto h-full">
            <div className="flex items-center mb-6">
              <span className="text-3xl mr-4">{getSymbolIcon(selectedSymbol.type)}</span>
              <div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-slate-100">{selectedSymbol.name}</h2>
                <div className="text-sm font-medium text-blue-600 dark:text-blue-400 uppercase tracking-wider">{selectedSymbol.type}</div>
              </div>
            </div>

            <div className="space-y-6">
              <section>
                <h3 className="text-sm font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider border-b border-gray-200 dark:border-slate-800 pb-2 mb-3">Location</h3>
                <div className="bg-gray-50 dark:bg-slate-800 p-3 rounded-md font-mono text-sm text-gray-800 dark:text-slate-200">
                  {selectedSymbol.file_path}{selectedSymbol.line_number ? ` : Line ${selectedSymbol.line_number}` : ''}
                </div>
              </section>

              {(selectedSymbol.type === 'Function' || selectedSymbol.type === 'Method') && (
                <>
                  <section>
                    <h3 className="text-sm font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider border-b border-gray-200 dark:border-slate-800 pb-2 mb-3">Signature</h3>
                    <div className="bg-gray-800 dark:bg-slate-950 text-green-400 p-4 rounded-md font-mono text-sm overflow-x-auto whitespace-pre border border-slate-700">
                      def {selectedSymbol.name}({(selectedSymbol.parameters || []).join(', ')})
                      {selectedSymbol.returns ? ` -> ${selectedSymbol.returns}` : ''}:
                    </div>
                  </section>
                </>
              )}

              {selectedSymbol.type === 'Class' && selectedSymbol.methods && selectedSymbol.methods.length > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider border-b border-gray-200 dark:border-slate-800 pb-2 mb-3">Methods</h3>
                  <ul className="list-disc list-inside space-y-1 pl-2">
                    {selectedSymbol.methods.map((method, idx) => (
                      <li key={idx} className="text-gray-800 dark:text-slate-200 font-mono text-sm">
                        <span className="font-bold">{method.name}</span>({(method.parameters || []).join(', ')})
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {selectedSymbol.docstring && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider border-b border-gray-200 dark:border-slate-800 pb-2 mb-3">Docstring</h3>
                  <pre className="bg-yellow-50 dark:bg-yellow-950/40 border border-yellow-200 dark:border-yellow-900/60 p-4 rounded-md text-sm text-gray-800 dark:text-yellow-200 whitespace-pre-wrap font-sans">
                    {selectedSymbol.docstring}
                  </pre>
                </section>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 dark:text-slate-500 p-8 text-center">
            <div>
              <div className="text-4xl mb-4">🔍</div>
              <p>Select a symbol from the list to view its details.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
