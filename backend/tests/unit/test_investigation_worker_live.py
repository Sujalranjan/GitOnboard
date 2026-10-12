"""
Integration test running real LocalInvestigationWorker against Ollama with real repository tools.
"""
import pytest
import os
from backend.agent.investigation.schemas import InvestigationSubtask, SubtaskStatus
from backend.agent.investigation.worker import LocalInvestigationWorker
from backend.database import SessionLocal
from backend.repository_tools.tools import RepositoryToolLayer
from backend.services.tool_dispatch import ToolDispatchTable
from backend.ai.service import get_llm_service


@pytest.mark.asyncio
async def test_real_worker_executes_focused_subtask():
    db = SessionLocal()
    try:
        tool_layer = RepositoryToolLayer('Deep-Guard-Integrated-Backend', db=db, analysis_id=5)
        tool_dispatch = ToolDispatchTable(tool_layer)
        llm_service = get_llm_service()

        worker = LocalInvestigationWorker(
            tool_dispatch=tool_dispatch,
            llm_service=llm_service,
            model='qwen3:4b-instruct',
            provider='ollama',
            max_turns=4,
        )

        subtask = InvestigationSubtask(
            id='task_auth_cookie_options',
            title='Inspect Auth Cookie Options',
            description='Read app/Deep-Guard-Backend/utils/authHelpers.js and verify the exact COOKIE_OPTS settings (httpOnly, secure, sameSite, path).',
            target_entities=['app/Deep-Guard-Backend/utils/authHelpers.js'],
            expected_output='Exact cookie flags configured for access and refresh tokens.',
        )

        result = await worker.execute_subtask(subtask)

        assert result.status == SubtaskStatus.COMPLETED
        assert result.turn_count >= 1
        assert len(result.files_inspected) >= 1
        assert any("authHelpers.js" in f for f in result.files_inspected)
        assert len(result.findings) >= 1
        assert any("cookie" in f.summary.lower() or "httponly" in (f.code_excerpt or '').lower() or "authhelpers" in f.file_path.lower() for f in result.findings)
    finally:
        db.close()
