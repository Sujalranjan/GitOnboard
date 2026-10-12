"""
QA Protocol Adapter: Builds system prompt and parses JSON actions.

Reuses the JSON-action-protocol pattern from ModelAdapter but simplified for Q&A.
Decomposes system prompt into buckets for token accounting.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.ai.schemas import LLMResponse

from backend.services.qa_protocol_rules import (
    TOOL_USAGE_STRATEGIES,
    REPOSITORY_ANALYSIS_RULES,
    GROUNDING_RULES_JSON,
    GROUNDING_RULES_HERMES,
    GROUNDING_RULES_NATIVE,
)
from backend.services.qa_protocol_parsers import (
    parse_hermes_response,
    parse_json_response,
    parse_final_synthesis,
)

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
    """Builds and parses the action protocol for Q&A (JSON by default, Hermes XML for Qwen3)."""

    TOOL_USAGE_STRATEGIES = TOOL_USAGE_STRATEGIES
    REPOSITORY_ANALYSIS_RULES = REPOSITORY_ANALYSIS_RULES
    GROUNDING_RULES_JSON = GROUNDING_RULES_JSON
    GROUNDING_RULES_HERMES = GROUNDING_RULES_HERMES
    GROUNDING_RULES_NATIVE = GROUNDING_RULES_NATIVE

    @staticmethod
    def is_cloud_model(model_id: str, provider: Optional[str] = None) -> bool:
        """Return True if model/provider is a cloud model using native tool calling."""
        import os
        from backend.config import settings

        if provider in ("groq", "gemini", "openrouter", "ollama_cloud"):
            return True

        if model_id:
            groq_m = getattr(settings, "groq_model", "openai/gpt-oss-120b")
            gemini_m = getattr(settings, "gemini_model", "gemini-2.0-flash")
            openrouter_m = getattr(settings, "openrouter_model", "gpt-4-turbo")
            if model_id in (groq_m, gemini_m, openrouter_m):
                return True

            model_lower = model_id.lower()
            if any(marker in model_lower for marker in ("groq", "gemini", "openrouter", "gpt-", "claude")):
                return True
            if "ollama_cloud" in model_lower or os.environ.get("OLLAMA_IS_CLOUD", "").lower() in ("true", "1"):
                return True

        if getattr(settings, "deployment_type", "").upper() == "PROD":
            return True

        return False

    def __init__(
        self,
        model_id: Optional[str] = None,
        provider: Optional[str] = None,
        native_tools: Optional[bool] = None,
    ):
        self.model_id = model_id or ""
        self.provider = provider
        if native_tools is not None:
            self.is_native = native_tools
        else:
            self.is_native = self.is_cloud_model(self.model_id, self.provider)

        # Local Ollama models: Hermes XML for local Qwen, JSON for others
        self.is_local_ollama = not self.is_native
        self.is_qwen = self.is_local_ollama and ("qwen" in self.model_id.lower())

    @property
    def GROUNDING_RULES(self) -> str:
        """Return format-specific grounding rules based on model type."""
        if self.is_native:
            return self.GROUNDING_RULES_NATIVE
        return self.GROUNDING_RULES_HERMES if self.is_qwen else self.GROUNDING_RULES_JSON

    def _build_tool_usage_strategy(self, tool_specs: List[ToolSpec]) -> str:
        """
        Build TOOL USAGE STRATEGY section dynamically from available tools only.

        This ensures that baseline runs (include_rim=False) only contain strategy
        descriptions for the 3 baseline tools, and RIM runs contain descriptions
        for all available tools. This prevents the LLM from learning about tools
        it cannot use.

        Args:
            tool_specs: List of ToolSpec objects for available tools

        Returns:
            Formatted TOOL USAGE STRATEGY section string
        """
        if not tool_specs:
            return "## TOOL USAGE STRATEGY\n\nNo tools available.\n"

        # Extract tool names from specs
        available_tool_names = {spec.name for spec in tool_specs}

        # Build strategy lines for only available tools
        strategy_lines = ["## TOOL USAGE STRATEGY\n"]
        for spec in tool_specs:
            if spec.name in self.TOOL_USAGE_STRATEGIES:
                strategy_lines.append(self.TOOL_USAGE_STRATEGIES[spec.name])
                strategy_lines.append("")  # Blank line between tools

        return "\n".join(strategy_lines)

    def build_system_prompt(self, tool_specs: List[ToolSpec], rim_metadata_block: Optional[str]) -> SystemPromptParts:
        """
        Build decomposed system prompt with separate buckets for token accounting.

        CRITICAL: Tool usage strategy is built DYNAMICALLY from tool_specs only.
        This ensures baseline runs (include_rim=False) only see strategy for their 3 tools,
        preventing the LLM from learning about unavailable RIM-only tools.

        Args:
            tool_specs: List of available tools (baseline + RIM-specific if RIM side)
            rim_metadata_block: RIM metadata facts (None or empty string for baseline)

        Returns:
            SystemPromptParts with decomposed text for token counting
        """
        # 1. Grounding rules + protocol (constant, already excludes tool strategy)
        grounding = self.GROUNDING_RULES

        # 2. Build tool usage strategy DYNAMICALLY from available tools only
        # This is the critical fix: baseline gets strategy for 3 tools, RIM gets strategy for 9
        tool_usage_strategy = self._build_tool_usage_strategy(tool_specs)

        # 3. Tool catalog (JSON schema definitions)
        tool_catalog = self._build_tool_catalog(tool_specs)

        # 4. RIM metadata (baseline gets empty, RIM side gets facts)
        rim_section = ""
        if rim_metadata_block:
            rim_section = f"""
