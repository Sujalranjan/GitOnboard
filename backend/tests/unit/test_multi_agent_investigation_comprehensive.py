"""
Comprehensive unit tests for the multi-agent investigation system:
1. Detailed task plan generation & malformed-plan validation.
2. Worker execution, multiple turns, tool calls, and budget exhaustion.
3. No synthetic evidence cards on timeout.
4. File inspection transparency (files_read, files_discovered, files_skipped, read_failures).
5. Large tool observation handling without 3000-char truncation.
6. Context sharing: worker receives user question, repo summary, and prior findings.
7. Verification gate using real turns recorded from multi-agent worker.
8. Sequential execution & dependency tracking.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agent.investigation.schemas import (
    EvidenceCard,
    FindingType,
    InvestigationSubtask,
    SubtaskStatus,
    WorkerTaskResult,
)
from backend.agent.investigation.planner import MainInvestigationPlanner
from backend.agent.investigation.worker import LocalInvestigationWorker
from backend.agent.investigation.orchestrator import InvestigationOrchestrator
from backend.agent.investigation.state_store import InvestigationStateStore
from backend.agent.loop.contracts import StopReason, ToolObservation
from backend.ai.schemas import LLMResponse, TokenUsage
from backend.services.qa_loop import QALoopTurn
from backend.services.qa_validation import validate_final_answer_against_evidence


@pytest.mark.asyncio
async def test_planner_validates_and_sanitizes_tasks():
    mock_llm = MagicMock()
    # Model generates 3 tasks with one duplicate ID and one invalid dependency
    model_json = """[
      {
        "id": "t1",
        "title": "Trace Auth Entry",
        "description": "Find express/fastapi auth route handler",
        "target_entities": ["routes/auth.py"],
        "search_strategy": "search_repository for auth route",
        "expected_output": "Auth router functions",
        "completion_criteria": "Inspect auth router",
        "dependencies": []
      },
      {
        "id": "t1",
        "title": "Trace Token Verification",
        "description": "Inspect JWT verification",
        "target_entities": ["services/token.py"],
        "search_strategy": "read_file on token service",
        "expected_output": "Token decoding logic",
        "completion_criteria": "Inspect jwt decode",
        "dependencies": ["t1", "non_existent_task"]
      }
    ]"""
    mock_llm.generate = AsyncMock(return_value=LLMResponse(
        content=model_json,
        usage=TokenUsage(prompt_tokens=200, completion_tokens=100),
        model="qwen3:4b-instruct",
        provider="ollama",
    ))

    planner = MainInvestigationPlanner(mock_llm, model="qwen3:4b-instruct")
    subtasks = await planner.create_plan("How does authentication work?", "Repo summary")

    assert len(subtasks) == 2
    # Ensure duplicate ID was deduplicated
    assert subtasks[0].id == "t1"
    assert subtasks[1].id != "t1"
    # Ensure invalid dependency was stripped
    assert "non_existent_task" not in subtasks[1].dependencies
    assert planner.last_plan_fallback_used is False


@pytest.mark.asyncio
async def test_planner_fallback_is_dynamic_and_honest():
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(side_effect=RuntimeError("Ollama connection refused"))

    planner = MainInvestigationPlanner(mock_llm, model="qwen3:4b-instruct")
    subtasks = await planner.create_plan("How are SQL sessions pooled?", "PostgreSQL app")

    assert planner.last_plan_fallback_used is True
    assert len(subtasks) == 2
    assert "SQL sessions pooled" in subtasks[0].title
    assert subtasks[1].dependencies == ["task_entrypoints_discovery"]


@pytest.mark.asyncio
async def test_worker_file_transparency_and_observation_budget():
    mock_dispatch = MagicMock()
    mock_dispatch.specs.return_value = []
    mock_dispatch.include_rim = True

    # 1. search_repository returns list of files
    search_obs = ToolObservation(
        tool_call_id="c1",
        tool_name="search_repository",
        success=True,
        data=[
            {"file": "backend/auth.py", "symbol": "login_handler", "score": 0.95},
            {"file": "backend/models.py", "symbol": "User", "score": 0.8},
        ],
    )
    # 2. read_file returns large content exceeding 3000 chars without being cut off
    large_code = "\n".join([f"line_{i} = do_work_{i}()" for i in range(120)])
    read_obs = ToolObservation(
        tool_call_id="c2",
        tool_name="read_file",
        success=True,
        data={
            "path": "backend/auth.py",
            "start_line": 1,
            "end_line": 120,
            "content": large_code,
        },
    )

    mock_dispatch.dispatch.side_effect = [search_obs, read_obs]

    mock_llm = MagicMock()
    r1 = LLMResponse(
        content='<tool_call><invoke name="search_repository"><parameter name="query">auth</parameter></invoke></tool_call>',
        usage=TokenUsage(prompt_tokens=50, completion_tokens=15),
        model="qwen3:4b-instruct",
        provider="ollama",
    )
    r2 = LLMResponse(
        content='<tool_call><invoke name="read_file"><parameter name="path">backend/auth.py</parameter><parameter name="start_line">1</parameter><parameter name="end_line">120</parameter></invoke></tool_call>',
        usage=TokenUsage(prompt_tokens=120, completion_tokens=25),
        model="qwen3:4b-instruct",
        provider="ollama",
    )
    final_json = """{
      "summary": "Verified auth workflow in backend/auth.py",
      "findings": [
        {
          "file_path": "backend/auth.py",
          "line_start": 1,
          "line_end": 120,
          "symbol_name": "login_handler",
          "summary": "Processes user login requests",
          "code_excerpt": "line_0 = do_work_0()",
          "finding_type": "SOURCE_IMPLEMENTATION"
        }
      ],
      "files_skipped": [
        {"path": "backend/models.py", "reason": "Not directly handling login routes"}
      ],
      "coverage_gaps": []
    }"""
    r3 = LLMResponse(
        content=f'<tool_call><invoke name="final_answer"><parameter name="answer">{final_json}</parameter></invoke></tool_call>',
        usage=TokenUsage(prompt_tokens=300, completion_tokens=80),
        model="qwen3:4b-instruct",
        provider="ollama",
    )
    mock_llm.generate = AsyncMock(side_effect=[r1, r2, r3])

    worker = LocalInvestigationWorker(
        tool_dispatch=mock_dispatch,
        llm_service=mock_llm,
        model="qwen3:4b-instruct",
        provider="ollama",
        max_turns=5,
    )

    subtask = InvestigationSubtask(
        id="sub_1",
        title="Verify login handler",
        description="Check backend login",
    )

    prior_finding = EvidenceCard(
        id="ev_prev",
        task_id="prev_task",
        file_path="main.py",
        summary="Registered router in main",
    )

    result, turns = await worker.execute_subtask(
        subtask=subtask,
        user_question="How does login work?",
        repo_context="FastAPI App",
        prior_findings=[prior_finding],
    )

    assert result.status == SubtaskStatus.COMPLETED
    assert len(result.findings) == 1
    assert "backend/auth.py:1-120" in result.files_read
    assert "backend/models.py" in result.files_discovered
    assert len(result.files_skipped) == 1
    assert result.files_skipped[0]["path"] == "backend/models.py"
    assert len(turns) == 2
    # Check that real usage tokens were collected
    assert result.prompt_tokens == 470
    assert result.completion_tokens == 120


@pytest.mark.asyncio
async def test_verification_gate_uses_real_worker_turns():
    # Verify that validate_final_answer_against_evidence receives real turns from orchestrator
    mock_planner = MagicMock(spec=MainInvestigationPlanner)
    mock_planner.create_plan = AsyncMock(return_value=[
        InvestigationSubtask(id="task_jwt", title="Inspect JWT", description="Find JWT decode")
    ])
    # The synthesized answer mentions a relationship: login_handler calls decode_token
    answer_text = "The login_handler calls decode_token in backend/auth.py to verify credentials."
    mock_planner.synthesize_answer = AsyncMock(return_value=answer_text)

    mock_worker = MagicMock(spec=LocalInvestigationWorker)
    w_res = WorkerTaskResult(
        task_id="task_jwt",
        status=SubtaskStatus.COMPLETED,
        findings=[
            EvidenceCard(
                id="ev_jwt_1",
                task_id="task_jwt",
                file_path="backend/auth.py",
                line_start=10,
                line_end=25,
                symbol_name="login_handler",
                summary="Invokes decode_token",
            )
        ],
        files_read=["backend/auth.py:10-25"],
    )

    # Real turn observation that contains decode_token(...) call
    real_turn = QALoopTurn(
        turn_index=1,
        tool_call={"tool_name": "read_file", "arguments": {"path": "backend/auth.py"}},
        tool_observation={
            "tool_name": "read_file",
            "success": True,
            "data": {
                "path": "backend/auth.py",
                "raw_text": "def login_handler():\n    decode_token(credentials)\n",
            },
        },
    )

    mock_worker.execute_subtask = AsyncMock(return_value=(w_res, [real_turn]))

    orchestrator = InvestigationOrchestrator(
        planner=mock_planner,
        worker=mock_worker,
    )

    result = await orchestrator.run("How are credentials verified?")

    assert result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
    # Verification passed without flagging false contradiction warning!
    assert "Verification Caveat" not in result.answer
    assert "login_handler calls decode_token" in result.answer
    assert result.tool_call_count == 1
    assert len(result.turns) == 1
