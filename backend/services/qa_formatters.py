"""
Formatters for tool observations and outputs in QALoop.
"""
from __future__ import annotations

import json
from typing import Any

from backend.agent.loop.contracts import ToolObservation


def format_tool_observation(tool_name: str, observation: ToolObservation, data: Any) -> str:
    """Format tool observation for appending to conversation.
    Includes both summary and actual data so LLM can reason over results.
    """
    if not observation.success:
        error = observation.error or {}
        return f"[TOOL ERROR] {tool_name}: {error.get('message', 'unknown error')}"

    # Format with summary + actual data so LLM can use the results
    if tool_name == "read_file" and isinstance(data, dict):
        # Check if data was truncated by sanitization
        if data.get("_truncated"):
            path = data.get('path', 'unknown file')
            return (
                f"[read_file] FILE TOO LARGE: {path} exceeds size limit.\n\n"
                f"SOLUTION: Use one of these approaches:\n"
                f"1. search_repository: Find specific functions/classes in the file\n"
                f"   Example: search_repository with query 'function_name' or 'class_name'\n"
                f"2. read_file with line range: Read specific sections\n"
                f"   Example: read_file('{path}', start_line=50, end_line=150)\n"
                f"3. get_symbol: Find definitions of specific symbols\n"
                f"   Example: get_symbol('MyClass') or get_symbol('my_function')\n\n"
                f"These tools will help you locate and read relevant parts without loading the entire file."
            )

        path = data.get('path', '')
        start_line = data.get('start_line', 1)
        end_line = data.get('end_line')  # Don't default to 0 - let it be None if missing
        total_lines = data.get('total_lines', 0)
        content = data.get('content', '')
        raw_text = data.get('raw_text', '')

        # Use formatted content (which contains line numbers and context protection notice) if available,
        # otherwise fall back to raw_text
        actual_content = content or raw_text

        # If end_line is missing, use total_lines
        if end_line is None:
            end_line = total_lines or start_line

        summary = f"[read_file] {path} lines {start_line}-{end_line}: {len(actual_content)} chars (total: {total_lines})\n"
        if actual_content:
            return summary + actual_content
        return summary
    elif tool_name == "get_code_relationships" and isinstance(data, dict):
        display_name = tool_name
        if not data.get("found"):
            resolution = data.get("resolution", "")
            msg = data.get("message", "")
            fallback = data.get("fallback")
            fb_str = f" Suggested next step: call {fallback['tool']}(query='{fallback['query']}')" if fallback else ""
            if resolution == "NO_STATIC_EDGE_FOUND":
                return f"[{display_name}] No static edge found: {msg}.{fb_str}"
            return f"[{display_name}] Entity not found: {msg}.{fb_str}"

        related = data.get("related", [])
        target_info = ""
        target_loc = ""
        target_line = 1
        if "target" in data and isinstance(data["target"], dict):
            t = data["target"]
            target_loc = t.get("location", "")
            target_line = t.get("line", 1) or 1
            target_info = f" for '{t.get('name', '')}' ({t.get('type', '')} at {target_loc}:{target_line})"

        summary = f"[{display_name}] Found {len(related)} related entities{target_info}:\n"
        inspection_recommendations = []

        # Guide to inspect the caller/target implementation itself if known
        if target_loc and target_loc not in ("?", ""):
            try:
                t_ln = int(target_line)
                start_w = max(1, t_ln - 5)
                end_w = t_ln + 50
                inspection_recommendations.append(
                    f"read_file(path='{target_loc}', start_line={start_w}, end_line={end_w}) to inspect caller implementation"
                )
            except (ValueError, TypeError):
                pass

        for entity in related:
            name = entity.get("name", "?")
            entity_type = entity.get("entity_type", "?")
            location = entity.get("location", "?")
            line_num = entity.get("line_number", "?")
            role = entity.get("relationship_role", "?")
            path_str = f", path: {' -> '.join(entity['path'])}" if entity.get("path") else ""
            summary += f"  - {name} ({entity_type}, {location}:{line_num}, role: {role}{path_str})\n"

            # If entity has a valid file path and line number, suggest targeted code inspection
            if location and location not in ("?", "") and line_num not in ("?", None, ""):
                try:
                    ln = int(line_num)
                    start_win = max(1, ln - 15)
                    end_win = ln + 25
                    if len(inspection_recommendations) < 3:
                        inspection_recommendations.append(
                            f"read_file(path='{location}', start_line={start_win}, end_line={end_win}) to inspect '{name}'"
                        )
                except (ValueError, TypeError):
                    pass

        if inspection_recommendations:
            summary += "\nActionable next step for verification:\n"
            for rec in inspection_recommendations:
                summary += f"- Call {rec}\n"

        return summary
    elif tool_name == "search_repository" and isinstance(data, list):
        summary = f"[search_repository] Found {len(data)} results:\n"
        for result in data[:10]:  # Include first 10 results
            if isinstance(result, dict):
                file_path = result.get("file", result.get("path", "?"))
                result_type = result.get("type", "")
                if result_type == "symbol" and "symbol" in result:
                    summary += f"  - {file_path}: {result['symbol']} (lines {result.get('lines', '?')})\n"
                elif result_type == "code" and "line" in result:
                    snippet = result.get("snippet", "")[:50]
                    summary += f"  - {file_path}:{result['line']} {snippet}\n"
                else:
                    summary += f"  - {file_path}\n"
            else:
                summary += f"  - {str(result)[:50]}\n"
        if len(data) > 10:
            summary += f"  ... and {len(data) - 10} more results available.\n"
            summary += f"To fetch more: search_repository(query=..., limit=10, offset={len(data[:10])})\n"
        return summary
    elif tool_name == "get_symbol" and isinstance(data, list):
        summary = f"[get_symbol] Found {len(data)} symbols:\n"
        for symbol in data[:10]:  # Include first 10 symbols
            name = symbol.get("name", "?") if isinstance(symbol, dict) else str(symbol)[:50]
            summary += f"  - {name}\n"
        if len(data) > 10:
            summary += f"  ... and {len(data) - 10} more symbols\n"
        return summary
    elif tool_name == "get_tree" and isinstance(data, dict):
        tree = data.get("tree", "")
        file_count = data.get("file_count", 0)
        path = data.get("path", "/")
        summary = f"[get_tree] {path} ({file_count} files):\n"
        return summary + tree
    else:
        try:
            if isinstance(data, (dict, list)):
                data_str = json.dumps(data, default=str)[:500]
            else:
                data_str = str(data)[:500]
        except Exception:
            data_str = str(data)[:500]
        return f"[{tool_name}] Result: {data_str}"
