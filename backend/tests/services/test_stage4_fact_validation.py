"""
Tests for Stage 4: Final Answer Fact Validation Against Tool Results.

Validates:
1. Final answer supported by successful tool results passes validation cleanly.
2. Final answer contradicted by a file-read result is intercepted or caveated.
3. Incorrect claim that a file, symbol, dependency, or database does not exist is rejected when observations found it.
4. Absence claim following a failed search is not accepted as proof of absence.
5. Absence claim following an empty but incomplete/narrow search is handled properly.
6. Claims based on truncated or partial file reads receive appropriate transparent notice caveats.
7. Claims unsupported but not contradicted are preserved without false contradiction.
8. Recovery when additional investigation can resolve a claim (re-prompting model for correction).
9. Graceful handling when verification remains inconclusive (appending caveat disclaimers when retries exhausted).
10. Multiple claims where only one is contradicted.
11. Valid plain-text and Markdown answers preserved without corruption.
12. Valid JSON/Hermes final-answer parsing preserved.
13. Prevention of raw tool-call leakage.
14. Prevention of infinite verification/retry loops (max 2 retries).
15. Backward compatibility and regression across Stages 1, 2, and 3.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agent.loop.contracts import AgentLoopConfig, StopReason
from backend.ai.schemas import LLMResponse, TokenUsage
from backend.services.qa_loop import QALoop, QALoopResult, QALoopTurn
from backend.services.qa_protocol import SystemPromptParts


@pytest.fixture
def qa_loop_instance():
    llm_service = MagicMock()
    llm_service.providers = [MagicMock(provider_name="groq")]
    tool_dispatch = MagicMock()
    config = AgentLoopConfig(max_agent_turns=6, max_tool_calls=10)
    system_parts = SystemPromptParts(
        grounding_and_protocol_text="Grounding rules",
        tool_catalog_text="Tool catalog",
        rim_metadata_text="RIM metadata",
        full_text="System Prompt Context",
    )
    loop = QALoop(
        llm_service=llm_service,
        tool_dispatch=tool_dispatch,
        config=config,
        system_prompt_parts=system_parts,
        model="openai/gpt-oss-120b",
        provider="groq",
    )
    return loop


@pytest.fixture
def mock_qwen_loop():
    llm_service = MagicMock()
    tool_dispatch = MagicMock()
    config = AgentLoopConfig(max_agent_turns=6, max_tool_calls=10)
    system_parts = SystemPromptParts(
        grounding_and_protocol_text="Grounding rules",
        tool_catalog_text="Tool catalog",
        rim_metadata_text="RIM metadata",
        full_text="System Prompt Context",
    )
    loop = QALoop(
        llm_service=llm_service,
        tool_dispatch=tool_dispatch,
        config=config,
        system_prompt_parts=system_parts,
        model="qwen3:4b-instruct",
        provider="ollama",
    )
    return loop


class TestFactValidationUnits:
    """Direct unit tests for QALoop fact validation methods."""

    def test_supported_final_answer_passes_validation(self, qa_loop_instance):
        """A final answer consistent with observations passes validation cleanly."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "backend/models.py"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {"path": "backend/models.py", "raw_text": "class User(Base): pass", "is_truncated": False},
                    },
                )
            ],
        )

        answer = "The User model is defined in `backend/models.py` using SQLAlchemy Base."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)

        assert is_valid is True
        assert feedback is None
        assert "User model is defined" in caveated
        assert "Verification Caveat" not in caveated

    def test_absence_claim_contradicted_by_search_results(self, qa_loop_instance):
        """Claiming that PostgreSQL or Redis does not exist when search found it is rejected."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "search_code", "arguments": {"query": "postgresql"}},
                    tool_observation={
                        "tool_name": "search_code",
                        "success": True,
                        "data": [
                            {"file": "backend/database.py", "line": 15, "snippet": "create_engine('postgresql://user:pass@localhost/db')"}
                        ],
                    },
                )
            ],
        )

        answer = "This repository does not use PostgreSQL database."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)

        assert is_valid is False
        assert "conflict with tool observations" in feedback
        assert "Verification Caveat" in caveated

    def test_absence_claim_following_failed_search_is_unsupported(self, qa_loop_instance):
        """A failed search call cannot be treated as evidence of absence."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "search_code", "arguments": {"query": "qdrant"}},
                    tool_observation={
                        "tool_name": "search_code",
                        "success": False,
                        "error": {"type": "search_error", "message": "Connection timed out"},
                        "data": None,
                    },
                )
            ],
        )

        answer = "There is no Qdrant vector database in this codebase."
        is_valid, feedback, _ = qa_loop_instance._validate_final_answer_against_evidence(answer, result)

        assert is_valid is False
        assert "Failed or errored searches cannot be treated as proof of absence" in feedback

    def test_absence_claim_without_any_retrieval_is_unsupported(self, qa_loop_instance):
        """Making sweeping absence claims without executing any retrieval tool is rejected."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[],
        )

        answer = "There are no authentication tokens or JWT implementation in this repository."
        is_valid, feedback, _ = qa_loop_instance._validate_final_answer_against_evidence(answer, result)

        assert is_valid is False
        assert "No retrieval was performed to verify this absence claim" in feedback

    def test_absence_claim_supported_when_search_succeeded_with_zero_results(self, qa_loop_instance):
        """When an exhaustive search succeeded and returned 0 results, absence claim is justified."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "search_code", "arguments": {"query": "redis"}},
                    tool_observation={
                        "tool_name": "search_code",
                        "success": True,
                        "data": [],
                    },
                )
            ],
        )

        answer = "There is no Redis cache configured in this repository."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)

        assert is_valid is True
        assert feedback is None
        assert "Verification Caveat" not in caveated

    def test_truncated_file_read_appends_transparent_notice(self, qa_loop_instance):
        """When the answer makes sweeping completeness claims on a truncated file, a notice is attached."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "src/big_file.py"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {
                            "path": "src/big_file.py",
                            "raw_text": "class Service:\n    pass\n",
                            "is_truncated": True,
                            "remaining_lines": 150,
                        },
                    },
                )
            ],
        )

        answer = "Here is the complete and entire definition of `src/big_file.py`."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)

        assert is_valid is True
        assert "> [!NOTE]" in caveated
        assert "partially read due to line limits" in caveated

    def test_symbol_nonexistence_contradicted_by_get_symbol(self, qa_loop_instance):
        """Claiming a symbol doesn't exist when get_symbol found it triggers contradiction."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "get_symbol", "arguments": {"name": "AuthService"}},
                    tool_observation={
                        "tool_name": "get_symbol",
                        "success": True,
                        "data": [
                            {"name": "AuthService", "file": "services/auth.py", "line_start": 10}
                        ],
                    },
                )
            ],
        )
        answer = "The repository does not contain AuthService."
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)

        assert is_valid is False
        assert "AuthService" in feedback
        assert "services/auth.py" in feedback

    def test_multiple_claims_where_only_one_is_contradicted(self, qa_loop_instance):
        """When multiple claims are made, but only one is contradicted, feedback notes the contradiction without wiping the valid claims."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "backend/auth.py"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {"path": "backend/auth.py", "raw_text": "class AuthService: pass\nimport jwt", "is_truncated": False},
                    },
                )
            ],
        )

        answer = (
            "1. The project implements JWT authentication in `backend/auth.py`.\n"
            "2. There is no AuthService in the codebase."
        )
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(answer, result)

        assert is_valid is False
        assert "AuthService" in feedback
        # The valid claim is preserved in the caveated answer
        assert "JWT authentication in `backend/auth.py`" in caveated
        assert "Verification Caveat" in caveated

    def test_valid_markdown_and_plain_text_preserved(self, qa_loop_instance):
        """Rich markdown formatting (headings, code blocks, lists) is preserved cleanly."""
        result = QALoopResult(
            answer="",
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=[
                QALoopTurn(
                    turn_index=1,
                    tool_call={"tool_name": "read_file", "arguments": {"path": "app.py"}},
                    tool_observation={
                        "tool_name": "read_file",
                        "success": True,
                        "data": {"path": "app.py", "raw_text": "app = FastAPI()", "is_truncated": False},
                    },
                )
            ],
        )

        markdown_answer = """### Architecture Overview

