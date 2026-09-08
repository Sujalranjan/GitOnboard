import React from 'react';
import LLMConversationFlow from '@/components/LLMConversationFlow';

interface Props {
  params: Promise<{ repoName: string }>;
}

export default async function ConversationFlowPage({ params }: Props) {
  const { repoName } = await params;

  return (
    <div className="flex flex-col h-full w-full">
      <LLMConversationFlow repoName={repoName} />
    </div>
  );
}
