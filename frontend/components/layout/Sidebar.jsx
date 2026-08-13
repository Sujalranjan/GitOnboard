"use client";

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, 
  FolderTree, 
  Share2, 
  Network, 
  Crosshair, 
  Search, 
  Code2, 
  Sparkles, 
  Activity, 
  BarChart3, 
  Microscope,
  ChevronLeft,
  CheckCircle2,
  GitMerge
} from 'lucide-react';

const navItems = [
  { id: 'overview', label: 'Dashboard', icon: LayoutDashboard, path: '' },
  { id: 'trace', label: 'Feature Tracing', icon: GitMerge, path: '/trace' },
  { id: 'explorer', label: 'File Explorer', icon: FolderTree, path: '/explorer' },
  { id: 'graph', label: 'Dependency Graph', icon: Share2, path: '/graph' },
  { id: 'architecture', label: 'Architecture', icon: Network, path: '/architecture' },
  { id: 'callgraph', label: 'Call Explorer', icon: Crosshair, path: '/callgraph' },
  { id: 'search', label: 'Search', icon: Search, path: '/search' },
  { id: 'symbols', label: 'Symbols', icon: Code2, path: '/symbols' },
  { id: 'summary', label: 'AI Summary', icon: Sparkles, path: '/summary' },
  { id: 'health', label: 'Health', icon: Activity, path: '/health' },
  { id: 'metrics', label: 'Metrics', icon: BarChart3, path: '/metrics' },
  { id: 'analysis', label: 'Analysis', icon: Microscope, path: '/analysis' },
];

export function Sidebar({ repoName }) {
  const pathname = usePathname();
  
  return (
    <div className="w-64 border-r border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex flex-col h-full hidden md:flex transition-colors">
      <div className="flex-grow py-6 overflow-y-auto overflow-x-hidden">
        <nav className="space-y-1 px-3">
          {navItems.map((item) => {
            const itemPath = `/repository/${repoName}${item.path}`;
            const isActive = item.path === '' 
              ? pathname === `/repository/${repoName}` 
              : pathname.startsWith(itemPath);

            return (
              <Link 
                key={item.id} 
                href={itemPath}
                className={`
                  flex items-center px-3 py-2.5 rounded-lg text-sm font-medium transition-colors group
                  ${isActive 
                    ? 'bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-400' 
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100'}
                `}
              >
                <item.icon 
                  className={`flex-shrink-0 mr-3 h-5 w-5 ${isActive ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400 dark:text-slate-500 group-hover:text-slate-500 dark:group-hover:text-slate-300'}`} 
                />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
      
      <div className="p-4 border-t border-slate-200 dark:border-slate-800">
        <button className="flex items-center text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 text-sm font-medium transition-colors mb-6 w-full px-3">
          <ChevronLeft className="h-4 w-4 mr-2" /> Collapse
        </button>
        
        <div className="bg-white dark:bg-slate-800 rounded-lg p-3 border border-slate-200 dark:border-slate-700 shadow-sm flex items-start space-x-3">
          <CheckCircle2 className="h-5 w-5 text-green-500 dark:text-green-400 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200">Sync Status</p>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Up to date</p>
          </div>
        </div>
      </div>
    </div>
  );
}
