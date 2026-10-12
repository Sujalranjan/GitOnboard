"""
Parser functions for QAProtocolAdapter.
Handles Hermes XML tool calling, JSON action extraction, and final synthesis cleaning.
"""
from __future__ import annotations

import logging
import re
import json
from typing import Any, Dict

logger = logging.getLogger(__name__)

KNOWN_TOOLS = {
    "search_code", "search_repository", "get_file_outline",
    "get_code_relationships", "read_file", "get_tree"
}


def parse_hermes_response(text: str) -> Dict[str, Any]:
    """Parse Hermes XML tool calling format (for Qwen models)."""
    # Look for <tool_call> ... </tool_call> blocks
    tool_call_match = re.search(r'<tool_call>(.*?)</tool_call>', text, re.DOTALL)
    if not tool_call_match:
        logger.debug(f"[parse_hermes] No <tool_call> block found in response: {text[:100]}")
        return {"action": "malformed", "error": "no <tool_call> block found"}

    tool_call_content = tool_call_match.group(1)

    # Extract invoke name: <invoke name="tool_name">
    invoke_match = re.search(r'<invoke name="([^"]+)">', tool_call_content)
    if not invoke_match:
        logger.debug(f"[parse_hermes] No <invoke> with name attribute found")
        return {"action": "malformed", "error": "no <invoke name=...> found"}

    invoke_name = invoke_match.group(1).strip()

    # Special case: final_answer
    if invoke_name == "final_answer":
        # Extract answer from <parameter name="answer">...</parameter>
        param_match = re.search(r'<parameter name="answer">(.*?)</parameter>', tool_call_content, re.DOTALL)
        answer = param_match.group(1).strip() if param_match else text
        return {
            "action": "final_answer",
            "answer": answer,
        }

    if invoke_name not in KNOWN_TOOLS:
        logger.debug(f"[parse_hermes] Unknown tool: {invoke_name}")
        return {"action": "malformed", "error": f"unknown tool: {invoke_name}"}

    # Extract all parameters: <parameter name="key">value</parameter>
    arguments = {}
    param_pattern = r'<parameter name="([^"]+)">([^<]*)</parameter>'
    for match in re.finditer(param_pattern, tool_call_content):
        param_name = match.group(1).strip()
        param_value = match.group(2).strip()

        # Try to parse as JSON if it looks like JSON
        if param_value.startswith('{') or param_value.startswith('['):
            try:
                param_value = json.loads(param_value)
            except json.JSONDecodeError:
                pass  # Keep as string if not valid JSON

        arguments[param_name] = param_value

    logger.debug(f"[parse_hermes] Parsed tool_call: {invoke_name} with {len(arguments)} params")
    return {
        "action": "tool_call",
        "tool_name": invoke_name,
        "arguments": arguments,
    }


def parse_json_response(text: str) -> Dict[str, Any]:
    """Parse JSON format responses."""
    # Try to extract JSON object from response.
    # Search for '{' and attempt to parse from each position until successful.
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
                    action = obj.get("action", "").lower()
                    if action in ["tool_call", "final_answer"]:
                        break
            except json.JSONDecodeError:
                obj = None
                continue

    if obj is None or not isinstance(obj, dict):
        stripped_text = text.strip()
        if stripped_text and not any(tag in stripped_text for tag in ["<tool_call>", "<function_call>"]):
            if not re.search(r'^\s*\{\s*"', stripped_text):
                logger.info(f"[_parse_json_response] Plain text / Markdown answer detected without JSON envelope. Wrapping as final_answer.")
                return {
                    "action": "final_answer",
                    "answer": stripped_text,
                }

        logger.debug(f"No valid JSON action object found in response: {text[:100]}")
        return {
            "action": "malformed",
            "error": "no valid JSON action object found",
        }

    action = obj.get("action", "").lower()

    if action in KNOWN_TOOLS and obj.get("arguments"):
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
            answer = text

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


