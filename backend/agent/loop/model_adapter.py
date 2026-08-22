"""
Phase 6 Model Interaction Adapter for Engineering Agent Loop.

Responsible for:
  - Constructing model prompt envelopes containing task context, tool catalog, and completion protocol.
  - Interfacing with LLMService / LLMProvider or mock models.
  - Parsing structured proposals (ToolCall vs CompletionSignal vs Malformed).
  - Strictly proposing actions without performing policy enforcement (Policy is enforced by ToolPolicy / AgentToolRegistry).
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from backend.agent.loop.contracts import (
    CompletionSignal,
    CriterionEvaluation,
    ToolCall,
    ToolObservation,
)
from backend.agent.tools.contracts import ToolDefinition

logger = logging.getLogger(__name__)


class ModelMessage(BaseModel):
    """Normalized message representation in the agent conversation loop."""
    role: str = Field(..., description="Role: 'system', 'user', 'assistant', 'tool'")
    content: str = Field(..., description="Text content of the message")
    tool_call_id: Optional[str] = Field(default=None, description="Associated tool_call_id for tool observations")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class ParsedModelOutput(BaseModel):
    """Parsed and structured outcome of a single model response."""
    raw_response: str
    tool_call: Optional[ToolCall] = None
    completion_signal: Optional[CompletionSignal] = None
    is_malformed: bool = False
    parse_error: Optional[str] = None


class ModelAdapter:
    """
    Adapter between the EngineeringAgentLoop and LLM providers.
    Constructs prompts, communicates with LLM services, and parses outputs.
    """

    def __init__(self, llm_service: Optional[Any] = None):
        self.llm_service = llm_service

    def build_system_prompt(
        self,
        tools: List[ToolDefinition],
        acceptance_criteria: List[str],
        constraints: Optional[List[str]] = None,
    ) -> str:
        """
        Constructs deterministic system instructions describing available tools,
        the tool invocation protocol, and the strict completion contract.
        """
        tool_catalogs = []
        for t in tools:
            tool_catalogs.append(
                f"- Tool: `{t.name}`\n"
                f"  Category: {t.category}\n"
                f"  Description: {t.description}\n"
                f"  Parameters: {json.dumps(t.input_schema)}"
            )
        tools_str = "\n\n".join(tool_catalogs)

        criteria_items = "\n".join([f"- {c}" for c in acceptance_criteria]) if acceptance_criteria else "- Satisfy all task requirements."
        constraints_items = "\n".join([f"- {c}" for c in (constraints or [])]) if constraints else "- Work strictly within the designated worktree."

        return f"""You are the GitOnBoard Engineering Agent executing a specific implementation task.
You operate in a controlled, step-by-step tool invocation loop.

### AVAILABLE TOOLS:
{tools_str}

### ACCEPTANCE CRITERIA TO SATISFY:
{criteria_items}

### EXECUTION CONSTRAINTS:
{constraints_items}

### RESPONSE PROTOCOL:
You MUST respond with a single valid JSON object in one of two formats:

Option 1: Propose a Tool Call
```json
{{
  "action": "tool_call",
  "tool_name": "<exact_tool_name>",
  "arguments": {{
    "<param_name>": "<value>"
  }}
}}
```

Option 2: Complete Implementation & Request Verification
```json
{{
  "action": "complete",
  "summary": "<Concise summary of changes made>",
  "acceptance_criteria_status": [
    {{
      "criterion": "<criterion text>",
      "status": "satisfied",
      "evidence": "<concrete file/line/test evidence>"
    }}
  ],
  "verification_requested": true
}}
```

