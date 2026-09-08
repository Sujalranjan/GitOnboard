"""
Symbol inspection tool - returns metadata about ONE symbol.
Reuses RepositoryToolLayer.get_symbol() and QueryLayer for relationships.
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session

from backend.repository_tools.tools import RepositoryToolLayer
from backend.models.fact_store import FactSymbol, FactFile, FactRelationship
from .contracts import InspectSymbolResult, SymbolRelationships, SymbolRelationship
from .utils import detect_language

logger = logging.getLogger(__name__)


def inspect_symbol(
    file_path: str,
    symbol_name: str,
    repo_hash: str,
    db: Optional[Session] = None,
) -> InspectSymbolResult:
    """
    Return metadata about ONE symbol without reading its source.

    CRITICAL: If multiple symbols with same name exist in the file:
    - Return error listing all candidates
    - Let caller specify by symbol_id or qualified_name

    Args:
        file_path: Repository-relative path to file
        symbol_name: Name of symbol to inspect
        repo_hash: UUID v4 of repository (unambiguous)
        db: SQLAlchemy session for DB queries

    Returns:
        InspectSymbolResult with symbol metadata and relationships
    """
    try:
        from backend.models.repository import Repository, Analysis

        # Query for symbols matching file_path + symbol_name
        if not db:
            return InspectSymbolResult(
                symbol_id="",
                name=symbol_name,
                qualified_name=symbol_name,
                symbol_type="unknown",
                file_path=file_path,
                line_start=0,
                line_end=0,
                language=detect_language(file_path),
                success=False,
                error="Database session not available",
            )

        # Get repository by hash (unambiguous)
        repo = db.query(Repository).filter(
            Repository.repository_hash == repo_hash
        ).first()

        if not repo:
            return InspectSymbolResult(
                symbol_id="",
                name=symbol_name,
                qualified_name=symbol_name,
                symbol_type="unknown",
                file_path=file_path,
                line_start=0,
                line_end=0,
                language=detect_language(file_path),
                success=False,
                error=f"Repository not found: {repo_hash}",
            )

        # Get latest completed analysis
        analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status == "Completed"
        ).order_by(Analysis.created_at.desc()).first()

        if not analysis:
            return InspectSymbolResult(
                symbol_id="",
                name=symbol_name,
                qualified_name=symbol_name,
                symbol_type="unknown",
                file_path=file_path,
                line_start=0,
                line_end=0,
                language=detect_language(file_path),
                success=False,
                error=f"No completed analysis for repository: {repo_hash}",
            )

        analysis_id = analysis.id

        # Look up FactFile first
        fact_file = (
            db.query(FactFile)
            .filter(
                FactFile.analysis_id == analysis_id,
                FactFile.path == file_path,
            )
            .first()
        )

        if not fact_file:
            return InspectSymbolResult(
                symbol_id="",
                name=symbol_name,
                qualified_name=symbol_name,
                symbol_type="unknown",
                file_path=file_path,
                line_start=0,
                line_end=0,
                language=detect_language(file_path),
                success=False,
                error=f"File not found in database: {file_path}",
            )

        # Query for all symbols in this file matching the name
        symbols = (
            db.query(FactSymbol)
            .filter(
                FactSymbol.analysis_id == analysis_id,
                FactSymbol.file_id == fact_file.id,
                FactSymbol.name == symbol_name,  # Exact name match
            )
            .all()
        )

        if len(symbols) == 0:
            return InspectSymbolResult(
                symbol_id="",
                name=symbol_name,
                qualified_name=symbol_name,
                symbol_type="unknown",
                file_path=file_path,
                line_start=0,
                line_end=0,
                language=detect_language(file_path),
                success=False,
                error=f"Symbol not found: {symbol_name}",
            )

        elif len(symbols) > 1:
            # Multiple symbols with same name - ambiguous
            candidates = [
                {
                    "symbol_id": sym.id,
                    "name": sym.name,
                    "qualified_name": sym.qualified_name,
                    "symbol_type": sym.symbol_type,
                    "line_start": sym.line_start,
                    "line_end": sym.line_end,
                }
                for sym in symbols
            ]
            return InspectSymbolResult(
                symbol_id="",
                name=symbol_name,
                qualified_name=symbol_name,
                symbol_type="unknown",
                file_path=file_path,
                line_start=0,
                line_end=0,
                language=detect_language(file_path),
                success=False,
                error=f"Multiple symbols found with name '{symbol_name}' in {file_path}",
                candidates=candidates,
            )

        # Exactly one symbol found
        symbol = symbols[0]
        language = detect_language(file_path)

        # Extract metadata
        metadata_json = symbol.metadata_json or {}
        signature = metadata_json.get("signature")
        docstring = metadata_json.get("docstring")

        # Query relationships
        relationships = _get_symbol_relationships(
            db=db,
            symbol_id=symbol.id,
            analysis_id=analysis_id,
        )

        return InspectSymbolResult(
            symbol_id=symbol.id,
            name=symbol.name,
            qualified_name=symbol.qualified_name or symbol.name,
            symbol_type=symbol.symbol_type,
            file_path=file_path,
            line_start=symbol.line_start or 0,
            line_end=symbol.line_end or 0,
            language=language,
            signature=signature,
            docstring=docstring,
            relationships=relationships,
            success=True,
        )

    except Exception as e:
        logger.error(f"Error inspecting symbol {symbol_name} in {file_path}: {e}")
        return InspectSymbolResult(
            symbol_id="",
            name=symbol_name,
            qualified_name=symbol_name,
            symbol_type="unknown",
            file_path=file_path,
            line_start=0,
            line_end=0,
            language=detect_language(file_path),
            success=False,
            error=str(e),
        )


def _get_symbol_relationships(
    db: Session,
    symbol_id: str,
    analysis_id: int,
) -> SymbolRelationships:
    """
    Query relationships for a symbol from FactRelationship table.
    """
    rels = SymbolRelationships()

    try:
        # Query CALLS relationships (what this symbol calls)
        calls_rels = (
            db.query(FactRelationship, FactSymbol.name, FactSymbol.qualified_name, FactFile.path)
            .join(FactSymbol, FactRelationship.to_symbol_id == FactSymbol.id)
            .join(FactFile, FactSymbol.file_id == FactFile.id)
            .filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.rel_type == "CALLS",
                FactRelationship.from_symbol_id == symbol_id,
            )
            .all()
        )
        rels.calls = [
            SymbolRelationship(
                name=name,
                file_path=path,
                symbol_id=rel.to_symbol_id,
                qualified_name=qual_name,
            )
            for rel, name, qual_name, path in calls_rels
        ]

        # Query CALLS relationships (what calls this symbol)
        called_by_rels = (
            db.query(FactRelationship, FactSymbol.name, FactSymbol.qualified_name, FactFile.path)
            .join(FactSymbol, FactRelationship.from_symbol_id == FactSymbol.id)
            .join(FactFile, FactSymbol.file_id == FactFile.id)
            .filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.rel_type == "CALLS",
                FactRelationship.to_symbol_id == symbol_id,
            )
            .all()
        )
        rels.called_by = [
            SymbolRelationship(
                name=name,
                file_path=path,
                symbol_id=rel.from_symbol_id,
                qualified_name=qual_name,
            )
            for rel, name, qual_name, path in called_by_rels
        ]

        # Query IMPORTS relationships
        imports_rels = (
            db.query(FactRelationship, FactSymbol.qualified_name)
            .join(FactSymbol, FactRelationship.to_symbol_id == FactSymbol.id)
            .filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.rel_type == "IMPORTS",
                FactRelationship.from_symbol_id == symbol_id,
            )
            .all()
        )
        rels.imports = [
            {"module": qual_name or "unknown"}
            for rel, qual_name in imports_rels
        ]

        # Query IMPORTED_BY relationships
        imported_by_rels = (
            db.query(FactFile.path)
            .join(FactSymbol, FactFile.id == FactSymbol.file_id)
            .join(FactRelationship, FactRelationship.from_symbol_id == FactSymbol.id)
            .filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.rel_type == "IMPORTS",
                FactRelationship.to_symbol_id == symbol_id,
            )
            .distinct()
            .all()
        )
        rels.imported_by = [path[0] for path in imported_by_rels]

        # Query USES relationships
        uses_rels = (
            db.query(FactRelationship, FactSymbol.name, FactSymbol.qualified_name, FactFile.path)
            .join(FactSymbol, FactRelationship.to_symbol_id == FactSymbol.id)
            .join(FactFile, FactSymbol.file_id == FactFile.id)
            .filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.rel_type == "USES",
                FactRelationship.from_symbol_id == symbol_id,
            )
            .all()
        )
        rels.uses = [
            SymbolRelationship(
                name=name,
                file_path=path,
                symbol_id=rel.to_symbol_id,
                qualified_name=qual_name,
            )
            for rel, name, qual_name, path in uses_rels
        ]

        # Query USED_BY relationships
        used_by_rels = (
            db.query(FactRelationship, FactSymbol.name, FactSymbol.qualified_name, FactFile.path)
            .join(FactSymbol, FactRelationship.from_symbol_id == FactSymbol.id)
            .join(FactFile, FactSymbol.file_id == FactFile.id)
            .filter(
                FactRelationship.analysis_id == analysis_id,
                FactRelationship.rel_type == "USES",
                FactRelationship.to_symbol_id == symbol_id,
            )
            .all()
        )
        rels.used_by = [
            SymbolRelationship(
                name=name,
                file_path=path,
                symbol_id=rel.from_symbol_id,
                qualified_name=qual_name,
            )
            for rel, name, qual_name, path in used_by_rels
        ]

    except Exception as e:
        logger.warning(f"Error querying relationships for symbol {symbol_id}: {e}")

    return rels
