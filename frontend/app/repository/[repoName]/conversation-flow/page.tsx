import React from 'react';
import LLMConversationFlow from '@/components/LLMConversationFlow';

/**
 * LLM Conversation Flow Page
 *
 * Shows how LLM queries the repository:
 * User Question → Tool Call → Response → LLM Processing → Next Tool → ... → Final Answer
 *
 * Part of the Repository Intelligence Platform features
 */

export default function ConversationFlowPage() {
  return (
    <div className="flex flex-col h-full w-full">
      <LLMConversationFlow />
    </div>
  );
}