### RIM_METADATA

Repository Intelligence Graph facts (structural relationships):

{rim_metadata_block}

**WHEN TO USE GET_CODE_RELATIONSHIPS:**
Use `get_code_relationships` when the question involves relationships, callers/callees, dependencies, or connections between repository entities:
- CALLS: functions called by or calling an entity
- IMPORTS: module dependencies (incoming and outgoing)
- INHERITS: class inheritance and base classes
- CONTAINS: symbols declared within a file or class
- ROUTE_HANDLER: route handlers mapped to HTTP endpoints
- DATABASE_ACCESS: database tables or models accessed by code

Do NOT use for exact text, comments, configuration files (Docker, YAML, JSON), or string literals. Use `search_code` instead.

Use scope='LOCAL' for direct 1-hop relationships, 'NEIGHBORHOOD' (depth 1-3) for multi-hop tracing, and 'GLOBAL' when repository-wide relationship inspection is required.

If get_code_relationships returns NO_STATIC_EDGE_FOUND, dynamic code may be present; use search_repository and read_file to inspect the implementation directly."""
        else:
            rim_section = ""  # baseline gets no RIM section at all

        # 5. Combine all sections in order: grounding → strategy → catalog → RIM
        full_text = f"""{grounding}

{tool_usage_strategy}
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
        Parse LLM response for action (JSON or Hermes XML depending on model).

        For Qwen models: tries Hermes XML first, falls back to JSON if XML not found.
        This handles non-deterministic LLM behavior where context degradation causes
        format switching (early turns: Hermes XML, later turns: JSON).

        Returns:
            {
                "action": "tool_call" | "final_answer" | "malformed",
                "tool_name": "...",  # if tool_call
                "arguments": {...},  # if tool_call
                "answer": "...",  # if final_answer
                "error": "...",  # if malformed
            }
        """
        if self.is_qwen:
            # Try Hermes format first (native for Qwen)
            result = self._parse_hermes_response(text)
            # If Hermes parsing failed but looks like it tried, don't fall back
            if result["action"] != "malformed" or "<tool_call>" in text:
                return result
            # Context degradation: LLM reverted to JSON, try JSON format as fallback
            logger.debug(f"[parse_response] Hermes parse failed, trying JSON fallback for Qwen")
            return self._parse_json_response(text)
        else:
            return self._parse_json_response(text)

    def parse_response_from_llm_response(self, llm_response: "LLMResponse") -> Dict[str, Any]:
        """
        Normalize native tool calls or text-parsed tool calls into a uniform list format.

        For Groq, Gemini, OpenRouter, and Ollama Cloud (native tool calling):
          - Always use native tool calling as the primary method.
          - If llm_response.tool_calls is populated, takes the first tool call.
          - If no tool calls, returns final_answer directly with llm_response.content.
          - NO text fallback to Hermes XML or JSON.

        Only for local Ollama models:
          - Uses Hermes XML (for local Qwen) or JSON action protocol parsing on llm_response.content.
        """
        is_native = self.is_native or self.is_cloud_model(llm_response.model, llm_response.provider)

        if is_native:
            if llm_response.tool_calls:
                tc = llm_response.tool_calls[0]  # Take only first tool call
                return {
                    "action": "tool_call",
                    "tool_calls": [
                        {"tool_name": tc.tool_name, "arguments": tc.parameters}
                    ],
                    "tool_name": tc.tool_name,
                    "arguments": tc.parameters,
                }
            # No tool call made -> This is a final answer directly (NO FALLBACK)
            return {
                "action": "final_answer",
                "answer": llm_response.content,
            }

        # Local Ollama model behavior (Hermes XML / JSON text protocol):
        if llm_response.tool_calls:
            tc = llm_response.tool_calls[0]  # Take only first tool call
            return {
                "action": "tool_call",
                "tool_calls": [
                    {"tool_name": tc.tool_name, "arguments": tc.parameters}
                ],
                "tool_name": tc.tool_name,
                "arguments": tc.parameters,
            }
        result = self.parse_response(llm_response.content)
        if result.get("action") == "tool_call":
            return {
                "action": "tool_call",
                "tool_calls": [
                    {"tool_name": result["tool_name"], "arguments": result["arguments"]}
                ],
                "tool_name": result["tool_name"],
                "arguments": result["arguments"],
            }
        return result

    def _parse_hermes_response(self, text: str) -> Dict[str, Any]:
        return parse_hermes_response(text)

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        return parse_json_response(text)

    def parse_final_synthesis(self, text: str) -> str:
        return parse_final_synthesis(text)

