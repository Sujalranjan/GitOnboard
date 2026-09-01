"""
QA Protocol Adapter: Builds system prompt and parses JSON actions.

Reuses the JSON-action-protocol pattern from ModelAdapter but simplified for Q&A.
Decomposes system prompt into buckets for token accounting.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    """Tool specification for inclusion in system prompt."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON schema


@dataclass
class SystemPromptParts:
    """Decomposed system prompt for token accounting."""
    grounding_and_protocol_text: str  # static grounding + protocol instructions ("system" bucket)
    tool_catalog_text: str  # tool schemas ("other" bucket)
    rim_metadata_text: str  # RIM metadata block ("rim" bucket, empty for baseline)
    full_text: str  # concatenation actually sent as system message


class QAProtocolAdapter:
    """Builds and parses the JSON action protocol for Q&A."""

    GROUNDING_RULES = """You are a code assistant analyzing a software repository to answer questions.

RULES:
1. Read source files ONE AT A TIME using available tools
2. Use search to find relevant files/symbols first
3. Query the repository intelligence graph (RIM) to understand relationships
4. Always reason step-by-step
5. Only claim to have read code you actually examined with your tools
6. Base your answer ONLY on information from your tools, never on general knowledge of libraries/frameworks
7. If you cannot find an answer, clearly state what you were missing

RESPONSE PROTOCOL:
Respond with exactly one JSON action per turn:
- To call a tool: {"action": "tool_call", "tool_name": "...", "arguments": {...}}
- To provide your answer: {"action": "final_answer", "answer": "..."}

Choose one action per response. Do not call multiple tools in one turn.
Read files ONE AT A TIME. Do not request multiple file reads in a single turn."""

    def build_system_prompt(self, tool_specs: List[ToolSpec], rim_metadata_block: Optional[str]) -> SystemPromptParts:
        """
        Build decomposed system prompt with separate buckets for token accounting.

        Args:
            tool_specs: List of available tools (baseline + RIM-specific if RIM side)
            rim_metadata_block: RIM metadata facts (None or empty string for baseline)

        Returns:
            SystemPromptParts with decomposed text for token counting
        """
        # 1. Grounding rules + protocol (constant across turns)
        grounding = self.GROUNDING_RULES

        # 2. Tool catalog
        tool_catalog = self._build_tool_catalog(tool_specs)

        # 3. RIM metadata (baseline gets empty, RIM side gets facts)
        rim_section = ""
        if rim_metadata_block:
            rim_section = f"""
### RIM_METADATA

Repository Intelligence Graph facts (structural relationships):

{rim_metadata_block}

Use these facts to understand the repository structure. Query the `query_rim` tool for additional details."""
        else:
            rim_section = ""  # baseline gets no RIM section at all

        # 4. Combine all sections
        full_text = f"""{grounding}

{tool_catalog}{rim_section}"""

        return SystemPromptParts(
            grounding_and_protocol_text=grounding,
            tool_catalog_text=tool_catalog,
            rim_metadata_text=rim_section,
            full_text=full_text,
        )

    def _build_tool_catalog(self, tool_specs: List[ToolSpec]) -> str:
        """Build the AVAILABLE TOOLS section of the prompt."""
        if not tool_specs:
            return "### AVAILABLE TOOLS\n(None)"

        lines = ["### AVAILABLE TOOLS\n"]
        for spec in tool_specs:
            lines.append(f"**{spec.name}**: {spec.description}")
            lines.append(f"Arguments: {self._format_json_schema(spec.parameters)}")
            lines.append("")

        return "\n".join(lines)

    def _format_json_schema(self, schema: Dict[str, Any]) -> str:
        """Format JSON schema as inline text."""
        import json
        try:
            return json.dumps(schema, indent=2)
        except:
            return str(schema)

    def parse_response(self, text: str) -> Dict[str, Any]:
        """
        Parse LLM response for JSON action.

        Returns:
            {
                "action": "tool_call" | "final_answer" | "malformed",
                "tool_name": "...",  # if tool_call
                "arguments": {...},  # if tool_call
                "answer": "...",  # if final_answer
                "error": "...",  # if malformed
            }
        """
        import json
        import re

        # Try to extract JSON object from response
        json_match = re.search(r'\{[^{}]*\}', text)
        if not json_match:
            logger.debug(f"No JSON object found in response: {text[:100]}")
            return {
                "action": "malformed",
                "error": "no JSON object found",
            }

        try:
            obj = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.debug(f"JSON parse error: {e}")
            return {
                "action": "malformed",
                "error": f"JSON parse error: {e}",
            }

        action = obj.get("action", "").lower()

        if action == "tool_call":
            tool_name = obj.get("tool_name", "").strip()
            arguments = obj.get("arguments", {})

            if not tool_name:
                return {
                    "action": "malformed",
                    "error": "tool_call missing tool_name",
                }

            return {
                "action": "tool_call",
                "tool_name": tool_name,
                "arguments": arguments if isinstance(arguments, dict) else {},
            }

        elif action == "final_answer":
            answer = obj.get("answer", text).strip()
            if not answer:
                answer = text  # fallback to raw text if answer is empty

            return {
                "action": "final_answer",
                "answer": answer,
            }

        else:
            logger.debug(f"Unknown action: {action}")
            return {
                "action": "malformed",
                "error": f"unknown action: {action}",
            }
