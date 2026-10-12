"""
Unit tests for LocalInvestigationWorker.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agent.investigation.schemas import (
    EvidenceCard,
    InvestigationSubtask,
    SubtaskStatus,
)
from backend.agent.investigation.worker import LocalInvestigationWorker
from backend.ai.schemas import LLMResponse, TokenUsage
from backend.agent.loop.contracts import ToolObservation


@pytest.mark.asyncio
async def test_worker_executes_tool_and_returns_findings():
    mock_dispatch = MagicMock()
    mock_dispatch.specs.return_value = []
    mock_dispatch.include_rim = False
    mock_dispatch.dispatch.return_value = ToolObservation(
        tool_call_id="call_1",
        tool_name="read_file",
        success=True,
        data="const token = jwt.sign(payload, SECRET);",
    )

    # Mock LLM service
    mock_llm = MagicMock()
    # Turn 0: emit tool call
    turn_0_response = LLMResponse(
        content="<tool_call><invoke name=\"read_file\"><parameter name=\"path\">controllers/auth.js</parameter></invoke></tool_call>",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=20),
        model="qwen3:4b-instruct",
        provider="ollama",
    )
    # Turn 1: emit final answer JSON
    final_json = """{
      "summary": "Verified JWT sign in auth.js",
      "findings": [
        {
          "file_path": "controllers/auth.js",
          "line_start": 1,
          "line_end": 20,
          "symbol_name": "createToken",
          "summary": "Signs token using secret",
          "code_excerpt": "const token = jwt.sign(payload, SECRET);",
          "finding_type": "SOURCE_IMPLEMENTATION",
          "discovered_dependencies": []
        }
      ],
      "discovered_next_steps": [],
      "limitations": []
    }"""
    turn_1_response = LLMResponse(
        content=f"<tool_call><invoke name=\"final_answer\"><parameter name=\"answer\">{final_json}</parameter></invoke></tool_call>",
        usage=TokenUsage(prompt_tokens=150, completion_tokens=50),
        model="qwen3:4b-instruct",
        provider="ollama",
    )
    mock_llm.generate = AsyncMock(side_effect=[turn_0_response, turn_1_response])

    worker = LocalInvestigationWorker(
        tool_dispatch=mock_dispatch,
        llm_service=mock_llm,
        model="qwen3:4b-instruct",
        provider="ollama",
        max_turns=3,
    )

    subtask = InvestigationSubtask(
        id="task_test_1",
        title="Check JWT signing",
        description="Verify how JWTs are signed in auth.js",
        target_entities=["controllers/auth.js"],
    )

    result, turns = await worker.execute_subtask(subtask)

    assert result.status == SubtaskStatus.COMPLETED
    assert result.task_id == "task_test_1"
    assert len(result.findings) == 1
    assert result.findings[0].file_path == "controllers/auth.js"
    assert result.findings[0].symbol_name == "createToken"
    assert result.files_inspected == ["controllers/auth.js"]
    assert len(turns) == 1
    assert turns[0].tool_call["tool_name"] == "read_file"
    assert mock_dispatch.dispatch.called


@pytest.mark.asyncio
async def test_worker_budget_exhaustion_never_fabricates_synthetic_evidence():
    mock_dispatch = MagicMock()
    mock_dispatch.specs.return_value = []
    mock_dispatch.include_rim = False
    mock_dispatch.dispatch.return_value = ToolObservation(
        tool_call_id="call_1",
        tool_name="read_file",
        success=False,
        error={"message": "File not found"},
    )

    mock_llm = MagicMock()
    # Emits only tool calls until max_turns
    turn_response = LLMResponse(
        content="<tool_call><invoke name=\"read_file\"><parameter name=\"path\">missing.js</parameter></invoke></tool_call>",
        usage=TokenUsage(prompt_tokens=50, completion_tokens=10),
        model="qwen3:4b-instruct",
        provider="ollama",
    )
    mock_llm.generate = AsyncMock(return_value=turn_response)

    worker = LocalInvestigationWorker(
        tool_dispatch=mock_dispatch,
        llm_service=mock_llm,
        model="qwen3:4b-instruct",
        provider="ollama",
        max_turns=2,
    )

    subtask = InvestigationSubtask(
        id="task_fail_1",
        title="Check missing file",
        description="Verify non-existent file",
    )

    result, turns = await worker.execute_subtask(subtask)

    # Must be marked FAILED because no evidence was verified
    assert result.status == SubtaskStatus.FAILED
    assert len(result.findings) == 0
    assert "Exhausted turn budget" in (result.error or "")
    assert len(result.read_failures) == 2
    assert result.read_failures[0]["path"] == "missing.js"
    assert len(turns) == 2


@pytest.mark.asyncio
async def test_worker_synthesizes_grounded_findings_from_read_files_on_budget_exhaustion():
    mock_dispatch = MagicMock()
    mock_dispatch.specs.return_value = []
    mock_dispatch.include_rim = False
    mock_dispatch.dispatch.return_value = ToolObservation(
        tool_call_id="call_read_1",
        tool_name="read_file",
        success=True,
        data={
            "path": "controllers/authController.js",
            "start_line": 20,
            "end_line": 60,
            "content": "export async function login(req, res) {\n  const user = await supabase.from('users').select('*');\n  const token = createAccessToken(user);\n  return res.json({ token });\n}",
        },
    )

    mock_llm = MagicMock()
    # Emits only tool calls until max_turns without final_answer
    turn_response = LLMResponse(
        content="<tool_call><invoke name=\"read_file\"><parameter name=\"path\">controllers/authController.js</parameter></invoke></tool_call>",
        usage=TokenUsage(prompt_tokens=50, completion_tokens=10),
        model="qwen3:4b-instruct",
        provider="ollama",
    )
    mock_llm.generate = AsyncMock(return_value=turn_response)

    worker = LocalInvestigationWorker(
        tool_dispatch=mock_dispatch,
        llm_service=mock_llm,
        model="qwen3:4b-instruct",
        provider="ollama",
        max_turns=1,
    )

    subtask = InvestigationSubtask(
        id="task_auth_flow",
        title="Trace Login Flow",
        description="Verify how users log in",
    )

    result, turns = await worker.execute_subtask(subtask)

    # Must be COMPLETED because real source code was read and preserved as evidence
    assert result.status == SubtaskStatus.COMPLETED
    assert len(result.findings) == 1
    assert result.findings[0].file_path == "controllers/authController.js"
    assert "controllers/authController.js" in result.findings[0].summary
    assert "createAccessToken" in (result.findings[0].code_excerpt or "")
    assert len(result.files_read) == 1


def test_worker_formats_tool_observations_with_actionable_diagnostics():
    worker = LocalInvestigationWorker(tool_dispatch=MagicMock())

    # 1. get_code_relationships miss
    obs_rel = ToolObservation(
        tool_call_id="c1",
        tool_name="get_code_relationships",
        success=True,
        data={"found": False, "resolution": "ENTITY_NOT_FOUND", "message": "'login' was not found in graph"},
    )
    text_rel = worker._format_tool_obs("get_code_relationships", obs_rel)
    assert "0 relationships resolved" in text_rel
    assert "ENTITY_NOT_FOUND" in text_rel
    assert "Adapt your search" in text_rel

    # 2. search 0 matches
    obs_search = ToolObservation(
        tool_call_id="c2",
        tool_name="search_repository",
        success=True,
        data=[],
    )
    text_search = worker._format_tool_obs("search_repository", obs_search)
    assert "0 matches found" in text_search
    assert "Adaptive Tip" in text_search


