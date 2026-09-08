'use client';

import React from 'react';
import { useParams } from 'next/navigation';
import LLMConversationFlow from '@/components/LLMConversationFlow';

export default function ConversationFlowPage() {
  const params = useParams();
  const repoName = (params?.repoName as string) || '';

  if (!repoName) {
    return <div className="p-8 text-center text-slate-500">Loading...</div>;
  }

  return (
    <div className="flex flex-col h-full w-full">
      <LLMConversationFlow repoName={repoName} />
    </div>
  );
}
