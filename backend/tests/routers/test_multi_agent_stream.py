"""
Integration test for the /api/llm/analyze/stream endpoint with investigation_mode='multi_agent'.
Verifies that:
1. Multi-agent mode can be specified in AnalyzeRequest.
2. The endpoint returns a streaming response.
3. Event stream includes agent-spawn, plan-created, task-update, and final-answer events.
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.qa_loop import QALoopResult
from backend.agent.loop.contracts import StopReason
from backend.models.user import User
from backend.models.repository import Repository, Analysis


@pytest.mark.asyncio
async def test_analyze_stream_multi_agent_events():
    from backend.routers.llm import analyze_repository_stream, AnalyzeRequest

    # Setup mocks
    mock_db = MagicMock()
    mock_user = User(id=1, email="test@example.com")
    
    # Mock repo & analysis
    mock_repo = Repository(
        id=1,
        user_id=1,
        url="https://github.com/org/repo.git",
        repository_hash="test-hash-123",
    )
    mock_analysis = Analysis(
        id=10,
        repository_id=1,
        status="Completed",
    )

    def mock_query(model):
        q = MagicMock()
        if model == Repository:
            q.filter.return_value.first.return_value = mock_repo
        elif model == Analysis:
            q.filter.return_value.order_by.return_value.first.return_value = mock_analysis
        return q

    mock_db.query.side_effect = mock_query

    # Mock build_analysis_service
    mock_analysis_service = MagicMock()
    
    async def mock_run(query: str):
        # Simulate orchestrator emitting events via the on_turn_callback
        cb = mock_analysis_service._callback
        if cb:
            await cb({
                "type": "agent-spawn",
                "agent_id": "planner-1",
                "role": "Lead Planner & Synthesizer",
                "model": "cloud-main",
                "is_local": False,
                "status": "running",
            })
            await cb({
                "type": "plan-created",
                "tasks": [
                    {
                        "id": "task-1",
                        "title": "Analyze architecture",
                        "description": "Inspect structure",
                        "status": "pending",
                        "assigned_agent": "worker-1",
                    }
                ],
            })
            await cb({
                "type": "agent-spawn",
                "agent_id": "worker-1",
                "role": "Local Repository Scout",
                "model": "qwen3:4b-instruct",
                "is_local": True,
                "status": "running",
                "current_task_id": "task-1",
            })
            await cb({
                "type": "task-update",
                "task_id": "task-1",
                "status": "completed",
                "evidence_count": 1,
            })
            await cb({
                "type": "finding-saved",
                "finding": {
                    "id": "ev-1",
                    "file_path": "src/main.py",
                    "summary": "Main entry point discovered",
                    "task_id": "task-1",
                },
            })

        return QALoopResult(
            answer="Multi-agent investigation concluded successfully.",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            tool_call_count=2,
            turns=[],
        )

    mock_analysis_service.run = mock_run

    def mock_build_service(*args, **kwargs):
        mock_analysis_service._callback = kwargs.get("on_turn_callback")
        return mock_analysis_service

    request = AnalyzeRequest(
        query="Explain system architecture",
        repo_hash="test-hash-123",
        model="qwen3:4b-instruct",
        show_tool_details=True,
        investigation_mode="multi_agent",
    )

    with patch("backend.routers.llm.build_analysis_service", side_effect=mock_build_service), \
         patch("backend.routers.llm.build_repository_context", AsyncMock(return_value="repo context")), \
         patch("backend.routers.llm.resolve_repo_root", return_value="f:/repo"):

        response = await analyze_repository_stream(
            request=request,
            current_user=mock_user,
            db=mock_db,
        )

        assert response.status_code == 200
        assert response.media_type == "text/event-stream"

        # Consume the streaming response chunks
        body_events = []
        async for chunk in response.body_iterator:
            chunk_str = chunk if isinstance(chunk, str) else chunk.decode("utf-8")
            for line in chunk_str.strip().split("\n"):
                if line.startswith("data: "):
                    event_data = json.loads(line[len("data: "):])
                    body_events.append(event_data)

        event_types = [e.get("type") for e in body_events]

        # Verify key SSE lifecycle events were propagated correctly
        assert "user-query" in event_types
        assert "agent-spawn" in event_types
        assert "plan-created" in event_types
        assert "task-update" in event_types
        assert "finding-saved" in event_types
        assert "final-answer" in event_types
        assert "completed" in event_types

        # Verify final answer content
        final_answer_event = next(e for e in body_events if e.get("type") == "final-answer")
        assert "Multi-agent investigation concluded successfully." in final_answer_event["content"]
