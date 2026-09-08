import React from 'react';
import LLMConversationFlow from '../components/LLMConversationFlow';

/**
 * LLM Conversation Flow Demo Page
 *
 * Shows how LLM actually works:
 * User Question → Tool Call → Tool Response → LLM Processing → Next Tool → ... → Final Answer
 *
 * No stages, no artificial structure - just real conversation flow
 */

export default function ConversationFlowPage() {
  return (
    <div style={{ padding: '20px' }}>
      <LLMConversationFlow />
    </div>
  );
}
