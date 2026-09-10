"use client";

import React from 'react';

export default function ViewTabs({ activeTab, setActiveTab }) {
  const tabs = [
    { id: 'explorer', label: 'File Explorer', defaultClass: 'text-gray-500 hover:text-gray-700', activeClass: 'bg-white shadow-sm text-gray-900' },
    { id: 'graph', label: 'Dependency Graph', defaultClass: 'text-gray-500 hover:text-gray-700', activeClass: 'bg-white shadow-sm text-gray-900' },
    { id: 'architecture', label: 'Architecture', defaultClass: 'text-gray-500 hover:text-gray-700', activeClass: 'bg-white shadow-sm text-gray-900' },
    { id: 'callgraph', label: 'Call Explorer', defaultClass: 'text-gray-500 hover:text-gray-700', activeClass: 'bg-white shadow-sm text-gray-900' },
    { id: 'search', label: 'Search', defaultClass: 'text-gray-500 hover:text-gray-700', activeClass: 'bg-white shadow-sm text-gray-900' },
    { id: 'symbols', label: 'Symbols', defaultClass: 'text-gray-500 hover:text-gray-700', activeClass: 'bg-white shadow-sm text-gray-900' },
    { id: 'semantic', label: '✨ Semantic Search', defaultClass: 'text-purple-500 hover:text-purple-700', activeClass: 'bg-white shadow-sm text-purple-700 border border-purple-100' },
    { id: 'summary', label: '📝 Summary', defaultClass: 'text-blue-500 hover:text-blue-700', activeClass: 'bg-white shadow-sm text-blue-700 border border-blue-100' },
    { id: 'health', label: '✨ Health', defaultClass: 'text-green-500 hover:text-green-700', activeClass: 'bg-white shadow-sm text-green-700 border border-green-100' },
    { id: 'metrics', label: '📊 Metrics', defaultClass: 'text-teal-500 hover:text-teal-700', activeClass: 'bg-white shadow-sm text-teal-700 border border-teal-100' },
    { id: 'analysis', label: '🔬 Analysis', defaultClass: 'text-red-500 hover:text-red-700', activeClass: 'bg-white shadow-sm text-red-700 border border-red-100' },
  ];

  return (
    <div className="flex bg-gray-100 p-1 rounded-lg border border-gray-200 overflow-x-auto scrollbar-hide">
      {tabs.map((tab) => (
        <button 
          key={tab.id}
          onClick={() => setActiveTab(tab.id)}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${activeTab === tab.id ? tab.activeClass : tab.defaultClass}`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
