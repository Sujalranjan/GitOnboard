"use client";

import React from 'react';
import { useParams } from 'next/navigation';
import KnowledgeGraphView from '@/components/repository/KnowledgeGraphView';

export default function KnowledgeGraphPage() {
  const params = useParams();
  const repoName = (params?.repoName as string) || '';

  return (
    <div className="w-full h-full">
      <KnowledgeGraphView repoName={repoName} />
    </div>
  );
}