def parse_final_synthesis(text: str) -> str:
    """
    Dedicated parsing path for final synthesis turns.
    Preserves pure markdown and plain-text answers while extracting answers and stripping raw tool syntax.
    """
    if not text or not text.strip():
        return ""

    raw_trimmed = text.strip()

    # 1. Structured JSON parse
    try:
        parsed_json = json.loads(raw_trimmed)
        if isinstance(parsed_json, dict):
            action = parsed_json.get("action", "").lower()
            if action == "final_answer" and "answer" in parsed_json:
                return str(parsed_json["answer"]).strip()
            if action == "tool_call" or "tool_name" in parsed_json or action in KNOWN_TOOLS:
                return ""
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Hermes XML <invoke name="final_answer">
    final_answer_match = re.search(
        r'<invoke\s+name=["\']final_answer["\']>(.*?)</invoke>',
        raw_trimmed,
        re.DOTALL
    )
    if final_answer_match:
        param_match = re.search(
            r'<parameter\s+name=["\']answer["\']>(.*?)</parameter>',
            final_answer_match.group(1),
            re.DOTALL
        )
        if param_match:
            extracted = param_match.group(1).strip()
            if extracted:
                return extracted

    # 3. Strip complete and incomplete <tool_call> and <function_call>
    cleaned = re.sub(r'<tool_call>.*?</tool_call>', '', raw_trimmed, flags=re.DOTALL)
    cleaned = re.sub(r'<function_call>.*?</function_call>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'<tool_call>.*$', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'<function_call>.*$', '', cleaned, flags=re.DOTALL)

    cleaned = re.sub(r'\[TOOL_CALL\].*?\[/TOOL_CALL\]', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\[TOOL_CALL\].*$', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\[TOOL_CALL\]', '', cleaned)

    cleaned = re.sub(r'```(?:tool_call|json)?\s*\{[^{}]*"action"\s*:\s*"(?:tool_call|read_file|search_code|search_repository|get_file_outline|get_code_relationships|get_tree)"[^{}]*\}\s*```', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'```tool_call\s*.*?```', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'```tool_call\s*.*$', '', cleaned, flags=re.DOTALL)

    cleaned = re.sub(r'</?(?:tool_call|function_call)>', '', cleaned)
    cleaned = re.sub(r'<invoke[^>]*>.*?</invoke>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'<invoke[^>]*>.*$', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'</?invoke[^>]*>', '', cleaned)
    cleaned = re.sub(r'<parameter[^>]*>.*?</parameter>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'<parameter[^>]*>.*$', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'</?parameter[^>]*>', '', cleaned)

    # 4. Strip JSON tool calls
    for match in re.finditer(r'\{[^{}]*"action"\s*:\s*"(?:tool_call|read_file|search_code|search_repository|get_file_outline|get_code_relationships|get_tree)"[^{}]*\}', cleaned, re.DOTALL):
        cleaned = cleaned.replace(match.group(0), "")

    for match in re.finditer(r'\{[^{}]*"tool_name"\s*:\s*"(?:read_file|search_code|search_repository|get_file_outline|get_code_relationships|get_tree)"[^{}]*\}', cleaned, re.DOTALL):
        cleaned = cleaned.replace(match.group(0), "")

    cleaned = re.sub(r'\{[^{}]*"action"\s*:\s*"(?:tool_call|read_file|search_code|search_repository|get_file_outline|get_code_relationships|get_tree)".*$', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\{[^{}]*"tool_name"\s*:\s*"(?:read_file|search_code|search_repository|get_file_outline|get_code_relationships|get_tree)".*$', '', cleaned, flags=re.DOTALL)

    fa_json_match = re.search(r'\{[^{}]*"action"\s*:\s*"final_answer"\s*,\s*"answer"\s*:\s*"(.*?)"\s*\}', cleaned, re.DOTALL)
    if fa_json_match:
        try:
            extracted_ans = json.loads(f'"{fa_json_match.group(1)}"')
            if extracted_ans.strip():
                return extracted_ans.strip()
        except Exception:
            pass

    cleaned = re.sub(r'^(\d+\.)\s*\n\s*', r'\1 ', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned).strip()

    return cleaned
