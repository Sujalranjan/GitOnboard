"use client";

import React, { useState } from 'react';
import { PythonIcon, JavascriptIcon, TypescriptIcon, ReactIcon, JavaIcon } from './common/LanguageIcons';
import { ChevronRight, ChevronDown, Folder, FolderOpen } from 'lucide-react';

const getFileMeta = (filename) => {
  const ext = filename.split('.').pop().toLowerCase();
  switch (ext) {
    case 'py': return { isSupported: true, color: 'text-blue-500 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/60', activeBg: 'bg-blue-100 dark:bg-blue-900/80', activeText: 'text-blue-800 dark:text-blue-200', Icon: PythonIcon };
    case 'js': return { isSupported: true, color: 'text-yellow-500 dark:text-yellow-400', bg: 'bg-yellow-50 dark:bg-yellow-950/60', activeBg: 'bg-yellow-100 dark:bg-yellow-900/80', activeText: 'text-yellow-800 dark:text-yellow-200', Icon: JavascriptIcon };
    case 'ts': return { isSupported: true, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/60', activeBg: 'bg-blue-100 dark:bg-blue-900/80', activeText: 'text-blue-800 dark:text-blue-200', Icon: TypescriptIcon };
    case 'jsx': 
    case 'tsx': return { isSupported: true, color: 'text-cyan-500 dark:text-cyan-400', bg: 'bg-cyan-50 dark:bg-cyan-950/60', activeBg: 'bg-cyan-100 dark:bg-cyan-900/80', activeText: 'text-cyan-800 dark:text-cyan-200', Icon: ReactIcon };
    case 'java': return { isSupported: true, color: 'text-red-500 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-950/60', activeBg: 'bg-red-100 dark:bg-red-900/80', activeText: 'text-red-800 dark:text-red-200', Icon: JavaIcon };
    default: return { isSupported: false, color: 'text-gray-400 dark:text-slate-500', bg: 'bg-gray-50 dark:bg-slate-800/50', activeBg: 'bg-gray-200 dark:bg-slate-800', activeText: 'text-gray-800 dark:text-slate-200', Icon: null };
  }
};

const TreeNode = ({ node, onFileClick, selectedPath, isRoot = false }) => {
  const [isOpen, setIsOpen] = useState(isRoot);

  if (node.type === "file") {
    const meta = getFileMeta(node.name);
    const isSelected = selectedPath === node.path;
    
    return (
      <div 
        className={`py-1 flex items-center text-sm rounded px-2 mt-1 ${meta.isSupported ? `cursor-pointer hover:${meta.bg}` : 'text-gray-500 dark:text-slate-500'} ${isSelected ? `${meta.activeBg} font-medium ${meta.activeText}` : 'text-gray-600 dark:text-slate-300'}`}
        onClick={() => meta.isSupported && onFileClick(node.path)}
      >
        <span className={`mr-2 flex items-center justify-center w-4 h-4 ${meta.color}`}>
          {meta.Icon ? <meta.Icon className="w-4 h-4" /> : "📄"}
        </span>
        <span className="truncate" title={node.name}>{node.name}</span>
      </div>
    );
  }

  return (
    <div className="mt-1">
      <div 
        className="py-1 px-2 flex items-center text-sm font-semibold text-gray-700 dark:text-slate-200 cursor-pointer hover:bg-gray-100 dark:hover:bg-slate-800 rounded"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="mr-1 text-gray-400 dark:text-slate-500">
          {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </span>
        <span className="mr-2 text-blue-400 dark:text-blue-400">
          {isOpen ? <FolderOpen className="w-4 h-4" /> : <Folder className="w-4 h-4" />}
        </span>
        <span className="truncate" title={node.name}>{node.name}</span>
      </div>
      {isOpen && node.children && node.children.length > 0 && (
        <div className="ml-4 pl-4 border-l-2 border-gray-200 dark:border-slate-800">
          {node.children.map((child, idx) => (
            <TreeNode key={idx} node={child} onFileClick={onFileClick} selectedPath={selectedPath} />
          ))}
        </div>
      )}
    </div>
  );
};

export default function FileExplorer({ hierarchy, onFileClick, selectedFile }) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg shadow-sm border border-gray-200 dark:border-slate-800 p-4 flex-grow overflow-auto flex flex-col h-full text-slate-900 dark:text-slate-100">
      <h2 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-4 px-2 border-b border-gray-200 dark:border-slate-800 pb-2 flex-shrink-0">Repository Explorer</h2>
      <div className="flex-grow overflow-y-auto">
        {hierarchy ? (
          <TreeNode node={hierarchy} onFileClick={onFileClick} selectedPath={selectedFile} isRoot={true} />
        ) : (
          <div className="text-gray-400 dark:text-slate-500 text-sm">No files found.</div>
        )}
      </div>
    </div>
  );
}
