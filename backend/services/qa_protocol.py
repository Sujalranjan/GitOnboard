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
    """Builds and parses the action protocol for Q&A (JSON by default, Hermes XML for Qwen3)."""

    def __init__(self, model_id: Optional[str] = None):
        """
        Initialize protocol adapter with optional model ID.

        Args:
            model_id: Model identifier (e.g., "qwen3:4b-instruct"). If model starts with "qwen",
                      enables optimizations for Qwen's native tool calling capabilities.
        """
        self.model_id = model_id or ""
        self.is_qwen = self.model_id.lower().startswith("qwen")

    GROUNDING_RULES = """You are a code assistant analyzing a software repository to answer questions.
CRITICAL: You MUST use repository tools to find information. You MUST NOT rely on general knowledge.

=== MANDATORY RESPONSE PROTOCOL (READ FIRST) ===
EVERY response MUST be EXACTLY ONE JSON object with NO extra text.
ONLY TWO VALID ACTIONS EXIST:
  1. {"action": "tool_call", "tool_name": "<NAME>", "arguments": {...}}
  2. {"action": "final_answer", "answer": "..."}

⚠️  CRITICAL RULE: action MUST ALWAYS be the STRING "tool_call" or "final_answer"
⚠️  NEVER use tool name as action: {"action": "search_code"} is WRONG
⚠️  ALWAYS use: {"action": "tool_call", "tool_name": "search_code"} is CORRECT

YOUR TASK:
Determine what information is needed to answer the user's question, then select the most direct available tool to retrieve that information. Provide your answer once sufficient repository evidence is gathered.

RESPONSE FORMAT (MANDATORY - STRICT JSON ONLY):
Each turn, output EXACTLY ONE complete JSON object with NO extra text:

For tool calls, ALWAYS use this structure:
{"action": "tool_call", "tool_name": "<TOOL_NAME>", "arguments": {<ARGUMENTS>}}

When done analyzing:
{"action": "final_answer", "answer": "Your answer based on tools"}

TOOL SELECTION GUIDE:
Use only tools listed in AVAILABLE TOOLS. Never invent, rename, or substitute a tool.

- search_code: Search repository file contents for text patterns, keywords, string literals
- search_symbols: Find files and symbols (classes, functions, methods) by name using exact matching, BM25, or semantic similarity
- get_symbol: Look up an exact known symbol and return its definition, location, type, docstring, methods
- get_callers: Find functions/methods that call a specific symbol
- get_callees: Find functions/methods called by a specific symbol
- get_dependencies: Return third-party project dependencies
- get_route: Look up HTTP REST routes and their handler mappings
- get_feature: Look up detected architectural capabilities (authentication, caching, logging, etc.)

Prefer specialized tools when they directly match the user's question:
- Question asks "Where is AuthService?" or "Find the login function" → search_symbols
- Question asks for exact symbol info → get_symbol
- Question asks "Who calls authenticate_user?" → get_callers
- Question asks "What does process_payment call?" → get_callees
- Question asks "What dependencies does this project use?" → get_dependencies
- Question asks "What endpoints exist?" or "Show routes under /users" → get_route
- Question asks "Does the repository have authentication?" → get_feature
- Question asks for text patterns or keyword search → search_code

EXECUTION RULES:
1. ONE tool call per turn - wait for results before taking next action
2. Use the fewest tool calls necessary to answer accurately
3. Once available repository evidence is sufficient, provide your answer - do not perform additional searches merely because more tools are available
4. Read source files only when available search/metadata/relationship results are insufficient or when implementation details are required
5. Only claim to have inspected code that was actually returned by a tool
6. Base repository-specific claims on tool results, never on general knowledge
7. JSON ONLY: Output ONLY the JSON object, with NO text before or after it
8. NO EXPLANATIONS: Do not add "Let me search..." or "I found..." - just output the JSON

PAGINATION:
If a tool result indicates "... and N more results" available, use offset/limit parameters to fetch additional results as needed.

RELATIONSHIP QUERIES:
When relationship information is actually relevant to answering the question, use relationship tools (get_callers, get_callees) to explore connections. Do not use relationship tools merely because they exist."""

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

**WHEN TO USE QUERY_RIM:**
Use `query_rim` when the question involves relationships, dependencies, or connections between repository entities. It can identify:
- CALLS: which functions call which
- IMPORTS: which modules import which
- INHERITS: inheritance relationships
- CONTAINS: what a module/class contains
- ROUTE_HANDLER: API routes and handlers
- DATABASE_ACCESS: database interactions

**WORKFLOW:**
1. Search for relevant code using search_repository or find_files
2. Read source files to understand implementation details
3. Determine: Does this question need structural relationships?
   - NO (implementation details, algorithms, syntax) → Answer from source code
   - YES (dependencies, connections, relationships) → Use query_rim to explore
4. Combine findings and provide your answer

**IMPORTANT:** Do not use query_rim just to use RIM. Use it only when relationship information is relevant to answering the question."""
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

        # FALLBACK: Detect and fix malformed responses where LLM put tool name as action
        # This happens with small models like Qwen 3 4B that don't follow complex instructions
        # Pattern: {"action": "search_code", "arguments": {...}} should be tool_call
        KNOWN_TOOLS = {
            "search_code", "search_repository", "search_symbols", "get_symbol",
            "get_file_outline", "get_callers", "get_callees", "get_dependencies",
            "get_route", "get_feature", "query_rim", "read_file", "find_files"
        }
        if action in KNOWN_TOOLS and obj.get("arguments"):
            # LLM mistakenly used tool name as action. Correct it.
            logger.warning(f"[parse_response] Correcting malformed response: action={action} (should be tool_call)")
            obj["tool_name"] = action
            obj["action"] = "tool_call"
            action = "tool_call"

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
