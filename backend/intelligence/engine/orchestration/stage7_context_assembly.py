"""
Stage 7: Context Assembly

Wraps existing ContextAssembler, consuming Stage 5 retrieval and Stage 6 graph results.
Preserves provenance from retrieval and graph traversal.
"""
import logging
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from sqlalchemy.orm import Session

from backend.agent.context.assembler import ContextAssembler
from backend.agent.context.contracts import (
    ContextAssemblyRequest,
    RepositoryContext,
    ContextEvidence,
    ContextBudget,
)
from backend.intelligence.retrieval.schema import RetrieverResult
from backend.intelligence.engine.orchestration.stage6_graph_navigation import GraphNavigationResult

logger = logging.getLogger(__name__)


@dataclass
class ContextAssemblyMetrics:
    """Metrics from Stage 7 assembly."""
    query: str
    retrieval_anchors: int
    graph_entities: int
    graph_edges: int
    selected_files: List[str]
    selected_symbols: List[str]
    context_size_kb: float
    evidence_count: int
    configured_budgets: Dict[str, int]
    assembly_time: float
    validation_passed: bool
    validation_errors: List[str]


class ContextAssemblyValidator:
    """Validate Stage 7 context output."""

    @staticmethod
    def validate(
        context: RepositoryContext,
        graph_result: GraphNavigationResult,
        query: str,
    ) -> tuple[bool, List[str]]:
        """
        Validate that assembled context is repository-derived and budgeted.

        Returns:
            (passed: bool, errors: List[str])
        """
        errors: List[str] = []

        # Validate context structure
        if not context:
            errors.append("Context is None")
            return False, errors

        if not context.requirement:
            errors.append("Context requirement is empty")

        if not context.relevant_files:
            errors.append("No relevant files selected")

        if not context.evidence:
            errors.append("No evidence items selected")

        # Validate that selected files actually exist (sanity check)
        # Note: Would need RepositoryModel to fully validate; skip for now
        if context.relevant_files and not all(isinstance(f, str) for f in context.relevant_files):
            errors.append("Selected files contain non-string values")

        # Validate budget constraints
        if len(context.relevant_files) > 50:
            errors.append(f"Too many files selected: {len(context.relevant_files)} > 50")

        if len(context.relevant_symbols) > 100:
            errors.append(f"Too many symbols selected: {len(context.relevant_symbols)} > 100")

        if len(context.evidence) > 200:
            errors.append(f"Too many evidence items: {len(context.evidence)} > 200")

        # Validate evidence provenance
        for evidence in context.evidence:
            if not evidence.source_type:
                errors.append("Evidence missing source_type")
            if not evidence.source_id:
                errors.append("Evidence missing source_id")
            if not evidence.summary:
                errors.append("Evidence missing summary")

        # Validate that evidence is bounded
        try:
            evidence_json = json.dumps([e.model_dump() for e in context.evidence])
            context_size_kb = len(evidence_json) / 1024
            if context_size_kb > 512:
                errors.append(f"Context too large: {context_size_kb:.1f}KB > 512KB")
        except Exception as e:
            errors.append(f"Failed to measure context size: {e}")

        passed = len(errors) == 0
        return passed, errors


