"""
Phase 2M.1: Phase 2L Tool Adapter for Stage 8

Wraps Phase 2L inspection tools with execution context injection, error handling,
and research event tracking.

Purpose:
- Thread execution context (analysis_id, repo_root, db) through Phase 2L tools
- Provide LLM-consumable tool result formatting
- Track research events for observability
- Integrate ContextManager for dynamic context tracking
"""
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum
from sqlalchemy.orm import Session

from backend.intelligence.inspection.file_inspector import inspect_file
from backend.intelligence.inspection.source_reader import read_symbol, read_file, read_lines
from backend.intelligence.context_management.manager import ContextManager
from backend.agent.context.contracts import ContextEvidence, ContextBudget

logger = logging.getLogger(__name__)


class ResearchEventType(str, Enum):
    """Types of observable research events for frontend visibility."""
    RESEARCH_STARTED = "research_started"
    TOOL_INVOKED = "tool_invoked"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    CONTEXT_UPDATED = "context_updated"
    CONTEXT_DROPPED = "context_dropped"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    GROUNDING_VALIDATED = "grounding_validated"
    RESEARCH_COMPLETED = "research_completed"


@dataclass
class ResearchEvent:
    """Observable research event for frontend tracking."""
    event_type: ResearchEventType
    timestamp: datetime
    stage: str  # "inspection", "reading", "context", "llm", "grounding"
    description: str
    details: Dict[str, Any]  # Tool-specific data: file_path, symbols, tokens, etc.

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON transport."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "stage": self.stage,
            "description": self.description,
            "details": self.details,
        }


@dataclass
class ExecutionContext:
    """Repository execution context for Phase 2L tool access."""
    analysis_id: int
    repo_root: str
    db: Session
    user_id: Optional[int] = None
    repo_name: str = "default"


