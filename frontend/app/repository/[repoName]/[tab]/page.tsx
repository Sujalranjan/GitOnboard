"use client";

import React from 'react';
import { useParams } from 'next/navigation';
import ExplorerView from '@/components/repository/ExplorerView';
import ArchitectureExplorer from '@/components/ArchitectureExplorer';
import KnowledgeGraphView from '@/components/repository/KnowledgeGraphView';
import SemanticSearch from '@/components/SemanticSearch';
import RepositorySummary from '@/components/RepositorySummary';
import { WorkspaceLayout } from '@/components/workspace/WorkspaceLayout';
import MultiAgentInvestigationView from '@/components/investigation/MultiAgentInvestigationView';

export default function TabPage() {
  const params = useParams();
  const repoName = params.repoName as string;
  const tab = params.tab as string;

  const renderContent = () => {
    switch (tab) {
      case 'workspace':
        return <WorkspaceLayout initialRepoName={repoName} />;
      case 'investigation':
        return <MultiAgentInvestigationView repoName={repoName} />;
      case 'explorer':
        return <ExplorerView repoName={repoName} />;
      case 'knowledge-graph':
        return <KnowledgeGraphView repoName={repoName} />;
      case 'architecture':
      case 'graph':
        return (
          <div className="p-6 h-full w-full">
            <ArchitectureExplorer repoName={repoName} />
          </div>
        );
      case 'search':
      case 'semantic':
      case 'symbols':
        return (
          <div className="p-6 h-full w-full overflow-hidden">
            <SemanticSearch repoName={repoName} />
          </div>
        );
      case 'summary':
      case 'ask':
        return (
          <div className="p-6 h-full w-full overflow-hidden">
            <RepositorySummary repoName={repoName} />
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
    <div className="w-full h-full relative">
      {renderContent()}
    </div>
  );
}
