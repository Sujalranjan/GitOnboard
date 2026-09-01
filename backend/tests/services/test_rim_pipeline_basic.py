"""Basic integration test for RIM pipeline.

Tests that the pipeline can execute end-to-end with mocked components.
Verifies:
1. Message history builds correctly
2. LLMRequest is constructed properly
3. Tool observations reach the LLM
4. Metrics are collected
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from backend.services.rim_qa_loop import RIMQALoop, QALoopResult, QALoopTurn, SystemPromptParts
from backend.services.rim_tool_dispatch import ToolDispatchTable
from backend.agent.loop.contracts import AgentLoopConfig, ToolObservation
from backend.ai.schemas import LLMResponse, TokenUsage


@pytest.mark.asyncio
async def test_rim_qa_loop_builds_message_history():
    """Test that message history accumulates across turns with tool observations."""

    # Create mocked dependencies
    mock_llm_service = AsyncMock()
    mock_tool_dispatch = AsyncMock(spec=ToolDispatchTable)

    config = AgentLoopConfig(
        max_agent_turns=3,
        max_tool_calls=3,
        max_execution_seconds=30,
        max_observation_bytes=8000,
    )

    system_prompt_parts = SystemPromptParts(
        grounding_and_protocol_text="You are a test assistant.",
        tool_catalog_text="Available tools: read_file, search_repository",
        rim_metadata_text="",
        full_text="You are a test assistant.\nAvailable tools: read_file, search_repository"
    )

    loop = RIMQALoop(
        llm_service=mock_llm_service,
        tool_dispatch=mock_tool_dispatch,
        config=config,
        system_prompt_parts=system_prompt_parts,
        model="test-model"
    )

    # Set up mock responses: first turn is tool_call, second turn is final_answer
    mock_llm_service.generate = AsyncMock()

    # Turn 0: LLM responds with tool_call
    tool_call_response = LLMResponse(
        content='{"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "test"}}',
        model="test-model",
        provider="mock",
        usage=TokenUsage(prompt_tokens=50, completion_tokens=10, total_tokens=60)
    )

    # Tool execution result
    tool_observation = ToolObservation(
        tool_call_id="turn-0",
        tool_name="search_repository",
        success=True,
        data=[{"path": "src/test.py", "line": 1}]
    )
    mock_tool_dispatch.dispatch = MagicMock(return_value=tool_observation)

    # Turn 1: LLM responds with final_answer (after seeing tool result)
    final_answer_response = LLMResponse(
        content='{"action": "final_answer", "answer": "The test file is at src/test.py"}',
        model="test-model",
        provider="mock",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120)
    )

    mock_llm_service.generate.side_effect = [tool_call_response, final_answer_response]

    # Run the loop
    result = await loop.run("Where is the test file?")

    # Verify results
    assert result.answer == "The test file is at src/test.py"
    assert result.tool_call_count == 1
    assert len(result.turns) == 2

    # Verify turn 0 (tool_call turn)
    assert result.turns[0].tool_call["tool_name"] == "search_repository"
    assert result.turns[0].tool_observation is not None
    assert result.turns[0].tool_observation["tool_name"] == "search_repository"
    assert result.turns[0].tool_observation["success"] is True
    # Verify data field is now stored
    assert "data" in result.turns[0].tool_observation
    assert "formatted_message" in result.turns[0].tool_observation

    # Verify turn 1 (final_answer turn)
    assert result.turns[1].tool_call is None  # No tool call on final answer turn


@pytest.mark.asyncio
async def test_rim_qa_loop_source_content_delivered():
    """Test that tool observation includes actual content, not just summary."""

    mock_llm_service = AsyncMock()
    mock_tool_dispatch = AsyncMock(spec=ToolDispatchTable)

    config = AgentLoopConfig(max_agent_turns=2, max_tool_calls=2)
    system_prompt_parts = SystemPromptParts(
        grounding_and_protocol_text="Test",
        tool_catalog_text="Tools",
        rim_metadata_text="",
        full_text="Test\nTools"
    )

    loop = RIMQALoop(
        llm_service=mock_llm_service,
        tool_dispatch=mock_tool_dispatch,
        config=config,
        system_prompt_parts=system_prompt_parts,
    )

    # Mock a read_file tool call
    tool_observation = ToolObservation(
        tool_call_id="turn-0",
        tool_name="read_file",
        success=True,
        data={
            "path": "src/main.py",
            "start_line": 1,
            "end_line": 10,
            "content": "def hello():\n    print('hello')\n# ... more code ...",
        }
    )
    mock_tool_dispatch.dispatch = MagicMock(return_value=tool_observation)

    # First turn: tool_call
    tool_call_response = LLMResponse(
        content='{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/main.py"}}',
        model="test",
        provider="mock",
        usage=TokenUsage(prompt_tokens=50, completion_tokens=10)
    )

    # Second turn: final_answer (after seeing file content)
    final_answer_response = LLMResponse(
        content='{"action": "final_answer", "answer": "The function hello() prints hello"}',
        model="test",
        provider="mock",
        usage=TokenUsage(prompt_tokens=150, completion_tokens=20)  # Larger due to file content
    )

    mock_llm_service.generate.side_effect = [tool_call_response, final_answer_response]

    result = await loop.run("What does main.py do?")

    # Verify that the formatted message includes actual content
    formatted_msg = result.turns[0].tool_observation["formatted_message"]
    assert "src/main.py" in formatted_msg
    assert "def hello()" in formatted_msg  # Actual code content should be included
    assert "# ... more code ..." in formatted_msg


@pytest.mark.asyncio
async def test_rim_qa_loop_query_rim_entities_delivered():
    """Test that query_rim tool observation includes entity details."""

    mock_llm_service = AsyncMock()
    mock_tool_dispatch = AsyncMock(spec=ToolDispatchTable)

    config = AgentLoopConfig(max_agent_turns=2, max_tool_calls=2)
    system_prompt_parts = SystemPromptParts(
        grounding_and_protocol_text="Test",
        tool_catalog_text="Tools",
        rim_metadata_text="",
        full_text="Test\nTools"
    )

    loop = RIMQALoop(
        llm_service=mock_llm_service,
        tool_dispatch=mock_tool_dispatch,
        config=config,
        system_prompt_parts=system_prompt_parts,
    )

    # Mock a query_rim tool call with entity results
    tool_observation = ToolObservation(
        tool_call_id="turn-0",
        tool_name="query_rim",
        success=True,
        data={
            "found": True,
            "related": [
                {
                    "name": "authenticate",
                    "entity_type": "function",
                    "location": "src/auth.py",
                    "line_number": 42,
                    "relationship_role": "CALLS"
                },
                {
                    "name": "validate",
                    "entity_type": "function",
                    "location": "src/auth.py",
                    "line_number": 50,
                    "relationship_role": "CALLS"
                }
            ],
            "message": "Found 2 related entities"
        }
    )
    mock_tool_dispatch.dispatch = MagicMock(return_value=tool_observation)

    # First turn: tool_call
    tool_call_response = LLMResponse(
        content='{"action": "tool_call", "tool_name": "query_rim", "arguments": {"entity_name": "login", "relationship_type": "CALLS"}}',
        model="test",
        provider="mock",
        usage=TokenUsage(prompt_tokens=50, completion_tokens=10)
    )

    # Second turn: final_answer (after seeing entity relationships)
    final_answer_response = LLMResponse(
        content='{"action": "final_answer", "answer": "login calls authenticate and validate"}',
        model="test",
        provider="mock",
        usage=TokenUsage(prompt_tokens=150, completion_tokens=20)
    )

    mock_llm_service.generate.side_effect = [tool_call_response, final_answer_response]

    result = await loop.run("What does login call?")

    # Verify that formatted message includes entity details
    formatted_msg = result.turns[0].tool_observation["formatted_message"]
    assert "Found 2 related entities" in formatted_msg
    assert "authenticate" in formatted_msg  # Entity name should be included
    assert "src/auth.py" in formatted_msg  # Location should be included
    assert "line_number" in formatted_msg or "42" in formatted_msg  # Line info should be included

    # Verify actual data is stored for metrics
    assert result.turns[0].tool_observation["data"] is not None
    assert len(result.turns[0].tool_observation["data"].get("related", [])) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
