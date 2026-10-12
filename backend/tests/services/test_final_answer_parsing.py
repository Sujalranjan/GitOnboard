"""
Tests for Stage 1: Fix Final-Answer Parsing and Termination.

Validates:
1. Plain-text and Markdown synthesis parsing in final turns.
2. Prevention of unexecuted tool calls or raw XML/JSON envelopes leaking into user's final answer.
3. Recovery of usable partial answer text when a model response is truncated.
4. Handling of empty responses and synthesis fallback generation from observations.
5. Preservation of valid tool calls during normal turn parsing.
6. Maximum tool-call budget exhaustion correctly synthesizing and terminating without tool leakage.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agent.loop.contracts import AgentLoopConfig, StopReason
from backend.ai.schemas import LLMRequest, LLMResponse, MessageRole, TokenUsage
from backend.services.qa_loop import QALoop
from backend.services.qa_protocol import QAProtocolAdapter, SystemPromptParts


class TestFinalAnswerParsingProtocol:
    """Direct tests for QAProtocolAdapter.parse_final_synthesis."""

    @pytest.fixture
    def adapter_local_qwen(self):
        return QAProtocolAdapter(model_id="qwen3:4b-instruct")

    @pytest.fixture
    def adapter_cloud(self):
        return QAProtocolAdapter(model_id="openai/gpt-oss-120b", provider="groq")

    def test_plain_markdown_preserved(self, adapter_local_qwen):
        """Markdown with headings, bullet points, and code blocks is preserved cleanly."""
        markdown_text = """### System Architecture

The authentication flow is composed of:
1. `AuthController` handling incoming requests.
2. Token generation using `jwt.sign`.
3. Middleware verification in `auth.ts`.

```python
def verify_token(token: str):
    return jwt.decode(token, SECRET)
```
"""
        result = adapter_local_qwen.parse_final_synthesis(markdown_text)
        assert "### System Architecture" in result
        assert "AuthController" in result
        assert "def verify_token" in result

    def test_json_wrapped_final_answer_extracted(self, adapter_local_qwen):
        """JSON {"action": "final_answer", "answer": "..."} has its answer extracted."""
        raw = '{"action": "final_answer", "answer": "The database uses PostgreSQL via SQLAlchemy ORM."}'
        result = adapter_local_qwen.parse_final_synthesis(raw)
        assert result == "The database uses PostgreSQL via SQLAlchemy ORM."

    def test_hermes_xml_final_answer_extracted(self, adapter_local_qwen):
        """Hermes XML <invoke name="final_answer"><parameter name="answer">...</parameter> is parsed."""
        raw = """<tool_call>
<invoke name="final_answer">
<parameter name="answer">
Authentication is handled via JWT tokens refreshed every 15 minutes.
</parameter>
</invoke>
</tool_call>"""
        result = adapter_local_qwen.parse_final_synthesis(raw)
        assert result == "Authentication is handled via JWT tokens refreshed every 15 minutes."

    def test_unexecuted_hermes_tool_call_is_not_leaked(self, adapter_local_qwen):
        """A raw unexecuted Hermes tool call with no answer text returns empty string."""
        raw = """<tool_call>
<invoke name="read_file">
<parameter name="path">app/Deep-Guard-ML-Engine/app/services/model.py</parameter>
<parameter name="start_line">51</parameter>
<parameter name="end_line">100</parameter>
</invoke>
</tool_call>"""
        result = adapter_local_qwen.parse_final_synthesis(raw)
        # Must NOT leak tool call arguments or parameter names
        assert "read_file" not in result
        assert "app/Deep-Guard-ML-Engine" not in result
        assert result == ""

    def test_unexecuted_json_tool_call_is_not_leaked(self, adapter_cloud):
        """A raw unexecuted JSON tool call returns empty string."""
        raw = '{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/main.py", "start_line": 1, "end_line": 50}}'
        result = adapter_cloud.parse_final_synthesis(raw)
        assert result == ""

    def test_leading_explanation_before_tool_call_retained(self, adapter_local_qwen):
        """If the model wrote useful explanation before an unexecuted tool call, explanation is preserved."""
        raw = """Based on our analysis, the project uses Express router for authentication.
Here is the file structure:
- `/routes/auth.js`
- `/controllers/auth.js`

<tool_call>
<invoke name="read_file">
<parameter name="path">app/routes/auth.js</parameter>
</invoke>
</tool_call>"""
        result = adapter_local_qwen.parse_final_synthesis(raw)
        assert "Based on our analysis, the project uses Express router" in result
        assert "`/routes/auth.js`" in result
        # Tool call envelope and tags should be cleanly stripped
        assert "<tool_call>" not in result
        assert "<invoke" not in result
        assert "<parameter" not in result

    def test_truncated_tool_call_stripped_safely(self, adapter_local_qwen):
        """Truncated XML tool call at the end of response is stripped, keeping prior text."""
        raw = """The system requires two environment variables: `DATABASE_URL` and `JWT_SECRET`.

