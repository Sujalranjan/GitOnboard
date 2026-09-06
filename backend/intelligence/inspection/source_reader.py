"""
Source code reading tools - read_symbol(), read_lines(), read_file().
Uses RepositoryToolLayer.read_file() for the actual file access.
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session

from backend.repository_tools.tools import RepositoryToolLayer
from backend.models.fact_store import FactFile, FactSymbol
from .contracts import SourceReadResult
from .utils import detect_language, estimate_tokens, calculate_file_size_kb, number_source_lines

logger = logging.getLogger(__name__)

# Maximum file size to read without warning
MAX_FILE_SIZE_KB = 50


def read_symbol(
    file_path: str,
    symbol_name: str,
    repo_name: str = "default",
    db: Optional[Session] = None,
    repo_root: Optional[str] = None,
    user_id: Optional[int] = None,
    analysis_id: Optional[int] = None,
) -> SourceReadResult:
    """
    Read EXACT source of ONE symbol using canonical line boundaries.

    CRITICAL: Uses FactSymbol.line_start/line_end for exact boundaries.
    If symbol_name is ambiguous (multiple symbols with same name):
    - Return error listing all candidates
    - Caller must specify by symbol_id or qualified_name

    Args:
        file_path: Repository-relative path to file
        symbol_name: Name of symbol to read
        repo_name: Repository name for lookup
        db: SQLAlchemy session
        repo_root: Optional repository root path
        user_id: User ID for multi-tenant scenarios
        analysis_id: Optional analysis ID (bypasses repo_name lookup)

    Returns:
        SourceReadResult with symbol source code
    """
    try:
        # Initialize RepositoryToolLayer
        tool_layer = RepositoryToolLayer(
            repo_name=repo_name,
            analysis_id=analysis_id,
            db=db,
            repo_root=repo_root,
            user_id=user_id,
        )

        # Resolve symbol canonically
        if not db or not tool_layer.analysis_id:
            return SourceReadResult(
                file_path=file_path,
                source="",
                raw_text="",
                line_start=0,
                line_end=0,
                total_lines=0,
                file_size_kb=0.0,
                language=detect_language(file_path),
                symbol_name=symbol_name,
                success=False,
                error="Database session or analysis_id not available",
            )

        # Look up FactFile
        fact_file = (
            db.query(FactFile)
            .filter(
                FactFile.analysis_id == tool_layer.analysis_id,
                FactFile.path == file_path,
            )
            .first()
        )

        if not fact_file:
            return SourceReadResult(
                file_path=file_path,
                source="",
                raw_text="",
                line_start=0,
                line_end=0,
                total_lines=0,
                file_size_kb=0.0,
                language=detect_language(file_path),
                symbol_name=symbol_name,
                success=False,
                error=f"File not found: {file_path}",
            )

        # Query for all symbols matching name in file
        symbols = (
            db.query(FactSymbol)
            .filter(
                FactSymbol.analysis_id == tool_layer.analysis_id,
                FactSymbol.file_id == fact_file.id,
                FactSymbol.name == symbol_name,
            )
            .all()
        )

        if len(symbols) == 0:
            return SourceReadResult(
                file_path=file_path,
                source="",
                raw_text="",
                line_start=0,
                line_end=0,
                total_lines=0,
                file_size_kb=0.0,
                language=detect_language(file_path),
                symbol_name=symbol_name,
                success=False,
                error=f"Symbol not found: {symbol_name}",
            )

        elif len(symbols) > 1:
            # Ambiguous - multiple symbols with same name
            candidates = [
                {
                    "symbol_id": sym.id,
                    "qualified_name": sym.qualified_name,
                    "line_start": sym.line_start,
                    "line_end": sym.line_end,
                }
                for sym in symbols
            ]
            return SourceReadResult(
                file_path=file_path,
                source="",
                raw_text="",
                line_start=0,
                line_end=0,
                total_lines=0,
                file_size_kb=0.0,
                language=detect_language(file_path),
                symbol_name=symbol_name,
                success=False,
                error=f"Multiple symbols found with name '{symbol_name}'",
            )

        # Exactly one symbol - get its source
        symbol = symbols[0]
        line_start = symbol.line_start or 0
        line_end = symbol.line_end or 0

        if line_start == 0 or line_end == 0:
            return SourceReadResult(
                file_path=file_path,
                source="",
                raw_text="",
                line_start=0,
                line_end=0,
                total_lines=0,
                file_size_kb=0.0,
                language=detect_language(file_path),
                symbol_id=symbol.id,
                symbol_name=symbol.name,
                success=False,
                error=f"Symbol has no line boundaries: {symbol_name}",
            )

        # Read the file using RepositoryToolLayer
        read_result = tool_layer.read_file(file_path, line_start, line_end)

        language = detect_language(file_path)
        raw_text = read_result["raw_text"]
        total_lines = read_result["total_lines"]
        file_size_kb = calculate_file_size_kb(fact_file.size or 0)

        # Number the source lines
        source = number_source_lines(raw_text, line_start)

        # Estimate tokens
        estimated_tokens = estimate_tokens(raw_text)

        return SourceReadResult(
            file_path=file_path,
            source=source,
            raw_text=raw_text,
            line_start=line_start,
            line_end=line_end,
            total_lines=total_lines,
            file_size_kb=file_size_kb,
            language=language,
            symbol_id=symbol.id,
            symbol_name=symbol.name,
            estimated_tokens=estimated_tokens,
            success=True,
        )

    except Exception as e:
        logger.error(f"Error reading symbol {symbol_name} in {file_path}: {e}")
        return SourceReadResult(
            file_path=file_path,
            source="",
            raw_text="",
            line_start=0,
            line_end=0,
            total_lines=0,
            file_size_kb=0.0,
            language=detect_language(file_path),
            symbol_name=symbol_name,
            success=False,
            error=str(e),
        )


def read_lines(
    file_path: str,
    start_line: int,
    end_line: int,
    repo_name: str = "default",
    db: Optional[Session] = None,
    repo_root: Optional[str] = None,
    user_id: Optional[int] = None,
) -> SourceReadResult:
    """
    Read explicit line range from a file (validated).

    Validates:
    - file_path exists
    - 1 <= start_line <= total_lines
    - start_line <= end_line <= total_lines

    Args:
        file_path: Repository-relative path to file
        start_line: Starting line number (1-based)
        end_line: Ending line number (1-based, inclusive)
        repo_name: Repository name
        db: SQLAlchemy session
        repo_root: Optional repository root path
        user_id: User ID for multi-tenant scenarios

    Returns:
        SourceReadResult with requested line range
    """
    try:
        # Initialize RepositoryToolLayer
        tool_layer = RepositoryToolLayer(
            repo_name=repo_name,
            db=db,
            repo_root=repo_root,
            user_id=user_id,
        )

        # Validate line numbers are positive
        if start_line < 1 or end_line < 1:
            return SourceReadResult(
                file_path=file_path,
                source="",
                raw_text="",
                line_start=start_line,
                line_end=end_line,
                total_lines=0,
                file_size_kb=0.0,
                language=detect_language(file_path),
                success=False,
                error=f"Invalid line numbers: start_line={start_line}, end_line={end_line} (must be >= 1)",
            )

        if start_line > end_line:
            return SourceReadResult(
                file_path=file_path,
                source="",
                raw_text="",
                line_start=start_line,
                line_end=end_line,
                total_lines=0,
                file_size_kb=0.0,
                language=detect_language(file_path),
                success=False,
                error=f"Invalid line range: start_line={start_line} > end_line={end_line}",
            )

        # Try to read the file - this will validate line bounds
        try:
            read_result = tool_layer.read_file(file_path, start_line, end_line)
        except Exception as e:
            return SourceReadResult(
                file_path=file_path,
                source="",
                raw_text="",
                line_start=start_line,
                line_end=end_line,
                total_lines=0,
                file_size_kb=0.0,
                language=detect_language(file_path),
                success=False,
                error=str(e),
            )

        language = detect_language(file_path)
        raw_text = read_result["raw_text"]
        actual_start = read_result["start_line"]
        actual_end = read_result["end_line"]
        total_lines = read_result["total_lines"]

        # Get file size
        file_size_kb = 0.0
        if db and tool_layer.analysis_id:
            fact_file = (
                db.query(FactFile)
                .filter(
                    FactFile.analysis_id == tool_layer.analysis_id,
                    FactFile.path == file_path,
                )
                .first()
            )
            if fact_file:
                file_size_kb = calculate_file_size_kb(fact_file.size or 0)

        # Number the source lines
        source = number_source_lines(raw_text, actual_start)

        # Estimate tokens
        estimated_tokens = estimate_tokens(raw_text)

        return SourceReadResult(
            file_path=file_path,
            source=source,
            raw_text=raw_text,
            line_start=actual_start,
            line_end=actual_end,
            total_lines=total_lines,
            file_size_kb=file_size_kb,
            language=language,
            estimated_tokens=estimated_tokens,
            success=True,
        )

    except Exception as e:
        logger.error(f"Error reading lines {start_line}-{end_line} from {file_path}: {e}")
        return SourceReadResult(
            file_path=file_path,
            source="",
            raw_text="",
            line_start=start_line,
            line_end=end_line,
            total_lines=0,
            file_size_kb=0.0,
            language=detect_language(file_path),
            success=False,
            error=str(e),
        )


def read_file(
    file_path: str,
    repo_name: str = "default",
    db: Optional[Session] = None,
    repo_root: Optional[str] = None,
    user_id: Optional[int] = None,
) -> SourceReadResult:
    """
    Read entire file (expensive operation).

    If file > 50KB:
    - Do NOT silently truncate
    - Return structured response with warning
    - Suggest inspect_file() + read_symbol() instead

    Args:
        file_path: Repository-relative path to file
        repo_name: Repository name
        db: SQLAlchemy session
        repo_root: Optional repository root path
        user_id: User ID for multi-tenant scenarios

    Returns:
        SourceReadResult with entire file content or warning
    """
    try:
        # Initialize RepositoryToolLayer
        tool_layer = RepositoryToolLayer(
            repo_name=repo_name,
            db=db,
            repo_root=repo_root,
            user_id=user_id,
        )

        # Get file size first
        file_size_kb = 0.0
        if db and tool_layer.analysis_id:
            fact_file = (
                db.query(FactFile)
                .filter(
                    FactFile.analysis_id == tool_layer.analysis_id,
                    FactFile.path == file_path,
                )
                .first()
            )
            if fact_file:
                file_size_kb = calculate_file_size_kb(fact_file.size or 0)

                # Check if file is too large
                if file_size_kb > MAX_FILE_SIZE_KB:
                    return SourceReadResult(
                        file_path=file_path,
                        source="",
                        raw_text="",
                        line_start=0,
                        line_end=0,
                        total_lines=0,
                        file_size_kb=file_size_kb,
                        language=detect_language(file_path),
                        success=False,
                        error=f"File too large ({file_size_kb}KB > {MAX_FILE_SIZE_KB}KB)",
                        warning=f"Use inspect_file() + read_symbol() instead for large files",
                    )

        # Read entire file (1 to None reads everything)
        read_result = tool_layer.read_file(file_path, 1, None)

        language = detect_language(file_path)
        raw_text = read_result["raw_text"]
        total_lines = read_result["total_lines"]
        start_line = 1
        end_line = total_lines

        # Number the source lines
        source = number_source_lines(raw_text, start_line)

        # Estimate tokens
        estimated_tokens = estimate_tokens(raw_text)

        # Warn if file is large
        warning = None
        if file_size_kb > MAX_FILE_SIZE_KB * 0.8:
            warning = f"Large file ({file_size_kb}KB). Consider using read_symbol() for specific functions."

        return SourceReadResult(
            file_path=file_path,
            source=source,
            raw_text=raw_text,
            line_start=start_line,
            line_end=end_line,
            total_lines=total_lines,
            file_size_kb=file_size_kb,
            language=language,
            estimated_tokens=estimated_tokens,
            success=True,
            warning=warning,
        )

    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return SourceReadResult(
            file_path=file_path,
            source="",
            raw_text="",
            line_start=0,
            line_end=0,
            total_lines=0,
            file_size_kb=0.0,
            language=detect_language(file_path),
            success=False,
            error=str(e),
        )
