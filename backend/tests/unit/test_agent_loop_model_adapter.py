"""
Unit tests for Phase 6 ModelAdapter.
"""
import pytest

from backend.agent.loop.model_adapter import ModelAdapter, ParsedModelOutput
from backend.agent.tools.contracts import ToolDefinition


def test_build_system_prompt_structure():
    adapter = ModelAdapter()
    tools = [
        ToolDefinition(
            name="read_file",
            description="Reads file contents",
            category="workspace",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
    ]
    prompt = adapter.build_system_prompt(
        tools=tools,
        acceptance_criteria=["Endpoint returns 200 OK", "404 when missing"],
        constraints=["Worktree only"],
    )

    assert "read_file" in prompt
    assert "Endpoint returns 200 OK" in prompt
    assert "404 when missing" in prompt
    assert "Worktree only" in prompt
    assert "tool_call" in prompt
    assert "complete" in prompt


def test_parse_valid_tool_call_json():
    adapter = ModelAdapter()
    raw = """
    ```json
    {
      "action": "tool_call",
      "tool_name": "read_file",
      "arguments": {
        "path": "backend/main.py"
      }
    }
    ```
    """
    parsed = adapter.parse_response(raw)
    assert parsed.is_malformed is False
    assert parsed.tool_call is not None
    assert parsed.tool_call.tool_name == "read_file"
    assert parsed.tool_call.arguments == {"path": "backend/main.py"}
    assert parsed.completion_signal is None


def test_parse_valid_completion_signal():
    adapter = ModelAdapter()
    raw = """
    {
      "action": "complete",
      "summary": "Implemented GET /users/{id}",
      "acceptance_criteria_status": [
        {
          "criterion": "Endpoint returns user",
          "status": "satisfied",
          "evidence": "Verified with test_get_user passing in test_users.py"
        }
      ],
      "verification_requested": true
    }
    """
    parsed = adapter.parse_response(raw)
    assert parsed.is_malformed is False
    assert parsed.tool_call is None
    assert parsed.completion_signal is not None
    assert parsed.completion_signal.summary == "Implemented GET /users/{id}"
    assert len(parsed.completion_signal.acceptance_criteria_status) == 1
    assert parsed.completion_signal.verification_requested is True


def test_reject_plain_done_string_as_malformed():
    adapter = ModelAdapter()
    parsed = adapter.parse_response("Done.")
    assert parsed.is_malformed is True
    assert "Invalid JSON format" in (parsed.parse_error or "")


def test_reject_missing_criterion_evidence():
    adapter = ModelAdapter()
    raw = """
    {
      "action": "complete",
      "summary": "Finished task",
      "acceptance_criteria_status": [
        {
          "criterion": "Criterion 1",
          "status": "satisfied",
          "evidence": ""
        }
      ]
    }
    """
    parsed = adapter.parse_response(raw)
    assert parsed.is_malformed is True
    assert "non-empty 'evidence'" in (parsed.parse_error or "")


def test_reject_empty_criteria_list():
    adapter = ModelAdapter()
    raw = """
    {
      "action": "complete",
      "summary": "Finished task",
      "acceptance_criteria_status": []
    }
    """
    parsed = adapter.parse_response(raw)
    assert parsed.is_malformed is True
    assert "non-empty 'acceptance_criteria_status'" in (parsed.parse_error or "")
