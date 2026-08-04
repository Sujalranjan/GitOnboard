"use client";

import React from 'react';
import { useParams } from 'next/navigation';
import ExplorerView from '@/components/repository/ExplorerView';
import DependencyGraph from '@/components/DependencyGraph';
import CallExplorer from '@/components/CallExplorer';
import ArchitectureExplorer from '@/components/ArchitectureExplorer';
import Search from '@/components/Search';
import SemanticSearch from '@/components/SemanticSearch';
import RepositorySummary from '@/components/RepositorySummary';
import SymbolExplorer from '@/components/SymbolExplorer';
import RepositoryHealth from '@/components/RepositoryHealth';
import RepositoryMetrics from '@/components/RepositoryMetrics';
import RepositoryAnalysis from '@/components/RepositoryAnalysis';

export default function TabPage() {
  const params = useParams();
  const repoName = params.repoName;
  const tab = params.tab;

  const renderContent = () => {
    switch (tab) {
      case 'explorer':
        return <ExplorerView repoName={repoName} />;
      case 'graph':
        return (
          <div className="p-6 h-full">
            <div className="h-full bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
              <DependencyGraph repoName={repoName} />
            </div>
          </div>
        );
      case 'architecture':
        return (
          <div className="p-6 h-full">
            <div className="h-full bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
              <ArchitectureExplorer repoName={repoName} />
            </div>
          </div>
        );
      case 'callgraph':
        return (
          <div className="p-6 h-full">
            <div className="h-full bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
              <CallExplorer repoName={repoName} />
            </div>
          </div>
        );
      case 'search':
        return (
          <div className="p-6 h-full">
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 h-full p-6 overflow-y-auto">
              <Search repoName={repoName} />
            </div>
          </div>
        );
      case 'semantic':
        return (
          <div className="p-6 h-full">
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 h-full p-6 overflow-y-auto">
              <SemanticSearch repoName={repoName} />
            </div>
          </div>
        );
      case 'summary':
        return (
          <div className="p-6 h-full">
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 h-full p-6 overflow-y-auto">
              <RepositorySummary repoName={repoName} />
            </div>
          </div>
        );
      case 'symbols':
        return (
          <div className="p-6 h-full">
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 h-full p-6 overflow-y-auto">
              <SymbolExplorer repoName={repoName} />
            </div>
          </div>
        );
      case 'health':
        return (
          <div className="p-6 h-full overflow-y-auto">
            <RepositoryHealth repoName={repoName} />
          </div>
        );
      case 'metrics':
        return (
          <div className="p-6 h-full overflow-y-auto">
            <RepositoryMetrics repoName={repoName} />
          </div>
        );
      case 'analysis':
        return (
          <div className="p-6 h-full overflow-y-auto">
            <RepositoryAnalysis repoName={repoName} />
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
    <div className="w-full h-full bg-slate-50 relative">
      {renderContent()}
    </div>
  );
}
