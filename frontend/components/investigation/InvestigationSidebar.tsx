'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  FolderTree,
  Network,
  Search,
  Sparkles,
  GitMerge,
  GitCompare,
  MessageCircle,
  Share2,
  Settings,
  Bot
} from 'lucide-react';

interface SidebarProps {
  repoName: string;
}

const navItems = [
  { id: 'overview', label: 'Dashboard', icon: LayoutDashboard, path: '' },
  { id: 'conversation-flow', label: 'LLM Conversation Flow', icon: MessageCircle, path: '/conversation-flow' },
  { id: 'investigation', label: 'Chatbot', icon: Sparkles, path: '/investigation' },
  { id: 'rim-comparison', label: 'RIM Comparison', icon: GitCompare, path: '/rim-comparison' },
  { id: 'knowledge-graph', label: 'Knowledge Graph', icon: Share2, path: '/knowledge-graph' },
  { id: 'summary', label: 'AI Summary', icon: Bot, path: '/summary' },
  { id: 'trace', label: 'Feature Tracing', icon: GitMerge, path: '/trace' },
  { id: 'workspace', label: 'AI Workspace IDE', icon: Sparkles, path: '/workspace' },
  { id: 'search', label: 'Search', icon: Search, path: '/search' },
  { id: 'explorer', label: 'File Explorer', icon: FolderTree, path: '/explorer' },
  { id: 'architecture', label: 'Architecture', icon: Network, path: '/architecture' },
];

export const InvestigationSidebar: React.FC<SidebarProps> = ({ repoName }) => {
  const pathname = usePathname();

  return (
    <div className="w-[220px] flex-shrink-0 glass-nav border-r border-slate-200/70 dark:border-slate-800/70 flex flex-col h-full select-none text-slate-700 dark:text-slate-300">
      {/* Brand logo header */}
      <div className="h-14 px-4 flex items-center gap-2.5 border-b border-slate-200/60 dark:border-slate-800/60 flex-shrink-0">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-violet-600 to-blue-600 flex items-center justify-center text-white shadow-sm shadow-violet-500/30">
          <Sparkles className="w-4 h-4 fill-white" />
        </div>
        <span className="text-base font-bold text-slate-900 dark:text-white tracking-tight">GitOnboard</span>
      </div>

      {/* Nav items list */}
      <div className="flex-1 py-3 px-2 overflow-y-auto space-y-0.5">
        {navItems.map((item) => {
          const itemPath =
            item.id === 'workspace'
              ? `/workspace?repo=${encodeURIComponent(repoName || '')}`
              : item.path === ''
              ? `/repository/${repoName}`
              : `/repository/${repoName}${item.path}`;

          const isActive = item.id === 'investigation';

          return (
            <Link
              key={item.id}
              href={itemPath}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                isActive
                  ? 'bg-gradient-to-r from-violet-600/15 to-blue-600/15 text-violet-700 dark:text-violet-300 font-semibold border border-violet-500/30 dark:border-violet-400/30 shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100/60 dark:hover:bg-slate-800/40'
              }`}
            >
              <item.icon
                className={`w-4 h-4 flex-shrink-0 ${
                  isActive ? 'text-violet-600 dark:text-violet-400' : 'text-slate-400 dark:text-slate-500'
                }`}
              />
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}
      </div>

      {/* Bottom Settings footer */}
      <div className="p-2 border-t border-slate-200/60 dark:border-slate-800/60 flex-shrink-0">
        <Link
          href={`/repository/${repoName}/settings`}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100/60 dark:hover:bg-slate-800/40 transition-colors"
        >
          <Settings className="w-4 h-4 text-slate-500" />
          <span>Settings</span>
        </Link>
      </div>
    </div>
  );
};
