"""
File inspection tool - returns file structure without full source.
Reuses RepositoryToolLayer.get_file_outline() for symbol discovery.
"""
import logging
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session

from backend.repository_tools.tools import RepositoryToolLayer
from backend.models.fact_store import FactFile, FactSymbol
from .contracts import InspectFileResult, FileSymbol
from .utils import detect_language, calculate_file_size_kb

logger = logging.getLogger(__name__)


def inspect_file(
    file_path: str,
    repo_name: str = "default",
    db: Optional[Session] = None,
    repo_root: Optional[str] = None,
    user_id: Optional[int] = None,
    analysis_id: Optional[int] = None,
) -> InspectFileResult:
    """
    Return file structure and symbol outline WITHOUT full source.

    Args:
        file_path: Repository-relative path to file (e.g. "backend/app.py")
        repo_name: Repository name for lookup
        db: SQLAlchemy session for DB queries
        repo_root: Optional repository root path (for active worktree)
        user_id: User ID for multi-tenant scenarios
        analysis_id: Optional analysis ID (bypasses repo_name lookup)

    Returns:
        InspectFileResult with file metadata and symbols
    """
    try:
        # PHASE 2L.2: Validate analysis context to prevent silent failures
        if analysis_id is None and (repo_name is None or repo_name == "default"):
            # Missing analysis context - return explicit error rather than silent empty
            return InspectFileResult(
                file_path=file_path,
                language="unknown",
                total_lines=0,
                file_size_kb=0.0,
                symbols=[],
                success=False,
                error="REPOSITORY_CONTEXT_ERROR: analysis_id is required for file inspection when repo_name='default'. "
                      "Please provide analysis_id explicitly."
            )

        # Initialize RepositoryToolLayer
        tool_layer = RepositoryToolLayer(
            repo_name=repo_name,
            analysis_id=analysis_id,
            db=db,
            repo_root=repo_root,
            user_id=user_id,
        )

        # Get file outline using RepositoryToolLayer
        outline = tool_layer.get_file_outline(file_path)

        # Extract language from file extension
        language = detect_language(file_path)

        # PART E FIX: Check if file exists in FactStore before proceeding
        fact_file = None
        if db and tool_layer.analysis_id:
            fact_file = (
                db.query(FactFile)
                .filter(
                    FactFile.analysis_id == tool_layer.analysis_id,
                    FactFile.path == file_path,
                )
                .first()
            )
            if not fact_file:
                # File not found in FactStore for this analysis
                return InspectFileResult(
                    file_path=file_path,
                    language=language,
                    total_lines=0,
                    file_size_kb=0.0,
                    symbols=[],
                    success=False,
                    error=f"FILE_NOT_FOUND: Repository file '{file_path}' does not exist or has not been analyzed.",
                )

        # Get file size and metadata from FactFile
        total_lines = 0
        file_size_kb = 0.0

        if db and tool_layer.analysis_id and fact_file:
            file_size_kb = calculate_file_size_kb(fact_file.size or 0)
        else:
            # Try filesystem fallback
            if tool_layer.repo_root:
                target = tool_layer.repo_root / file_path
                if target.exists():
                    file_size_kb = calculate_file_size_kb(target.stat().st_size)
                    with open(target, "r", encoding="utf-8", errors="replace") as f:
                        total_lines = sum(1 for _ in f)

        # Get actual total_lines from reading file if we have tool_layer
        if total_lines == 0:
            try:
                read_result = tool_layer.read_file(file_path, 1, None)
                total_lines = read_result.get("total_lines", 0)
            except Exception:
                # File doesn't exist or can't be read
                total_lines = 0

        # Convert outline symbols to FileSymbol objects
        symbols: list[FileSymbol] = []
        for sym in outline.get("symbols", []):
            line_end = sym.get("line_end")
            if line_end is None:
                line_end = sym.get("line_start", 0)  # Use line_start as fallback
            symbols.append(
                FileSymbol(
                    name=sym["name"],
                    qualified_name=sym.get("qualified_name", sym["name"]),
                    symbol_type=sym["type"],
                    line_start=sym.get("line_start", 0),
                    line_end=line_end,
                    symbol_id=sym.get("symbol_id", f"{file_path}:{sym['name']}"),
                    parent_symbol=sym.get("parent_symbol"),
                )
            )

        return InspectFileResult(
            file_path=file_path,
            language=language,
            total_lines=total_lines,
            file_size_kb=file_size_kb,
            symbols=symbols,
            success=True,
        )

    except Exception as e:
        logger.error(f"Error inspecting file {file_path}: {e}")
        return InspectFileResult(
            file_path=file_path,
            language="unknown",
            total_lines=0,
            file_size_kb=0.0,
            symbols=[],
            success=False,
            error=str(e),
        )
