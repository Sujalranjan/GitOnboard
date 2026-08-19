"use client";

import React from 'react';
import { useParams } from 'next/navigation';
import ExplorerView from '@/components/repository/ExplorerView';
import ArchitectureExplorer from '@/components/ArchitectureExplorer';
import SemanticSearch from '@/components/SemanticSearch';
import RepositorySummary from '@/components/RepositorySummary';
import { WorkspaceLayout } from '@/components/workspace/WorkspaceLayout';

export default function TabPage() {
  const params = useParams();
  const repoName = params.repoName as string;
  const tab = params.tab as string;

  const renderContent = () => {
    switch (tab) {
      case 'workspace':
        return <WorkspaceLayout initialRepoName={repoName} />;
      case 'explorer':
        return <ExplorerView repoName={repoName} />;
      case 'architecture':
      case 'graph':
        return (
          <div className="p-6 h-full">
            <div className="h-full bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800 overflow-hidden">
              <ArchitectureExplorer repoName={repoName} />
            </div>
          </div>
        );
      case 'search':
      case 'semantic':
      case 'symbols':
        return (
          <div className="p-6 h-full">
            <div className="bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800 h-full p-6 overflow-y-auto">
              <SemanticSearch repoName={repoName} />
            </div>
          </div>
        );
      case 'summary':
      case 'ask':
        return (
          <div className="p-6 h-full">
            <div className="bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800 h-full p-6 overflow-y-auto">
              <RepositorySummary repoName={repoName} />
            </div>
          </div>
        );
      default:
        return (
          <div className="flex items-center justify-center h-full text-slate-500">
            Tab "{tab}" not found.
          </div>
        );
    }
  };

  return (
    <div className="w-full h-full bg-slate-50 dark:bg-slate-950 relative">
      {renderContent()}
    </div>
  );
}