CRITICAL RULES:
1. Propose EXACTLY ONE action (tool_call or complete) per turn.
2. NEVER output raw markdown or conversational text outside the JSON object.
3. NEVER say 'Done' or declare completion without satisfying all acceptance criteria with concrete evidence.
4. When all necessary files are modified and inspected, propose the 'complete' action to request verification.
"""

    def parse_response(self, text: str) -> ParsedModelOutput:
        """
        Parses raw model output into a structured ToolCall, CompletionSignal, or malformed result.
        """
        if not text or not text.strip():
            return ParsedModelOutput(
                raw_response=text or "",
                is_malformed=True,
                parse_error="Empty or whitespace response from model.",
            )

        cleaned = text.strip()
        # Strip markdown code fences if present (e.g. ```json ... ```)
        if cleaned.startswith("```"):
            fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
            if fence_match:
                cleaned = fence_match.group(1).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as err:
            logger.warning(f"ModelAdapter: Failed to parse JSON response: {err}")
            return ParsedModelOutput(
                raw_response=text,
                is_malformed=True,
                parse_error=f"Invalid JSON format: {str(err)}",
            )

        if not isinstance(data, dict):
            return ParsedModelOutput(
                raw_response=text,
                is_malformed=True,
                parse_error="Response JSON must be a dictionary/object.",
            )

        action = data.get("action")

        # 1. Handle Tool Call
        if action == "tool_call":
            tool_name = data.get("tool_name")
            if not tool_name or not isinstance(tool_name, str):
                return ParsedModelOutput(
                    raw_response=text,
                    is_malformed=True,
                    parse_error="tool_call missing valid 'tool_name' string.",
                )
            arguments = data.get("arguments", {})
            if not isinstance(arguments, dict):
                return ParsedModelOutput(
                    raw_response=text,
                    is_malformed=True,
                    parse_error="'arguments' field in tool_call must be an object/dict.",
                )
            tool_call = ToolCall(
                tool_call_id=f"call_{uuid.uuid4().hex[:8]}",
                tool_name=tool_name.strip(),
                arguments=arguments,
            )
            return ParsedModelOutput(raw_response=text, tool_call=tool_call)

        # 2. Handle Completion Signal
        elif action == "complete":
            summary = data.get("summary")
            if not summary or not isinstance(summary, str):
                return ParsedModelOutput(
                    raw_response=text,
                    is_malformed=True,
                    parse_error="Completion signal missing required 'summary' string.",
                )

            crit_list = data.get("acceptance_criteria_status")
            if not isinstance(crit_list, list) or len(crit_list) == 0:
                return ParsedModelOutput(
                    raw_response=text,
                    is_malformed=True,
                    parse_error="Completion signal requires non-empty 'acceptance_criteria_status' list.",
                )

            evaluations: List[CriterionEvaluation] = []
            for item in crit_list:
                if not isinstance(item, dict):
                    return ParsedModelOutput(
                        raw_response=text,
                        is_malformed=True,
                        parse_error="Each item in 'acceptance_criteria_status' must be an object.",
                    )
                criterion = item.get("criterion", "")
                status = item.get("status", "satisfied")
                evidence = item.get("evidence", "")
                if not criterion or not evidence:
                    return ParsedModelOutput(
                        raw_response=text,
                        is_malformed=True,
                        parse_error="Each criterion evaluation must include 'criterion' and non-empty 'evidence'.",
                    )
                evaluations.append(
                    CriterionEvaluation(criterion=str(criterion), status=str(status), evidence=str(evidence))
                )

            signal = CompletionSignal(
                summary=summary.strip(),
                acceptance_criteria_status=evaluations,
                verification_requested=bool(data.get("verification_requested", True)),
                metadata=data.get("metadata", {}),
            )
            return ParsedModelOutput(raw_response=text, completion_signal=signal)

        else:
            return ParsedModelOutput(
                raw_response=text,
                is_malformed=True,
                parse_error=f"Unrecognized action '{action}'. Must be 'tool_call' or 'complete'.",
            )

    async def call_model(self, messages: List[ModelMessage]) -> str:
        """
        Dispatches conversation messages to the underlying LLM provider.
        """
        if not self.llm_service:
            raise RuntimeError("ModelAdapter: No LLMService provided.")

        from backend.ai.schemas import LLMRequest, LLMMessage

        llm_messages = [
            LLMMessage(role=m.role, content=m.content) for m in messages
        ]
        request = LLMRequest(
            messages=llm_messages,
            temperature=0.1,
            max_tokens=4096,
        )

        response = await self.llm_service.generate(request)
        return response.content