class Phase2LToolWrapper:
    """
    Wraps Phase 2L inspection tools with execution context and observability.

    Responsibilities:
    1. Inject execution context into tool calls
    2. Format tool results for LLM consumption
    3. Add results to ContextManager
    4. Track research events
    5. Handle tool errors gracefully
    """

    def __init__(
        self,
        execution_context: ExecutionContext,
        context_manager: ContextManager,
    ):
        self.exec_ctx = execution_context
        self.context_manager = context_manager
        self.events: List[ResearchEvent] = []

    def _emit_event(
        self,
        event_type: ResearchEventType,
        stage: str,
        description: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> ResearchEvent:
        """Record observable research event."""
        event = ResearchEvent(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            stage=stage,
            description=description,
            details=details or {},
        )
        self.events.append(event)
        logger.debug(f"[Research Event] {event_type.value}: {description}")
        return event

    def inspect_file_tool(self, file_path: str) -> Dict[str, Any]:
        """
        Inspect file structure and symbols (no source).

        LLM-consumable tool result.
        Adds discovery to ContextManager.
        """
        start_time = time.time()

        try:
            result = inspect_file(
                file_path=file_path,
                db=self.exec_ctx.db,
                repo_root=self.exec_ctx.repo_root,
                repo_name=self.exec_ctx.repo_name,
                analysis_id=self.exec_ctx.analysis_id,
                user_id=self.exec_ctx.user_id,
            )

            elapsed = time.time() - start_time

            if not result.success:
                self._emit_event(
                    ResearchEventType.TOOL_ERROR,
                    "inspection",
                    f"inspect_file({file_path}) failed: {result.error}",
                    {"file_path": file_path, "error": result.error},
                )
                return {
                    "file": file_path,
                    "success": False,
                    "error": result.error,
                    "tool": "inspect_file",
                }

            # Format for LLM
            symbols_list = [
                {
                    "name": s.name,
                    "type": s.symbol_type,
                    "line_start": s.line_start,
                    "line_end": s.line_end,
                }
                for s in result.symbols
            ]

            formatted_result = {
                "file": file_path,
                "success": True,
                "tool": "inspect_file",
                "language": result.language,
                "total_lines": result.total_lines,
                "file_size_kb": result.file_size_kb,
                "symbols": symbols_list,
                "symbol_count": len(result.symbols),
            }

            # Add to context manager
            try:
                evidence = ContextEvidence(
                    source_type="repository_structure",
                    source_id=file_path,
                    summary=f"File structure: {len(result.symbols)} symbols in {result.language}",
                    data={
                        "file_path": file_path,
                        "symbols": symbols_list,
                        "language": result.language,
                        "total_lines": result.total_lines,
                    },
                    confidence=1.0,
                    relevance=1.0,
                )
                ctx_item = self.context_manager.add_item(
                    evidence,
                    retrieval_source="llm_inspect_file",
                )

                self._emit_event(
                    ResearchEventType.CONTEXT_UPDATED,
                    "inspection",
                    f"Added file structure for {file_path} to context",
                    {
                        "file_path": file_path,
                        "context_item_id": ctx_item.context_item_id,
                        "symbols": len(result.symbols),
                        "elapsed_ms": int(elapsed * 1000),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to add inspect_file result to context: {e}")

            self._emit_event(
                ResearchEventType.TOOL_RESULT,
                "inspection",
                f"Inspected {file_path}: {len(result.symbols)} symbols",
                {
                    "file_path": file_path,
                    "symbols": len(result.symbols),
                    "language": result.language,
                    "elapsed_ms": int(elapsed * 1000),
                },
            )

            return formatted_result

        except Exception as e:
            logger.error(f"Exception in inspect_file_tool({file_path}): {e}")
            self._emit_event(
                ResearchEventType.TOOL_ERROR,
                "inspection",
                f"inspect_file({file_path}) exception: {str(e)}",
                {"file_path": file_path, "exception": str(e)},
            )
            return {
                "file": file_path,
                "success": False,
                "error": f"Exception: {str(e)}",
                "tool": "inspect_file",
            }

    def read_symbol_tool(self, file_path: str, symbol_name: str) -> Dict[str, Any]:
        """
        Read exact source of one symbol.

        LLM-consumable tool result.
        Adds source to ContextManager.
        """
        start_time = time.time()

        try:
            result = read_symbol(
                file_path=file_path,
                symbol_name=symbol_name,
                db=self.exec_ctx.db,
                repo_root=self.exec_ctx.repo_root,
                repo_name=self.exec_ctx.repo_name,
                analysis_id=self.exec_ctx.analysis_id,
                user_id=self.exec_ctx.user_id,
            )

            elapsed = time.time() - start_time

            if not result.success:
                self._emit_event(
                    ResearchEventType.TOOL_ERROR,
                    "reading",
                    f"read_symbol({file_path}:{symbol_name}) failed: {result.error}",
                    {"file_path": file_path, "symbol": symbol_name, "error": result.error},
                )
                return {
                    "file": file_path,
                    "symbol": symbol_name,
                    "success": False,
                    "error": result.error,
                    "tool": "read_symbol",
                }

            formatted_result = {
                "file": file_path,
                "symbol": symbol_name,
                "success": True,
                "tool": "read_symbol",
                "source": result.source,
                "line_start": result.line_start,
                "line_end": result.line_end,
                "total_lines": result.total_lines,
                "language": result.language,
                "estimated_tokens": result.estimated_tokens,
            }

            # Add to context manager
            try:
                evidence = ContextEvidence(
                    source_type="source_excerpt",
                    source_id=f"{file_path}:{symbol_name}",
                    summary=f"Source: {symbol_name} ({result.line_end - result.line_start + 1} lines)",
                    data={
                        "file_path": file_path,
                        "symbol_name": symbol_name,
                        "content": result.source,
                        "line_start": result.line_start,
                        "line_end": result.line_end,
                    },
                    confidence=1.0,
                    relevance=1.0,
                )
                ctx_item = self.context_manager.add_item(
                    evidence,
                    retrieval_source="llm_read_symbol",
                )

                utilization = self.context_manager.calculate_utilization()

                self._emit_event(
                    ResearchEventType.CONTEXT_UPDATED,
                    "reading",
                    f"Added source for {symbol_name} to context (utilization: {utilization:.1%})",
                    {
                        "file_path": file_path,
                        "symbol": symbol_name,
                        "context_item_id": ctx_item.context_item_id,
                        "tokens": result.estimated_tokens,
                        "utilization": utilization,
                        "elapsed_ms": int(elapsed * 1000),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to add read_symbol result to context: {e}")

            self._emit_event(
                ResearchEventType.TOOL_RESULT,
                "reading",
                f"Read {symbol_name} from {file_path}: {result.line_end - result.line_start + 1} lines",
                {
                    "file_path": file_path,
                    "symbol": symbol_name,
                    "lines": result.line_end - result.line_start + 1,
                    "tokens": result.estimated_tokens,
                    "elapsed_ms": int(elapsed * 1000),
                },
            )

            return formatted_result

        except Exception as e:
            logger.error(f"Exception in read_symbol_tool({file_path}:{symbol_name}): {e}")
            self._emit_event(
                ResearchEventType.TOOL_ERROR,
                "reading",
                f"read_symbol({file_path}:{symbol_name}) exception: {str(e)}",
                {"file_path": file_path, "symbol": symbol_name, "exception": str(e)},
            )
            return {
                "file": file_path,
                "symbol": symbol_name,
                "success": False,
                "error": f"Exception: {str(e)}",
                "tool": "read_symbol",
            }

    def read_file_tool(self, file_path: str) -> Dict[str, Any]:
        """
        Read entire file (expensive operation).

        LLM-consumable tool result.
        Adds source to ContextManager.
        """
        start_time = time.time()

        try:
            result = read_file(
                file_path=file_path,
                db=self.exec_ctx.db,
                repo_root=self.exec_ctx.repo_root,
                repo_name=self.exec_ctx.repo_name,
                user_id=self.exec_ctx.user_id,
            )

            elapsed = time.time() - start_time

            if not result.success:
                self._emit_event(
                    ResearchEventType.TOOL_ERROR,
                    "reading",
                    f"read_file({file_path}) failed: {result.error}",
                    {"file_path": file_path, "error": result.error},
                )
                return {
                    "file": file_path,
                    "success": False,
                    "error": result.error or result.warning,
                    "tool": "read_file",
                }

            formatted_result = {
                "file": file_path,
                "success": True,
                "tool": "read_file",
                "source": result.source,
                "total_lines": result.total_lines,
                "file_size_kb": result.file_size_kb,
                "language": result.language,
                "estimated_tokens": result.estimated_tokens,
            }

            # Add to context manager
            try:
                evidence = ContextEvidence(
                    source_type="source_excerpt",
                    source_id=file_path,
                    summary=f"Full file: {result.total_lines} lines",
                    data={
                        "file_path": file_path,
                        "content": result.source,
                        "total_lines": result.total_lines,
                    },
                    confidence=1.0,
                    relevance=1.0,
                )
                ctx_item = self.context_manager.add_item(
                    evidence,
                    retrieval_source="llm_read_file",
                )

                utilization = self.context_manager.calculate_utilization()

                self._emit_event(
                    ResearchEventType.CONTEXT_UPDATED,
                    "reading",
                    f"Added full file {file_path} to context (utilization: {utilization:.1%})",
                    {
                        "file_path": file_path,
                        "context_item_id": ctx_item.context_item_id,
                        "lines": result.total_lines,
                        "tokens": result.estimated_tokens,
                        "utilization": utilization,
                        "elapsed_ms": int(elapsed * 1000),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to add read_file result to context: {e}")

            self._emit_event(
                ResearchEventType.TOOL_RESULT,
                "reading",
                f"Read full file {file_path}: {result.total_lines} lines",
                {
                    "file_path": file_path,
                    "lines": result.total_lines,
                    "tokens": result.estimated_tokens,
                    "file_size_kb": result.file_size_kb,
                    "elapsed_ms": int(elapsed * 1000),
                },
            )

            return formatted_result

        except Exception as e:
            logger.error(f"Exception in read_file_tool({file_path}): {e}")
            self._emit_event(
                ResearchEventType.TOOL_ERROR,
                "reading",
                f"read_file({file_path}) exception: {str(e)}",
                {"file_path": file_path, "exception": str(e)},
            )
            return {
                "file": file_path,
                "success": False,
                "error": f"Exception: {str(e)}",
                "tool": "read_file",
            }

    def read_lines_tool(self, file_path: str, start_line: int, end_line: int) -> Dict[str, Any]:
        """
        Read explicit line range from file (validated).

        LLM-consumable tool result.
        Adds partial source to ContextManager.
        """
        start_time = time.time()

        try:
            result = read_lines(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                db=self.exec_ctx.db,
                repo_root=self.exec_ctx.repo_root,
                repo_name=self.exec_ctx.repo_name,
                user_id=self.exec_ctx.user_id,
            )

            elapsed = time.time() - start_time

            if not result.success:
                self._emit_event(
                    ResearchEventType.TOOL_ERROR,
                    "reading",
                    f"read_lines({file_path}:{start_line}-{end_line}) failed: {result.error}",
                    {
                        "file_path": file_path,
                        "line_start": start_line,
                        "line_end": end_line,
                        "error": result.error,
                    },
                )
                return {
                    "file": file_path,
                    "line_start": start_line,
                    "line_end": end_line,
                    "success": False,
                    "error": result.error,
                    "tool": "read_lines",
                }

            formatted_result = {
                "file": file_path,
                "line_start": result.line_start,
                "line_end": result.line_end,
                "success": True,
                "tool": "read_lines",
                "source": result.source,
                "total_lines": result.total_lines,
                "language": result.language,
                "estimated_tokens": result.estimated_tokens,
            }

            # Add to context manager
            try:
                evidence = ContextEvidence(
                    source_type="source_excerpt",
                    source_id=f"{file_path}:{start_line}-{end_line}",
                    summary=f"Lines {start_line}-{end_line}",
                    data={
                        "file_path": file_path,
                        "content": result.source,
                        "line_start": result.line_start,
                        "line_end": result.line_end,
                    },
                    confidence=1.0,
                    relevance=1.0,
                )
                ctx_item = self.context_manager.add_item(
                    evidence,
                    retrieval_source="llm_read_lines",
                )

                utilization = self.context_manager.calculate_utilization()

                self._emit_event(
                    ResearchEventType.CONTEXT_UPDATED,
                    "reading",
                    f"Added lines {start_line}-{end_line} from {file_path} to context",
                    {
                        "file_path": file_path,
                        "line_start": start_line,
                        "line_end": end_line,
                        "context_item_id": ctx_item.context_item_id,
                        "tokens": result.estimated_tokens,
                        "utilization": utilization,
                        "elapsed_ms": int(elapsed * 1000),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to add read_lines result to context: {e}")

            self._emit_event(
                ResearchEventType.TOOL_RESULT,
                "reading",
                f"Read lines {start_line}-{end_line} from {file_path}",
                {
                    "file_path": file_path,
                    "line_start": start_line,
                    "line_end": end_line,
                    "lines": end_line - start_line + 1,
                    "tokens": result.estimated_tokens,
                    "elapsed_ms": int(elapsed * 1000),
                },
            )

            return formatted_result

        except Exception as e:
            logger.error(f"Exception in read_lines_tool({file_path}:{start_line}-{end_line}): {e}")
            self._emit_event(
                ResearchEventType.TOOL_ERROR,
                "reading",
                f"read_lines({file_path}:{start_line}-{end_line}) exception: {str(e)}",
                {
                    "file_path": file_path,
                    "line_start": start_line,
                    "line_end": end_line,
                    "exception": str(e),
                },
            )
            return {
                "file": file_path,
                "line_start": start_line,
                "line_end": end_line,
                "success": False,
                "error": f"Exception: {str(e)}",
                "tool": "read_lines",
            }

    def get_context_status_tool(self) -> Dict[str, Any]:
        """
        Get current context utilization and status.

        For LLM to monitor context pressure.
        """
        try:
            utilization = self.context_manager.calculate_utilization()
            checkpoint = self.context_manager.get_budget_checkpoint()
            items = self.context_manager.list_context()

            status = {
                "utilization": utilization,
                "utilization_percent": f"{utilization * 100:.1f}%",
                "budget_status": checkpoint.status,
                "total_items": len(items),
                "active_items": len([i for i in items if i.state.value == "ACTIVE"]),
                "total_tokens": checkpoint.current_tokens,
                "max_tokens": checkpoint.max_tokens,
                "success": True,
                "tool": "get_context_status",
            }

            self._emit_event(
                ResearchEventType.TOOL_RESULT,
                "context",
                f"Context status: {utilization:.1%} utilization, {checkpoint.status} budget",
                {
                    "utilization": utilization,
                    "budget_status": checkpoint.status,
                    "total_items": len(items),
                    "active_items": len([i for i in items if i.state.value == "ACTIVE"]),
                },
            )

            return status

        except Exception as e:
            logger.error(f"Exception in get_context_status_tool(): {e}")
            return {
                "success": False,
                "error": str(e),
                "tool": "get_context_status",
            }

    def list_context_tool(self) -> Dict[str, Any]:
        """
        List all context items currently in use.

        For LLM transparency into what evidence is available.
        """
        try:
            items = self.context_manager.list_context()

            formatted_items = []
            for item in items:
                formatted_items.append({
                    "context_item_id": item.context_item_id,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "priority": item.priority.value,
                    "state": item.state.value,
                    "estimated_tokens": item.estimated_tokens,
                })

            return {
                "success": True,
                "tool": "list_context",
                "items": formatted_items,
                "total_items": len(items),
                "total_tokens": sum(i.estimated_tokens for i in items),
            }

        except Exception as e:
            logger.error(f"Exception in list_context_tool(): {e}")
            return {
                "success": False,
                "error": str(e),
                "tool": "list_context",
            }
