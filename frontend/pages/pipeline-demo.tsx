import React from 'react';
import PipelineVisualizer from '../components/PipelineVisualizer';

/**
 * Pipeline Demonstration Page
 *
 * Shows the 8-stage pipeline of how LLM agents query the codebase:
 *
 * Stage 1: User Question Received
 * Stage 2: LLM Reasoning & Tool Selection
 * Stage 3: Tool #3 Call - Search Auth Symbols
 * Stage 4: Tool #3 Call - Query Graph Relationships
 * Stage 5: Tool #2 Call - Read File Content
 * Stage 6: Read Additional Auth Files
 * Stage 7: LLM Analysis & Context Building
 * Stage 8: Final Answer Generated
 *
 * Features:
 * ✅ Interactive stage-by-stage progression
 * ✅ Auto-play mode to watch the pipeline
 * ✅ Shows input/output for each stage
 * ✅ Displays tool calls and responses
 * ✅ Final synthesis into comprehensive answer
 * ✅ Performance metrics visualization
 */

export default function PipelineDemoPage() {
  return (
    <div>
      <PipelineVisualizer />
    </div>
  );
}