class ContextAssembler7:
    """Stage 7: Assemble bounded repository context from retrieval + graph results."""

    def __init__(self, db: Optional[Session] = None):
        self.assembler = ContextAssembler()
        self.db = db
        self.validator = ContextAssemblyValidator()

    def _read_file_content(self, file_path: str, max_lines: int = 100) -> Optional[str]:
        """Read actual file content from disk."""
        try:
            from pathlib import Path
            fp = Path(file_path)
            if not fp.exists():
                return None

            content = fp.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')[:max_lines]
            return '\n'.join(lines)
        except Exception as e:
            logger.warning(f"Could not read file {file_path}: {e}")
            return None

    def assemble(
        self,
        query: str,
        retrieval_results: List[RetrieverResult],
        graph_result: GraphNavigationResult,
        repository_id: str,
        analysis_id: Optional[int] = None,
        context_budget: Optional[ContextBudget] = None,
    ) -> tuple[RepositoryContext, ContextAssemblyMetrics]:
        """
        Assemble repository context from retrieval + graph results.

        Args:
            query: Original user query
            retrieval_results: Stage 5 retrieval anchors
            graph_result: Stage 6 graph traversal results
            repository_id: Repository identifier
            analysis_id: Analysis ID (optional)
            context_budget: Context budget constraints (optional)

        Returns:
            (context: RepositoryContext, metrics: ContextAssemblyMetrics)
        """
        import time
        start_time = time.time()

        # Default budget if not provided
        if not context_budget:
            context_budget = ContextBudget(
                max_files=15,
                max_symbols=30,
                max_routes=10,
                max_db_objects=10,
                max_dependencies=15,
                max_call_paths=10,
                max_source_excerpts=10,
                max_total_evidence_size_kb=256,
            )

        # Build ContextAssemblyRequest
        task_context = {
            "retrieval_anchors": len(retrieval_results),
            "graph_entities": graph_result.entity_count,
            "graph_edges": graph_result.edge_count,
            "graph_depth": graph_result.traversal_depth,
            "search_strategy": "hybrid_retrieval_plus_graph",
        }

        request = ContextAssemblyRequest(
            repository_id=repository_id,
            requirement=query,
            context_budget=context_budget,
            analysis_id=analysis_id,
            task_context=task_context,
        )

        # Call existing ContextAssembler
        try:
            context = self.assembler.assemble(request, db=self.db)
        except Exception as e:
            logger.error(f"[Stage 7] ContextAssembler failed: {e}")
            raise

        # CRITICAL FIX: Integrate graph results into context
        # The underlying ContextAssembler only knows about keywords, not graph entities.
        # Stage 6 discovered entities with precise relationships - we must use them!
        graph_files_added = 0
        graph_symbols_added = 0

        if graph_result.discovered_entities:
            logger.debug(f"[Stage 7] Integrating {len(graph_result.discovered_entities)} entities from Stage 6...")

            # Track which files/symbols we already have to avoid duplicates
            existing_files = set(context.relevant_files or [])
            existing_symbols = {s.get("name", "") for s in (context.relevant_symbols or [])}

            for entity_id, entity in graph_result.discovered_entities.items():
                try:
                    # Extract file path from entity location
                    file_path = entity.location.repository_path if entity.location else None

                    if not file_path:
                        continue

                    # Add file if not already present
                    if file_path not in existing_files:
                        if not context.relevant_files:
                            context.relevant_files = []
                        context.relevant_files.append(file_path)
                        existing_files.add(file_path)
                        graph_files_added += 1
                        logger.debug(f"  Added file from graph: {file_path}")

                    # For symbol-like entities, also add to symbols list
                    if entity.type.value in ("FUNCTION", "METHOD", "CLASS", "INTERFACE", "ENUM", "VARIABLE", "CONSTANT"):
                        symbol_name = entity.name
                        if symbol_name not in existing_symbols:
                            if not context.relevant_symbols:
                                context.relevant_symbols = []
                            context.relevant_symbols.append({
                                "name": symbol_name,
                                "file_path": file_path,
                                "kind": entity.type.value,
                                "symbol_type": entity.type.value,
                                "line_start": entity.location.start_line if entity.location else 1,
                            })
                            existing_symbols.add(symbol_name)
                            graph_symbols_added += 1
                            logger.debug(f"  Added symbol from graph: {symbol_name} ({entity.type.value})")

                except Exception as e:
                    logger.warning(f"[Stage 7] Error processing graph entity {entity_id}: {e}")
                    continue

            if graph_files_added > 0 or graph_symbols_added > 0:
                logger.debug(f"[Stage 7] ✓ Integrated from graph results:")
                logger.debug(f"    Files added: {graph_files_added}")
                logger.debug(f"    Symbols added: {graph_symbols_added}")
                logger.debug(f"    Total files now: {len(context.relevant_files or [])}")
                logger.debug(f"    Total symbols now: {len(context.relevant_symbols or [])}")
            else:
                logger.debug(f"[Stage 7] No new files/symbols from graph entities")

        # Validate assembled context
        validated, errors = self.validator.validate(context, graph_result, query)

        # ENHANCEMENT: Add actual file content to context
        # This ensures LLM gets real code, not just metadata
        # Read files including those added from graph results
        if context.relevant_files:
            logger.debug(f"[Stage 7] Reading actual file content for {len(context.relevant_files)} files (including {graph_files_added} from graph)...")
            file_contents = {}
            total_content_size = 0
            max_content_size = 200_000  # 200KB total for file contents

            for file_path in context.relevant_files:  # Read all selected files
                if total_content_size > max_content_size:
                    logger.debug(f"[Stage 7] Reached max content size ({max_content_size} bytes), stopping file reads")
                    break

                logger.debug(f"  Attempting to read: {file_path}")
                content = self._read_file_content(file_path, max_lines=200)
                if content:
                    file_contents[file_path] = content
                    total_content_size += len(content)
                    logger.debug(f"  ✓ {file_path} - {len(content)} chars, {len(content.split(chr(10)))} lines (total: {total_content_size})")
                else:
                    logger.warning(f"  ✗ {file_path} - Failed to read or file empty")

            # Add file contents to context evidence
            logger.debug(f"[Stage 7] Successfully read {len(file_contents)} files, adding to evidence...")
            if file_contents:
                for file_path, content in file_contents.items():
                    # LOG EXACT CONTENT BEING ADDED
                    content_lines = content.split('\n')
                    logger.debug(f"\n[Stage 7] ADDING FILE CONTENT TO CONTEXT:")
                    logger.debug(f"  File: {file_path}")
                    logger.debug(f"  Total chars: {len(content)}")
                    logger.debug(f"  Total lines: {len(content_lines)}")
                    logger.debug(f"  First 500 chars:\n{content[:500]}")
                    logger.debug(f"  Last 200 chars:\n{content[-200:]}")

                    # Create evidence item with actual code in 'data' field
                    code_evidence = ContextEvidence(
                        source_type="source_excerpt",
                        source_id=file_path,
                        summary=f"Source code excerpt from {file_path}",
                        data={
                            "file_path": file_path,
                            "content": content,
                            "lines": len(content_lines),
                            "chars": len(content),
                        },
                        metadata={
                            "excerpt_type": "full_file",
                            "truncated": False,
                        },
                        confidence=1.0,
                        relevance=1.0,
                    )
                    if not context.evidence:
                        context.evidence = []
                    context.evidence.append(code_evidence)

                    # VERIFY IT WAS ADDED
                    added_evidence = context.evidence[-1]
                    logger.debug(f"  ✓ VERIFIED in context.evidence[{len(context.evidence)-1}]:")
                    logger.debug(f"    - source_type: {added_evidence.source_type}")
                    logger.debug(f"    - source_id: {added_evidence.source_id}")
                    logger.debug(f"    - data['content'] length: {len(added_evidence.data.get('content', ''))}")
                    logger.debug(f"    - data['content'] first 200 chars: {added_evidence.data.get('content', '')[:200]}")

                logger.debug(f"\n[Stage 7] ✓ COMPLETE: Added {len(file_contents)} files to evidence (total items: {len(context.evidence)})")
            else:
                logger.warning(f"[Stage 7] ✗ No files were successfully read!")

        # Collect metrics
        selected_files = context.relevant_files or []
        selected_symbols = [s.get("name", "") for s in context.relevant_symbols] if context.relevant_symbols else []

        try:
            context_json = json.dumps(context.model_dump())
            context_size_kb = len(context_json) / 1024
        except Exception:
            context_size_kb = 0.0

        metrics = ContextAssemblyMetrics(
            query=query,
            retrieval_anchors=len(retrieval_results),
            graph_entities=graph_result.entity_count,
            graph_edges=graph_result.edge_count,
            selected_files=selected_files,
            selected_symbols=selected_symbols,
            context_size_kb=context_size_kb,
            evidence_count=len(context.evidence) if context.evidence else 0,
            configured_budgets={
                "max_files": context_budget.max_files,
                "max_symbols": context_budget.max_symbols,
                "max_routes": context_budget.max_routes,
            },
            assembly_time=time.time() - start_time,
            validation_passed=validated,
            validation_errors=errors,
        )

        if not validated:
            logger.warning(f"[Stage 7] Context validation failed: {errors}")

        return context, metrics
