"use client";

import React from 'react';

export default function CodeDetailsViewer({ 
  selectedFile, 
  isParsing, 
  parseError, 
  astData, 
  selectedFunction, 
  setSelectedFunction, 
  selectedClass, 
  setSelectedClass 
}) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-gray-200 dark:border-slate-800 overflow-hidden flex flex-col h-full text-slate-900 dark:text-slate-100">
      <div className="bg-gray-50 dark:bg-slate-800/60 px-6 py-4 border-b border-gray-200 dark:border-slate-800 flex-shrink-0 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-slate-100">
            {selectedFunction ? `Function: ${selectedFunction.name}` : selectedClass ? `Class: ${selectedClass.name}` : selectedFile ? `File: ${selectedFile}` : "Repository Viewer"}
          </h2>
        </div>
        {(selectedFunction || selectedClass) && (
          <button 
            onClick={() => { setSelectedFunction(null); setSelectedClass(null); }}
            className="text-sm bg-white dark:bg-slate-800 border border-gray-300 dark:border-slate-700 px-3 py-1 rounded hover:bg-gray-50 dark:hover:bg-slate-700 font-medium text-slate-700 dark:text-slate-200"
          >
            &larr; Back to File
          </button>
        )}
      </div>
      
      <div className="p-6 overflow-y-auto overflow-x-hidden flex-grow">
        {!selectedFile ? (
          <div className="text-center text-gray-400 dark:text-slate-500 mt-20">
            <div className="text-4xl mb-2">🔍</div>
            <p className="text-lg">Select a source file from the explorer</p>
          </div>
        ) : isParsing ? (
          <div className="text-center text-blue-500 dark:text-blue-400 font-medium mt-10 text-lg">Extracting structures...</div>
        ) : parseError ? (
          <div className="bg-red-50 dark:bg-red-950/60 text-red-600 dark:text-red-300 p-4 rounded-md text-base border border-red-100 dark:border-red-900">Failed to parse: {parseError}</div>
        ) : astData ? (
          <div className="space-y-6 max-w-full">
            
            {/* --- FUNCTION DETAIL VIEW --- */}
            {selectedFunction ? (
              <div className="space-y-6">
                <div className="bg-blue-50 dark:bg-blue-950/60 border border-blue-100 dark:border-blue-900/60 rounded-md p-5">
                  <div className="font-mono text-xl font-bold text-blue-800 dark:text-blue-300 break-all mb-4">
                    <span className="text-blue-500 dark:text-blue-400 font-normal">Function: </span>{selectedFunction.name}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Location</p>
                      <p className="text-base text-gray-900 dark:text-slate-100 mt-1">Line {selectedFunction.line_number || "Unknown"}</p>
                    </div>
                    <div>
                      <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase">Parameters</p>
                      <div className="mt-1 flex flex-wrap gap-2">
                        {selectedFunction.parameters && selectedFunction.parameters.length > 0 ? (
                          selectedFunction.parameters.map((p, i) => (
                            <span key={i} className="px-2 py-1 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded text-sm font-mono text-gray-700 dark:text-slate-300">{p}</span>
                          ))
                        ) : (
                          <span className="text-sm text-gray-500 dark:text-slate-400 italic">None</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                <div>
                  <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase mb-2 border-b border-gray-200 dark:border-slate-800 pb-2">Docstring</p>
                  {selectedFunction.docstring ? (
                    <pre className="bg-gray-50 dark:bg-slate-800/80 p-4 rounded text-base text-gray-700 dark:text-slate-300 whitespace-pre-wrap break-words border border-gray-100 dark:border-slate-800 font-sans">{selectedFunction.docstring}</pre>
                  ) : (
                    <p className="text-gray-400 dark:text-slate-500 italic">No docstring provided.</p>
                  )}
                </div>
              </div>
            ) : 
            
            /* --- CLASS DETAIL VIEW --- */
            selectedClass ? (
              <div className="space-y-6">
                <div className="bg-purple-50 dark:bg-purple-950/60 border border-purple-100 dark:border-purple-900/60 rounded-md p-5">
                  <div className="font-mono text-xl font-bold text-purple-800 dark:text-purple-300 break-all mb-2">class {selectedClass.name}</div>
                  <div>
                    <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase mt-4 mb-2">Docstring</p>
                    {selectedClass.docstring ? (
                      <pre className="bg-white dark:bg-slate-800 p-4 rounded text-base text-gray-700 dark:text-slate-300 whitespace-pre-wrap break-words border border-gray-100 dark:border-slate-700 font-sans">{selectedClass.docstring}</pre>
                    ) : (
                      <p className="text-gray-400 dark:text-slate-500 italic">No docstring provided.</p>
                    )}
                  </div>
                </div>
                <div>
                  <p className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase mb-3 border-b border-gray-200 dark:border-slate-800 pb-2">Methods ({selectedClass.methods.length})</p>
                  {selectedClass.methods.length > 0 ? (
                    <div className="grid grid-cols-1 gap-3">
                      {selectedClass.methods.map((method, mi) => (
                        <div key={mi} className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-md p-4 shadow-sm hover:border-purple-300 dark:hover:border-purple-500 transition-colors">
                          <div className="font-mono text-base font-bold text-gray-800 dark:text-slate-100 break-all">def {method.name}()</div>
                          {method.docstring && (
                            <pre className="text-sm text-gray-600 dark:text-slate-300 mt-2 whitespace-pre-wrap break-words font-sans">{method.docstring}</pre>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 dark:text-slate-400 italic">No methods defined in this class.</p>
                  )}
                </div>
              </div>
            ) : 
            
            /* --- FILE VIEW --- */
            (
              <div className="space-y-8">
                {/* Classes */}
                <div>
                  <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-3 border-b border-gray-200 dark:border-slate-800 pb-2">Classes ({astData.classes.length})</h3>
                  {astData.classes.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {astData.classes.map((cls, i) => (
                        <div 
                          key={i} 
                          onClick={() => setSelectedClass(cls)}
                          className="border border-purple-200 dark:border-purple-900/60 rounded-md p-4 bg-white dark:bg-slate-800/80 hover:bg-purple-50 dark:hover:bg-purple-950/40 cursor-pointer shadow-sm transition-colors group"
                        >
                          <div className="font-mono text-lg font-bold text-purple-700 dark:text-purple-400 group-hover:text-purple-900 dark:group-hover:text-purple-300 break-all">{cls.name}</div>
                          <div className="text-sm text-gray-500 dark:text-slate-400 mt-1">{cls.methods.length} methods</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400 dark:text-slate-500 italic">No classes found.</p>
                  )}
                </div>

                {/* Functions */}
                <div>
                  <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-3 border-b border-gray-200 dark:border-slate-800 pb-2">Functions ({astData.functions.length})</h3>
                  {astData.functions.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {astData.functions.map((fn, i) => (
                        <div 
                          key={i} 
                          onClick={() => setSelectedFunction(fn)}
                          className="border border-blue-200 dark:border-blue-900/60 rounded-md p-4 bg-white dark:bg-slate-800/80 hover:bg-blue-50 dark:hover:bg-blue-950/40 cursor-pointer shadow-sm transition-colors group"
                        >
                          <div className="font-mono text-base font-bold text-blue-700 dark:text-blue-400 group-hover:text-blue-900 dark:group-hover:text-blue-300 break-all">{fn.name}()</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400 dark:text-slate-500 italic">No functions found.</p>
                  )}
                </div>

                {/* Imports */}
                <div>
                  <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-3 border-b border-gray-200 dark:border-slate-800 pb-2">Imports ({astData.imports.length})</h3>
                  {astData.imports.length > 0 ? (
                    <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {astData.imports.map((imp, i) => (
                        <li key={i} className="text-base text-gray-700 dark:text-slate-300 bg-gray-50 dark:bg-slate-800 px-3 py-2 rounded border border-gray-200 dark:border-slate-700 font-mono break-all">
                          {imp.module_name} {imp.alias ? `(as ${imp.alias})` : ''}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-gray-400 dark:text-slate-500 italic">No imports found.</p>
                  )}
                </div>
              </div>
            )}
            
          </div>
        ) : null}
      </div>
    </div>
  );
}
