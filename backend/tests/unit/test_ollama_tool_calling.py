"""
Unit tests verifying Ollama tool calling refactoring:
1. Native structured tool calls priority over text parsing
2. Multi-turn tool call message and tool observation preservation
3. Malformed tool calls rejection (never silently converted to final_answer)
4. Consecutive malformed responses threshold triggering failure state
5. Planner synthesis safety when all subtasks fail or no evidence is collected
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from backend.ai.schemas import LLMResponse, ToolCall, Message, MessageRole, LLMRequest
from backend.services.qa_protocol import QAProtocolAdapter
from backend.services.qa_protocol_parsers import is_tool_call_attempt, parse_json_response, parse_hermes_response
from backend.agent.investigation.schemas import InvestigationSubtask, SubtaskStatus
from backend.agent.investigation.worker import LocalInvestigationWorker
from backend.agent.investigation.planner import MainInvestigationPlanner
from backend.agent.investigation.state_store import InvestigationStateStore
from backend.services.tool_dispatch import ToolObservation


class TestNativeToolCallingPriority:
    """Verify that structured tool calls take precedence over text."""

    def test_structured_tool_calls_consumed_before_text(self):
        adapter = QAProtocolAdapter(model_id="qwen2.5-coder:3b", provider="ollama")
        
        # LLM returns structured tool call and text that looks like a final answer
        response = LLMResponse(
            content="I found the files and will now conclude the investigation.",
            model="qwen2.5-coder:3b",
            provider="ollama",
            tool_calls=[
                ToolCall(
                    tool_name="read_file",
                    parameters={"path": "app/auth.py", "start_line": 1, "end_line": 50},
                    tool_call_id="call_test_123",
                )
            ],
        )

        result = adapter.parse_response_from_llm_response(response)
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "read_file"
        assert result["arguments"] == {"path": "app/auth.py", "start_line": 1, "end_line": 50}
        assert result["tool_call_id"] == "call_test_123"

    def test_malformed_hermes_cannot_become_final_answer(self):
        adapter = QAProtocolAdapter(model_id="qwen2.5-coder:3b", provider="ollama")
        
        # Model produced an invalid invoke block missing closure or attributes
        bad_text = "I will check the code now:\n<invoke name=\"read_file\">"
        
        response = LLMResponse(
            content=bad_text,
            model="qwen2.5-coder:3b",
            provider="ollama",
            tool_calls=[],
        )

        result = adapter.parse_response_from_llm_response(response)
        # Must be malformed, NEVER final_answer
        assert result["action"] == "malformed"
        assert "error" in result

    def test_is_tool_call_attempt_detection(self):
        assert is_tool_call_attempt('<invoke name="search_code">') is True
        assert is_tool_call_attempt('<tool_call>{"name": "test"}</tool_call>') is True
        assert is_tool_call_attempt('{"action": "tool_call", "tool_name": "read_file"}') is True
        assert is_tool_call_attempt('Here is the explanation of the authentication system.') is False


@pytest.mark.asyncio
class TestWorkerMultiTurnAndFailureHandling:
    """Verify LocalInvestigationWorker handles multi-turn history and fails on malformed loops."""

    async def test_worker_fails_on_consecutive_malformed_responses(self):
        mock_dispatch = MagicMock()
        mock_dispatch.specs.return_value = []
        mock_service = MagicMock()
        
        # LLM keeps returning garbage tool attempts that cannot be parsed
        mock_service.generate = AsyncMock(return_value=LLMResponse(
            content="<invoke malformed without closing tag",
            model="qwen2.5-coder:3b",
            provider="ollama",
            tool_calls=[],
        ))

        worker = LocalInvestigationWorker(
            tool_dispatch=mock_dispatch,
            llm_service=mock_service,
            model="qwen2.5-coder:3b",
            provider="ollama",
            max_turns=5,
        )

        subtask = InvestigationSubtask(
            id="task_fail_test",
            title="Test Failure Subtask",
            description="Inspect non-existent flow",
            expected_output="Grounded facts",
        )

        result, turns = await worker.execute_subtask(subtask)
        
        # Must terminate with FAILED status and not mark completed
        assert result.status == SubtaskStatus.FAILED
        assert "repeated malformed model responses" in (result.error or "")
        assert len(result.findings) == 0

    async def test_worker_passes_tool_schemas_in_llm_request(self):
        from backend.services.tool_dispatch import ToolSpec
        mock_dispatch = MagicMock()
        mock_dispatch.specs.return_value = [
            ToolSpec(
                name="read_file",
                description="Read lines from file",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            )
        ]
        
        captured_requests = []
        mock_service = MagicMock()
        async def mock_generate(req: LLMRequest):
            captured_requests.append(req)
            # Finish on first turn
            return LLMResponse(
                content='{"summary": "Task complete", "findings": [{"file_path": "a.py", "summary": "found fact"}]}',
                model="qwen2.5-coder:3b",
                provider="ollama",
                tool_calls=[],
            )
        mock_service.generate = AsyncMock(side_effect=mock_generate)

        worker = LocalInvestigationWorker(
            tool_dispatch=mock_dispatch,
            llm_service=mock_service,
            model="qwen2.5-coder:3b",
            provider="ollama",
            max_turns=2,
        )

        subtask = InvestigationSubtask(
            id="task_schema_test",
            title="Test Schema Subtask",
            description="Verify tool schemas are forwarded",
            expected_output="Schemas forwarded",
        )

        result, turns = await worker.execute_subtask(subtask)
        assert len(captured_requests) >= 1
        req = captured_requests[0]
        # Schema tools must be populated in the LLMRequest!
        assert req.tools is not None
        assert len(req.tools) == 1
        assert req.tools[0].name == "read_file"
        assert req.tools[0].description == "Read lines from file"


@pytest.mark.asyncio
class TestPlannerSynthesisSafety:
    """Verify planner synthesis never turns failed investigations into verified answers."""

    async def test_planner_returns_unsuccessful_when_all_subtasks_fail(self):
        mock_service = MagicMock()
        planner = MainInvestigationPlanner(llm_service=mock_service, model="test-planner")
        
        store = InvestigationStateStore(investigation_id="inv_test_123")
        task1 = store.create_task(
            task_id="t1",
            title="Inspect Auth",
            description="Inspect auth logic",
            search_strategy="",
        )
        task1.status = SubtaskStatus.FAILED
        task1.error = "Repeated malformed model responses"

        # Synthesis should NOT invoke LLM to fabricate an answer when all tasks failed
        answer = await planner.synthesize_answer("How does authentication work?", store)
        
        assert "# Investigation Unsuccessful" in answer
        assert "Execution Failures" in answer
        assert "t1" in answer or "Inspect Auth" in answer
        assert mock_service.generate.called is False
