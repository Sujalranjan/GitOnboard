"""
Contract and file generation helpers for VerificationOrchestrator.
Handles fallback keyword contracts, prompt keyword extraction, file synthesis, and scaffolding.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.models.implementation import AgentRun

logger = logging.getLogger(__name__)


def get_active_agent_run(db: Optional[Session], task_id: str) -> Optional[AgentRun]:
    """Returns the most recently started AgentRun for task_id, if any."""
    if db is None:
        return None
    return (
        db.query(AgentRun)
        .filter(AgentRun.task_id == task_id)
        .order_by(AgentRun.started_at.desc())
        .first()
    )


def extract_keywords(prompt: str) -> List[str]:
    """Extract meaningful keywords from a natural language prompt for impact analysis search."""
    stop_words = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "has", "have", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "that", "this", "it", "i",
        "we", "you", "they", "my", "your", "our", "add", "create", "new",
        "implement", "build", "make", "use", "using", "need", "want",
    }
    words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', prompt.lower())
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:10]


def fallback_contract(prompt: str) -> Dict[str, Any]:
    """Generate a minimal contract from keyword matching when LLM is unavailable."""
    endpoints = []
    if "auth" in prompt.lower() or "login" in prompt.lower():
        endpoints = ["POST /api/auth/login", "GET /api/auth/me"]
    elif "todo" in prompt.lower() or "api" in prompt.lower():
        endpoints = ["POST /api/todos", "GET /api/todos"]
    else:
        endpoints = ["POST /api/resource", "GET /api/resource"]

    return {
        "id": f"contract-{int(time.time())}",
        "requirement": prompt,
        "title": prompt[:60],
        "required_endpoints": endpoints,
        "expected_components": [],
        "affected_components": [],
        "invariants": [
            "Request payload validation required",
            "Error handling for invalid inputs",
        ],
        "required_tests": [
            "Test verifying success response on valid input",
            "Test verifying error response on invalid input",
        ],
        "acceptance_criteria": [
            "Request payload validation required",
            "Error handling for invalid inputs",
        ],
        "security_considerations": ["Input sanitization", "Error message safety"],
    }


def write_generated_files(
    wt_path: Path,
    generated_code: str,
    components: List[Dict[str, Any]],
) -> List[str]:
    """
    Parse LLM-generated multi-file output and write files to worktree.
    Expected format:
      // FILE: path/to/file.ext
      <code>
      // END_FILE
    """
    files_written: List[str] = []

    file_pattern = re.compile(
        r'(?://|#)\s*FILE:\s*(.+?)\s*\n(.*?)(?:(?://|#)\s*END_FILE|(?=(?://|#)\s*FILE:)|\Z)',
        re.DOTALL,
    )
    matches = file_pattern.findall(generated_code)

    if matches:
        for file_path_str, code_content in matches:
            file_path_str = file_path_str.strip().strip('"').strip("'")
            code_content = code_content.strip()
            if not code_content:
                continue

            target = wt_path / file_path_str
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code_content + "\n", encoding="utf-8")
            files_written.append(file_path_str)
            logger.debug(f"Orchestrator: Wrote generated file: {file_path_str}")

    return files_written


def write_scaffold(
    wt_path: Path,
    components: List[Dict[str, Any]],
    requirement: str,
) -> List[str]:
    """Write minimal scaffold files when LLM is unavailable."""
    files_written: List[str] = []
    for comp in components:
        file_path = comp.get("file", "")
        if not file_path:
            continue
        target = wt_path / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        symbol = comp.get("symbol", "implementation")
        scaffold = (
            f"// Auto-generated scaffold for: {requirement[:80]}\n"
            f"// Component: {file_path} :: {symbol}\n"
            f"// TODO: Implement {symbol}\n\n"
            f"export default function {symbol}() {{\n"
            f"  throw new Error('Not implemented: {symbol}');\n"
            f"}}\n"
        )
        target.write_text(scaffold, encoding="utf-8")
        files_written.append(file_path)
    return files_written


def deterministic_repair(
    wt_path: Path,
    components: List[str],
    defects: Any,
) -> None:
    """Apply basic deterministic fixes when LLM is unavailable."""
    from backend.verification.schemas import DefectCategory
    for comp_path in components:
        target = wt_path / comp_path
        if not target.exists():
            continue
        try:
            content = target.read_text(encoding="utf-8")
            for d in defects:
                if d.category == DefectCategory.STATIC_IMPORT_MISSING.value and d.symbol:
                    if d.symbol not in content:
                        content = f"// Auto-import for repair: {d.symbol}\n" + content
            target.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Deterministic repair failed for {comp_path}: {e}")
