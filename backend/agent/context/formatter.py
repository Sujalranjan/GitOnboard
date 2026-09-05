"""
RepositoryContext Formatter: Converts RepositoryContext to LLM-consumable text.

Formats assembled repository evidence into bounded text suitable for injection
into LLM system prompts or context windows.
"""
import logging
from typing import Dict, Any, List, Optional
from backend.agent.context.contracts import RepositoryContext, ContextEvidence

logger = logging.getLogger(__name__)


class RepositoryContextFormatter:
    """Formats RepositoryContext into LLM-consumable text blocks."""

    @staticmethod
    def format_to_system_prompt_block(
        context: RepositoryContext,
        max_chars: int = 8000,
        include_evidence_provenance: bool = True,
    ) -> str:
        """
        Format RepositoryContext into a system prompt block.

        Includes:
        - Repository understanding contract status
        - Key capabilities discovered
        - Relevant files and symbols
        - Architectural constraints
        - Known unknowns

        Args:
            context: RepositoryContext object
            max_chars: Maximum character length of output (default 8000)
            include_evidence_provenance: Include source provenance (default True)

        Returns:
            Formatted text block ready for LLM system prompt injection
        """
        lines = []

        # 1. Header
        lines.append("### REPOSITORY_CONTEXT")
        lines.append("")

        # 2. Understanding contract status
        lines.append(f"Requirement: {context.requirement[:100]}")
        lines.append(f"Completeness: {context.contract.completeness.value}")
        if context.contract.explanation:
            lines.append(f"Status: {context.contract.explanation[:150]}")
        lines.append("")

        # 3. Known capabilities
        if context.capabilities:
            lines.append("Matched Capabilities:")
            for cap in context.capabilities[:5]:  # Top 5
                cap_name = cap.get("name", "?")
                cap_type = cap.get("type", "")
                lines.append(f"  - {cap_name} ({cap_type})")
            lines.append("")

        # 4. Relevant files
        if context.relevant_files:
            lines.append(f"Relevant Files ({len(context.relevant_files)}):")
            for file_path in context.relevant_files[:10]:  # Top 10
                lines.append(f"  - {file_path}")
            if len(context.relevant_files) > 10:
                lines.append(f"  ... and {len(context.relevant_files) - 10} more")
            lines.append("")

        # 5. Relevant symbols
        if context.relevant_symbols:
            lines.append(f"Relevant Symbols ({len(context.relevant_symbols)}):")
            for sym in context.relevant_symbols[:10]:  # Top 10
                sym_name = sym.get("name", "?")
                sym_kind = sym.get("kind", sym.get("symbol_type", ""))
                sym_file = sym.get("file_path", "?")
                lines.append(f"  - {sym_name} ({sym_kind}, {sym_file})")
            if len(context.relevant_symbols) > 10:
                lines.append(f"  ... and {len(context.relevant_symbols) - 10} more")
            lines.append("")

        # 6. Architectural patterns
        if context.architecture_constraints:
            lines.append("Architectural Context:")
            for constraint in context.architecture_constraints[:5]:
                lines.append(f"  - {constraint}")
            lines.append("")

        # 7. Dependencies
        if context.relevant_dependencies:
            lines.append(f"Dependencies ({len(context.relevant_dependencies)}):")
            for dep in context.relevant_dependencies[:8]:  # Top 8
                dep_name = dep.get("name", "?")
                dep_version = dep.get("version", "")
                version_str = f" ({dep_version})" if dep_version else ""
                lines.append(f"  - {dep_name}{version_str}")
            if len(context.relevant_dependencies) > 8:
                lines.append(f"  ... and {len(context.relevant_dependencies) - 8} more")
            lines.append("")

        # 8. Database objects
        if context.relevant_db_objects:
            lines.append(f"Database Objects ({len(context.relevant_db_objects)}):")
            for db_obj in context.relevant_db_objects[:5]:
                obj_name = db_obj.get("name", "?")
                obj_type = db_obj.get("object_type", "")
                lines.append(f"  - {obj_name} ({obj_type})")
            if len(context.relevant_db_objects) > 5:
                lines.append(f"  ... and {len(context.relevant_db_objects) - 5} more")
            lines.append("")

        # 9. Known unknowns (explicit missing facts)
        if context.unknowns:
            lines.append("Known Unknowns (Missing Evidence):")
            for unknown in context.unknowns[:5]:  # Top 5
                lines.append(f"  - {unknown[:120]}")
            if len(context.unknowns) > 5:
                lines.append(f"  ... and {len(context.unknowns) - 5} more")
            lines.append("")

        # 10. Evidence provenance (optional, for debugging)
        if include_evidence_provenance and context.evidence:
            lines.append(f"Evidence Items ({len(context.evidence)} sources):")
            for evidence in context.evidence[:8]:  # Top 8
                source_type = evidence.source_type
                source_id = evidence.source_id[:30]
                confidence = evidence.confidence
                lines.append(f"  - {source_type} '{source_id}' (confidence: {confidence:.2f})")
            if len(context.evidence) > 8:
                lines.append(f"  ... and {len(context.evidence) - 8} more sources")
            lines.append("")

        # 11. Metadata (optional)
        if context.metadata:
            duration_ms = context.metadata.get("duration_ms", 0)
            evidence_count = context.metadata.get("evidence_count", 0)
            lines.append(f"Assembly Duration: {duration_ms:.0f}ms | Evidence Items: {evidence_count}")

        # Join lines and enforce character limit
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars]
            text = text.rsplit("\n", 1)[0]  # Remove partial line
            text += f"\n... (truncated, {len(context.evidence)} total evidence items available)"

        return text

    @staticmethod
    def format_as_json_summary(context: RepositoryContext) -> Dict[str, Any]:
        """
        Format RepositoryContext as a JSON-serializable summary.

        Useful for API responses and debugging.

        Returns:
            Dictionary with context summary
        """
        return {
            "version": context.version,
            "repository_id": context.repository_id,
            "requirement": context.requirement,
            "completeness": context.contract.completeness.value,
            "satisfied_categories": context.contract.satisfied_categories,
            "missing_categories": context.contract.missing_categories,
            "counts": {
                "capabilities": len(context.capabilities),
                "files": len(context.relevant_files),
                "symbols": len(context.relevant_symbols),
                "routes": len(context.relevant_routes),
                "db_objects": len(context.relevant_db_objects),
                "dependencies": len(context.relevant_dependencies),
                "evidence": len(context.evidence),
                "unknowns": len(context.unknowns),
            },
            "unknowns": context.unknowns[:10],
            "assembly_duration_ms": context.metadata.get("duration_ms", 0),
        }

    @staticmethod
    def extract_evidence_for_context_window(
        context: RepositoryContext,
        focus_types: Optional[List[str]] = None,
        max_items: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Extract high-priority evidence items for LLM context window.

        Args:
            context: RepositoryContext object
            focus_types: Filter to specific source types (e.g., ['rim_symbol', 'retrieval'])
            max_items: Maximum items to return

        Returns:
            List of evidence items (dicts with source_type, summary, data)
        """
        filtered_evidence = context.evidence

        if focus_types:
            filtered_evidence = [
                e for e in context.evidence
                if e.source_type in focus_types
            ]

        # Sort by relevance and confidence
        sorted_evidence = sorted(
            filtered_evidence,
            key=lambda e: (e.relevance * e.confidence),
            reverse=True
        )

        return [
            {
                "source_type": e.source_type,
                "source_id": e.source_id,
                "summary": e.summary,
                "relevance": e.relevance,
                "confidence": e.confidence,
            }
            for e in sorted_evidence[:max_items]
        ]
