"use client";

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, 
  FolderTree, 
  Network, 
  Search, 
  Sparkles, 
  GitMerge
} from 'lucide-react';

const navItems = [
  { id: 'overview', label: 'Dashboard', icon: LayoutDashboard, path: '' },
  { id: 'workspace', label: 'AI Workspace IDE', icon: Sparkles, directPath: '/workspace' },
  { id: 'trace', label: 'Feature Tracing', icon: GitMerge, path: '/trace' },
  { id: 'explorer', label: 'File Explorer', icon: FolderTree, path: '/explorer' },
  { id: 'architecture', label: 'Architecture', icon: Network, path: '/architecture' },
  { id: 'search', label: 'Search', icon: Search, path: '/search' },
  { id: 'summary', label: 'AI Summary', icon: Sparkles, path: '/summary' },
];

export function Sidebar({ repoName }) {
  const pathname = usePathname();
  
  return (
    <div className="w-64 border-r border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex flex-col h-full hidden md:flex transition-colors">
      <div className="flex-grow py-6 overflow-y-auto overflow-x-hidden">
        <nav className="space-y-1 px-3">
          {navItems.map((item) => {
            const itemPath = item.directPath ? item.directPath : `/repository/${repoName}${item.path}`;
            const isActive = item.directPath
              ? pathname === item.directPath
              : item.path === ''
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
    </div>
  );
}
