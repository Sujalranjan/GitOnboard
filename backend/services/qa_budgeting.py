"""
Token budgeting, provider constraints, and deterministic message compaction for QALoop.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from backend.config import settings

logger = logging.getLogger(__name__)


def derive_provider_budget_profile(
    model: Optional[str],
    provider: Optional[str],
    llm_service: Any,
) -> Dict[str, Any]:
    """
    Derive the 4 distinct constraints and safe application budget for the active provider/model:
    - context_window
    - input_tpm
    - single_request_limit
    - application_safety_budget
    """
    model_name = (model or "").strip()
    provider_str = (provider or "").strip().lower()

    # 1. Check provider if explicitly set
    if not provider_str:
        # 2. Check active providers attached to llm_service
        active_providers = getattr(llm_service, "providers", [])
        if active_providers and hasattr(active_providers[0], "provider_name"):
            provider_str = active_providers[0].provider_name.lower()

    # 3. If still unknown, infer strictly from model name
    if not provider_str:
        m_lower = model_name.lower()
        if "gemini" in m_lower:
            provider_str = "gemini"
        elif "groq" in m_lower or "gpt-oss" in m_lower:
            provider_str = "groq"
        elif "openrouter" in m_lower or "nemotron" in m_lower:
            provider_str = "openrouter"
        elif "qwen" in m_lower or "llama" in m_lower:
            provider_str = "ollama"

    if not provider_str:
        logger.error(
            f"[QALoop] Provider could not be determined for token budgeting (model='{model}', "
            f"llm_service={llm_service}). Missing provider information."
        )
        raise ValueError(
            f"[QALoop] Provider information is required for token budgeting but was not provided and could not be determined for model='{model}'."
        )

    if provider_str == "groq":
        context_window = settings.groq_context_window
        input_tpm = settings.groq_input_tpm
        single_request_limit = settings.groq_single_request_limit
        safety_margin = settings.groq_safety_margin_tokens
        control_reservation = settings.groq_control_reservation_tokens
        output_reservation = settings.groq_output_reservation_tokens
    elif provider_str == "gemini":
        context_window = settings.gemini_context_window
        input_tpm = settings.gemini_input_tpm
        single_request_limit = settings.gemini_single_request_limit
        safety_margin = settings.gemini_safety_margin_tokens
        control_reservation = settings.gemini_control_reservation_tokens
        output_reservation = settings.gemini_output_reservation_tokens
    elif provider_str == "openrouter":
        context_window = settings.openrouter_context_window
        input_tpm = settings.openrouter_input_tpm
        single_request_limit = settings.openrouter_single_request_limit or 100000
        safety_margin = settings.openrouter_safety_margin_tokens
        control_reservation = settings.openrouter_control_reservation_tokens
        output_reservation = settings.openrouter_output_reservation_tokens
    else:
        # Local / Ollama
        context_window = 32768
        input_tpm = 0
        single_request_limit = 32768
        safety_margin = 1000
        control_reservation = 100
        output_reservation = 2048

    # Calculate safe application budget
    effective_limit = single_request_limit
    if input_tpm and input_tpm > 0:
        effective_limit = min(effective_limit, input_tpm)

    safe_budget = max(
        1000,
        effective_limit - safety_margin - control_reservation - output_reservation
    )

    return {
        "provider": provider_str,
        "model": model or model_name,
        "context_window": context_window,
        "input_tpm": input_tpm,
        "single_request_limit": single_request_limit,
        "safety_margin": safety_margin,
        "control_reservation": control_reservation,
        "output_reservation": output_reservation,
        "safe_budget": safe_budget,
    }


def extract_read_file_metadata(content: str) -> Optional[Dict[str, Any]]:
    """Extract path and optional line ranges from tool observation content or assistant tool calls."""
    if not content:
        return None

    # 1. Standard formatted read_file observation:
    # "[read_file] path/to/file.js lines 25-158: 10604 chars (total: 158)"
    # or "[read_file] path/to/file.js lines 1-13:"
    m = re.search(r"\[read_file\]\s+([^\s:]+)(?:\s+lines\s+(\d+)-(\d+))?", content)
    if m:
        path = m.group(1).strip()
        start = int(m.group(2)) if m.group(2) else None
        end = int(m.group(3)) if m.group(3) else None
        return {"path": path, "start_line": start, "end_line": end}

    # 2. Assistant tool call string or pythonic syntax:
    # "read_file(path='app/controllers/trial.js', start_line=1, end_line=13)"
    m = re.search(r"read_file\(\s*path=[\x27\x22]([^\x27\x22]+)[\x27\x22]", content)
    if m:
        path = m.group(1).strip()
        s_m = re.search(r"start_line=(\d+)", content)
        e_m = re.search(r"end_line=(\d+)", content)
        start = int(s_m.group(1)) if s_m else None
        end = int(e_m.group(1)) if e_m else None
        return {"path": path, "start_line": start, "end_line": end}

    # 3. Legacy phrase: "Showing 50 lines of ARCHITECTURE.md: line 1 to 50"
    m = re.search(r"lines of\s+([^\s:]+)(?::\s*line\s+(\d+)\s+to\s+(\d+))?", content)
    if m:
        path = m.group(1).strip()
        start = int(m.group(2)) if m.group(2) else None
        end = int(m.group(3)) if m.group(3) else None
        return {"path": path, "start_line": start, "end_line": end}

    # 4. JSON arguments snippet
    m = re.search(r'["\']path["\']\s*:\s*["\']([^"\']+)["\']', content)
    if m and ("read_file" in content or "lines" in content):
        path = m.group(1).strip()
        s_m = re.search(r'["\']start_line["\']\s*:\s*(\d+)', content)
        e_m = re.search(r'["\']end_line["\']\s*:\s*(\d+)', content)
        start = int(s_m.group(1)) if s_m else None
        end = int(e_m.group(1)) if e_m else None
        return {"path": path, "start_line": start, "end_line": end}

    return None


def compact_messages_deterministically(
    messages: List[Dict[str, Any]],
    target_tokens: int,
) -> List[Dict[str, Any]]:
    """
    Deterministic, rule-based working context compaction. ZERO LLM summarization.
    Keeps raw evidence separately in QALoopTurn / Evidence Store.

    Pass 1: Deduplicate redundant file reads for the same path by tracking inspected line ranges.
            Earlier slices of the same file are compacted to high-level coverage references.
    Pass 2: Compact older tool observations (>1 turn old) to structural outlines or summaries.
    Pass 3: Truncate oversized recent observation bodies to stay within target_tokens.
    """
    if len(messages) <= 1:
        return messages

    user_query_msg = messages[0]
    conversation = [dict(m) for m in messages[1:]]

    # Pass 1: Deduplicate file reads (keep latest read per file path, summarize earlier ranges)
    # Map path -> list of line ranges seen across all reads to preserve coverage knowledge
    file_coverage: Dict[str, List[str]] = {}
    for msg in conversation:
        content = msg.get("content", "")
        meta = extract_read_file_metadata(content)
        if meta and meta["path"]:
            path = meta["path"]
            rng = f"{meta['start_line']}-{meta['end_line']}" if meta["start_line"] and meta["end_line"] else "inspected"
            file_coverage.setdefault(path, []).append(rng)

    seen_paths = set()
    for idx in range(len(conversation) - 1, -1, -1):
        msg = conversation[idx]
        content = msg.get("content", "")
        meta = extract_read_file_metadata(content)
        if meta and meta["path"]:
            path = meta["path"]
            if path in seen_paths:
                ranges_str = ", ".join(file_coverage.get(path, []))
                lines = content.splitlines()
                header = lines[0] if lines else f"[read_file] {path}"
                msg["content"] = f"{header}\n... [Deduplicated older observation for '{path}'; covered ranges: {ranges_str}] ..."
            else:
                seen_paths.add(path)

    # Pass 2: Compact older non-source observations (> 2 messages from the end)
    # Never degrade source code observations ([read_file] or "Showing X lines") to outlines
    # unless they are deduplicated duplicates from Pass 1.
    for idx in range(len(conversation) - 2):
        msg = conversation[idx]
        content = msg.get("content", "")
        if "[Deduplicated" in content:
            continue
        meta = extract_read_file_metadata(content)
        # Protect verified read_file evidence from unconditional outline degradation
        if meta and meta.get("path"):
            continue
        if len(content) > 300:
            lines = content.splitlines()
            header = lines[0] if lines else ""
            msg["content"] = f"{header}\n... [Older observation compacted to outline ({len(lines)} lines)] ..."

    # Pass 3: If still heavy, compact non-deduplicated earlier non-source messages
    for idx in range(len(conversation) - 1):
        msg = conversation[idx]
        content = msg.get("content", "")
        if "[Deduplicated" in content:
            continue
        meta = extract_read_file_metadata(content)
        if meta and meta.get("path"):
            continue
        if len(content) > 200:
            msg["content"] = content[:150] + "\n... [Compacted] ..."

    return [user_query_msg] + conversation