- **Framework**: FastAPI
- **Entry**: `app.py`

```python
app = FastAPI()
```
"""
        is_valid, feedback, caveated = qa_loop_instance._validate_final_answer_against_evidence(markdown_answer, result)
        assert is_valid is True
        assert "### Architecture Overview" in caveated
        assert "```python" in caveated

    def test_valid_json_final_answer_parsing_preserved(self, qa_loop_instance):
        """JSON-wrapped answers are parsed and validated cleanly."""
        raw_json = '{"action": "final_answer", "answer": "The application uses FastAPI in app.py."}'
        parsed = qa_loop_instance.protocol_adapter.parse_final_synthesis(raw_json)
        assert parsed == "The application uses FastAPI in app.py."

        result = QALoopResult(answer="", stop_reason=StopReason.COMPLETED_FOR_VERIFICATION, turns=[])
        is_valid, _, caveated = qa_loop_instance._validate_final_answer_against_evidence(parsed, result)
        assert is_valid is True
        assert caveated == "The application uses FastAPI in app.py."

    def test_raw_tool_call_xml_not_leaked(self, qa_loop_instance):
        """Synthesis parsing and validation strips any raw tool call XML tags."""
        raw_xml = '<tool_call><invoke name="final_answer"><parameter name="answer">FastAPI is configured.</parameter></invoke></tool_call>'
        parsed = qa_loop_instance.protocol_adapter.parse_final_synthesis(raw_xml)
        assert "<tool_call>" not in parsed
        assert "<invoke" not in parsed
        assert parsed == "FastAPI is configured."


class TestQALoopFactValidationFlow:
    """Integration tests running QALoop with validation gates, recovery, and retry bounds."""

    @pytest.mark.asyncio
    async def test_contradiction_prompts_model_and_recovers_on_second_turn(self, mock_qwen_loop):
        """
        When the model outputs a contradicted claim, it receives verification feedback.
        When the model provides the corrected claim on the next turn, it completes successfully.
        """
        mock_observation = MagicMock(
            success=True,
            error=None,
            data=[{"file": "backend/config.py", "line": 5, "snippet": "REDIS_URL = 'redis://localhost:6379'"}]
        )
        mock_qwen_loop.tool_dispatch.dispatch = MagicMock(return_value=mock_observation)
        mock_qwen_loop.tool_dispatch.specs = MagicMock(return_value=[])

        # Sequence:
        # Turn 0: tool call search_code(redis) -> succeeds and finds REDIS_URL
        # Turn 1: model outputs false claim "There is no Redis configured" -> REJECTED by validation
        # Turn 2: model corrects itself "Redis is configured via REDIS_URL in backend/config.py" -> ACCEPTED
        resp0 = LLMResponse(
            content='<tool_call><invoke name="search_code"><parameter name="query">redis</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        resp1_false = LLMResponse(
            content='<tool_call><invoke name="final_answer"><parameter name="answer">There is no Redis database configured in this repository.</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=150, completion_tokens=30, total_tokens=180),
        )
        resp2_corrected = LLMResponse(
            content='<tool_call><invoke name="final_answer"><parameter name="answer">Redis is configured in `backend/config.py` with `REDIS_URL`.</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=200, completion_tokens=30, total_tokens=230),
        )

        mock_qwen_loop.llm_service.generate = AsyncMock(side_effect=[resp0, resp1_false, resp2_corrected])

        result = await mock_qwen_loop.run("Is Redis used?")

        assert result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
        assert "Redis is configured in `backend/config.py`" in result.answer
        assert "Verification Caveat" not in result.answer
        # Verification retry count was recorded
        assert mock_qwen_loop.verification_retries == 1

    @pytest.mark.asyncio
    async def test_infinite_retry_loop_prevented_by_max_verification_retries(self, mock_qwen_loop):
        """
        If the model stubbornly repeats an unsupported or contradicted claim,
        the loop must NOT spin infinitely. After max_verification_retries (2),
        it terminates with a structured caveat.
        """
        # No retrieval performed; model immediately gives unverified absence claim
        stubborn_resp = LLMResponse(
            content='<tool_call><invoke name="final_answer"><parameter name="answer">There is no authentication anywhere in this project.</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
        )

        mock_qwen_loop.llm_service.generate = AsyncMock(return_value=stubborn_resp)

        result = await mock_qwen_loop.run("Does the project have auth?")

        # Must terminate gracefully without exceeding turns
        assert result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
        assert mock_qwen_loop.verification_retries == 2
        # Caveat attached to answer
        assert "Verification Caveat" in result.answer
        assert "Absence claim unverified" in result.answer

    @pytest.mark.asyncio
    async def test_tool_limit_synthesis_runs_fact_validation_with_caveats(self, mock_qwen_loop):
        """
        When tool limits are reached and final synthesis turn runs,
        fact validation applies and appends caveats if unsupported claims are made.
        """
        mock_observation = MagicMock(
            success=True,
            error=None,
            data=[{"file": "server.py", "line": 10, "snippet": "import psycopg2"}]
        )
        mock_qwen_loop.tool_dispatch.dispatch = MagicMock(return_value=mock_observation)
        mock_qwen_loop.tool_dispatch.specs = MagicMock(return_value=[])

        mock_qwen_loop.config.max_tool_calls = 1

        resp0_tool = LLMResponse(
            content='<tool_call><invoke name="search_code"><parameter name="query">database</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        resp1_tool_exceeded = LLMResponse(
            content='<tool_call><invoke name="search_code"><parameter name="query">postgres</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        resp_synthesis = LLMResponse(
            content="Summary: The project has no postgres database.",
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=150, completion_tokens=25, total_tokens=175),
        )

        mock_qwen_loop.llm_service.generate = AsyncMock(side_effect=[resp0_tool, resp1_tool_exceeded, resp_synthesis])

        result = await mock_qwen_loop.run("What database is used?")

        assert result.stop_reason == StopReason.MAX_TOOL_CALLS_EXCEEDED
        assert "Summary: The project has no postgres database." in result.answer
        assert "Verification Caveat" in result.answer
