"""
Unit tests for InvestigationOrchestrator and end-to-end multi-agent flow.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agent.investigation.orchestrator import InvestigationOrchestrator
from backend.agent.investigation.planner import MainInvestigationPlanner
from backend.agent.investigation.schemas import (
    EvidenceCard,
    FindingType,
    InvestigationSubtask,
    SubtaskStatus,
    WorkerTaskResult,
)
from backend.agent.investigation.worker import LocalInvestigationWorker
from backend.agent.loop.contracts import StopReason


@pytest.mark.asyncio
async def test_investigation_orchestrator_runs_end_to_end():
    # 1. Mock Planner
    mock_planner = MagicMock(spec=MainInvestigationPlanner)
    mock_planner.create_plan = AsyncMock(return_value=[
        InvestigationSubtask(
            id="t1",
            title="Inspect auth tokens",
            description="Find token generation",
        ),
        InvestigationSubtask(
            id="t2",
            title="Inspect token storage",
            description="Find session tables",
            dependencies=["t1"],
        ),
    ])
    mock_planner.synthesize_answer = AsyncMock(
        return_value="User authentication uses JWT access tokens and rotates refresh tokens in Supabase user_sessions table."
    )

    # 2. Mock Worker
    mock_worker = MagicMock(spec=LocalInvestigationWorker)
    res_t1 = WorkerTaskResult(
        task_id="t1",
        status=SubtaskStatus.COMPLETED,
        files_inspected=["authcontroller.js"],
        findings=[
            EvidenceCard(
                id="ev_1",
                task_id="t1",
                file_path="authcontroller.js",
                summary="Generates access and refresh tokens",
            )
        ],
        discovered_next_steps=["user_sessions table schema"],
    )
    res_t2 = WorkerTaskResult(
        task_id="t2",
        status=SubtaskStatus.COMPLETED,
        files_inspected=["supabase.js"],
        findings=[
            EvidenceCard(
                id="ev_2",
                task_id="t2",
                file_path="supabase.js",
                summary="Stores hashed refresh token in user_sessions",
            )
        ],
    )
    res_t3 = WorkerTaskResult(
        task_id="task_discovered_3",
        status=SubtaskStatus.COMPLETED,
        files_inspected=["schema.sql"],
        findings=[
            EvidenceCard(
                id="ev_3",
                task_id="task_discovered_3",
                file_path="schema.sql",
                summary="user_sessions table schema with refresh_token_hash",
            )
        ],
    )
    mock_worker.execute_subtask = AsyncMock(side_effect=[res_t1, res_t2, res_t3])

    events_received = []

    def on_event(ev):
        events_received.append(ev)

    orchestrator = InvestigationOrchestrator(
        planner=mock_planner,
        worker=mock_worker,
        on_event_callback=on_event,
    )

    result = await orchestrator.run("How are tokens stored and rotated?")

    assert result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
    assert "JWT access tokens" in result.answer
    assert mock_planner.create_plan.called
    assert mock_worker.execute_subtask.call_count >= 2
    assert mock_planner.synthesize_answer.called
    assert any(e["type"] == "plan-created" for e in events_received)
    assert any(e["type"] == "task-update" for e in events_received)
    assert any(e["type"] == "agent-spawn" for e in events_received)
    assert any(e["type"] == "finding-saved" for e in events_received)
