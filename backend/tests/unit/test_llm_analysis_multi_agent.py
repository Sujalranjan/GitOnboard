"""
Test end-to-end multi_agent mode in LLMAnalysisService.
"""
import pytest
from unittest.mock import MagicMock
from backend.services.llm_analysis_service import LLMAnalysisService
from backend.repository_tools.tools import RepositoryToolLayer
from backend.agent.loop.contracts import StopReason


@pytest.mark.asyncio
async def test_llm_analysis_service_multi_agent_wiring():
    mock_tool_layer = MagicMock(spec=RepositoryToolLayer)
    mock_tool_layer.db = None
    mock_tool_layer.analysis_id = 5
    mock_tool_layer.repo_name = "test_repo"

    mock_llm = MagicMock()
    # Mock planning output
    mock_llm.generate = MagicMock()

    service = LLMAnalysisService(
        llm_service=mock_llm,
        tool_layer=mock_tool_layer,
        mode="multi_agent",
    )

    # Patch orchestrator run directly to verify call delegation
    from backend.agent.investigation.orchestrator import InvestigationOrchestrator
    from backend.services.qa_loop import QALoopResult

    orig_run = InvestigationOrchestrator.run
    async def mock_orch_run(self, query, repo_summary=""):
        return QALoopResult(
            answer="Multi-agent verified answer",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
        )

    InvestigationOrchestrator.run = mock_orch_run
    try:
        res = await service.run("Test query")
        assert res.answer == "Multi-agent verified answer"
        assert res.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
    finally:
        InvestigationOrchestrator.run = orig_run