<tool_call>
<invoke name="read_file">
<parameter name="path">config/en"""
        result = adapter_local_qwen.parse_final_synthesis(raw)
        assert "The system requires two environment variables: `DATABASE_URL` and `JWT_SECRET`." in result
        assert "<tool_call>" not in result
        assert "config/en" not in result

    def test_empty_and_whitespace_responses(self, adapter_local_qwen):
        """Empty strings and whitespace return empty string cleanly."""
        assert adapter_local_qwen.parse_final_synthesis("") == ""
        assert adapter_local_qwen.parse_final_synthesis("   \n\t  ") == ""


class TestTurnByTurnToolCallingPreservation:
    """Verify that normal turn-by-turn tool calling is completely preserved."""

    def test_valid_hermes_tool_call_parsed(self):
        adapter = QAProtocolAdapter(model_id="qwen3:4b-instruct")
        raw = """<tool_call>
<invoke name="read_file">
<parameter name="path">src/app.py</parameter>
<parameter name="start_line">10</parameter>
<parameter name="end_line">30</parameter>
</invoke>
</tool_call>"""
        parsed = adapter.parse_response(raw)
        assert parsed["action"] == "tool_call"
        assert parsed["tool_name"] == "read_file"
        assert parsed["arguments"]["path"] == "src/app.py"
        assert parsed["arguments"]["start_line"] == "10"

    def test_valid_json_tool_call_parsed(self):
        adapter = QAProtocolAdapter(model_id="gpt-oss-120b", provider="groq")
        raw = '{"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "auth"}}'
        parsed = adapter.parse_response(raw)
        assert parsed["action"] == "tool_call"
        assert parsed["tool_name"] == "search_repository"
        assert parsed["arguments"]["query"] == "auth"


class TestQALoopMaxToolCallsTerminationAndFallback:
    """End-to-end unit tests on QALoop verifying budget termination and synthesis fallback."""

    @pytest.fixture
    def mock_loop(self):
        llm_service = MagicMock()
        tool_dispatch = MagicMock()
        config = AgentLoopConfig(max_turns=10, max_tool_calls=2)
        system_parts = SystemPromptParts(
            grounding_and_protocol_text="Grounding",
            tool_catalog_text="Catalog",
            rim_metadata_text="",
            full_text="System Prompt",
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

    @pytest.mark.asyncio
    async def test_tool_limit_reached_triggers_synthesis_turn(self, mock_loop):
        """When max_tool_calls is reached, synthesis turn is called with pure markdown prompt."""
        # Setup tool dispatch return
        mock_observation = MagicMock(success=True, error=None, data=["found symbol Foo"])
        mock_loop.tool_dispatch.dispatch = MagicMock(return_value=mock_observation)
        mock_loop.tool_dispatch.specs = MagicMock(return_value=[])

        # LLM sequence:
        # Turn 1: tool_call 1 (count = 1) -> executes
        # Turn 2: tool_call 2 (count = 2) -> executes
        # Turn 3: tool_call 3 (count = 3 > max_tool_calls=2) -> triggers guardrail limit hit
        # Final answer turn: synthesis response
        resp1 = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">file1.py</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        resp2 = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">file2.py</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        resp3_limit = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">file3.py</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        synthesis_resp = LLMResponse(
            content="### Final Analysis\n\nBased on `file1.py` and `file2.py`, the service boots properly.",
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=200, completion_tokens=40, total_tokens=240),
        )

        mock_loop.llm_service.generate = AsyncMock(side_effect=[resp1, resp2, resp3_limit, synthesis_resp])

        result = await mock_loop.run("How does the service boot?")

        assert result.stop_reason == StopReason.MAX_TOOL_CALLS_EXCEEDED
        assert "### Final Analysis" in result.answer
        assert "Based on `file1.py` and `file2.py`" in result.answer
        # Ensure raw tool call envelope is not leaked
        assert "<tool_call>" not in result.answer

    @pytest.mark.asyncio
    async def test_tool_limit_synthesis_returns_unexecuted_tool_call_falls_back_to_observations(self, mock_loop):
        """
        If the model stubbornly returns another tool call during the final synthesis turn,
        the system must NOT leak the tool syntax as the answer, and instead synthesize
        a fallback summary from the accumulated observations.
        """
        mock_observation = MagicMock(
            success=True,
            error=None,
            data="export const authConfig = { secret: 'xyz' };"
        )
        mock_loop.tool_dispatch.dispatch = MagicMock(return_value=mock_observation)
        mock_loop.tool_dispatch.specs = MagicMock(return_value=[])

        resp1 = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">file1.py</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        resp2 = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">file2.py</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        resp3_limit = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">file3.py</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        )
        # Stubborn model outputs another tool call instead of markdown answer in final turn
        leaked_synthesis_resp = LLMResponse(
            content='<tool_call><invoke name="read_file"><parameter name="path">file4.py</parameter></invoke></tool_call>',
            model="qwen3:4b-instruct",
            provider="ollama",
            usage=TokenUsage(prompt_tokens=200, completion_tokens=20, total_tokens=220),
        )

        mock_loop.llm_service.generate = AsyncMock(side_effect=[resp1, resp2, resp3_limit, leaked_synthesis_resp])

        result = await mock_loop.run("Analyze the authentication config")

        assert result.stop_reason == StopReason.MAX_TOOL_CALLS_EXCEEDED
        # Raw tool call is NOT leaked
        assert "<tool_call>" not in result.answer
        assert "<invoke name=\"read_file\">" not in result.answer
        # Observation fallback was generated
        assert ("### Key Repository Findings" in result.answer or "repository analysis finished" in result.answer)
