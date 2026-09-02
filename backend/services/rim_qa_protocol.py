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
CRITICAL: You MUST use repository tools to find information. You MUST NOT rely on general knowledge.

YOUR TASK:
1. First, use tools to search the repository and find relevant files/symbols
2. Read source files ONE AT A TIME using the read_file tool
3. Query relationships using available tools (query_rim if available)
4. Based on what you find, provide your answer

RESPONSE FORMAT (MANDATORY):
Each turn, respond with EXACTLY ONE of these JSON objects:
- To search/read: {"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "..."}}
- To read a file: {"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "...", "start_line": 1, "end_line": 100}}
- To look up a symbol: {"action": "tool_call", "tool_name": "get_symbol", "arguments": {"name": "..."}}
- To find callers: {"action": "tool_call", "tool_name": "get_callers", "arguments": {"symbol_name": "..."}}
- To find callees: {"action": "tool_call", "tool_name": "get_callees", "arguments": {"symbol_name": "..."}}
- When done: {"action": "final_answer", "answer": "Your comprehensive answer based on tools"}

RULES:
1. ALWAYS start with a search_repository or find_files tool call to identify relevant code
2. Read files ONE AT A TIME using read_file
3. ONE tool call per turn - wait for results before the next action
4. NEVER provide an answer without first using tools to examine the code
5. Only claim to have read code you actually examined with tools
6. Base your answer ONLY on information from tools, NEVER on general knowledge

Example flow:
Turn 0: {"action": "tool_call", "tool_name": "search_repository", "arguments": {"query": "login authentication"}}
Turn 1: {"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/auth.py", "start_line": 1, "end_line": 50}}
Turn 2: {"action": "final_answer", "answer": "Based on examining src/auth.py, the login process..."}"""

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

        # Try to extract JSON object from response.
        # Search for '{' and attempt to parse from each position until successful.
        # This handles nested JSON (e.g., arguments with nested dicts).
        obj = None
        for match in re.finditer(r'\{', text):
            start_pos = match.start()
            # Find the matching closing brace by counting braces
            brace_count = 0
            end_pos = start_pos
            for i in range(start_pos, len(text)):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break

            if brace_count == 0:  # Found matching close brace
                try:
                    # Try to parse just this JSON object
                    json_str = text[start_pos:end_pos]
                    obj = json.loads(json_str)
                    if isinstance(obj, dict):
                        # Successfully parsed a JSON object
                        action = obj.get("action", "").lower()
                        if action in ["tool_call", "final_answer"]:
                            # This is a valid action object
                            break
                except json.JSONDecodeError:
                    # This position didn't yield valid JSON, try next {
                    obj = None
                    continue

        if obj is None or not isinstance(obj, dict):
            logger.debug(f"No valid JSON action object found in response: {text[:100]}")
            return {
                "action": "malformed",
                "error": "no valid JSON action object found",
            }

        try:
            # obj is already parsed
            pass
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
