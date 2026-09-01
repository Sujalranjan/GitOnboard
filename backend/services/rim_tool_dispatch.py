"""
Tool Dispatch Table: wraps RepositoryToolLayer and query_rim tool.

Routes tool calls from the LLM to the appropriate backend, catches all exceptions.
Exposes different tool sets for baseline (no RIM) vs. RIM side (with query_rim).
"""

import logging
from typing import Any, Dict, List, Optional

from backend.agent.loop.contracts import ToolObservation
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser, TraversedEntity
from backend.repository_tools.tools import RepositoryToolLayer
from backend.agent.intent.semantic_query import SemanticQueryClass, TraversalDirection, SemanticQueryIntent

logger = logging.getLogger(__name__)


class ToolSpec:
    """Tool specification for system prompt."""
    def __init__(self, name: str, description: str, parameters: Dict[str, Any]):
        self.name = name
        self.description = description
        self.parameters = parameters


class TargetEntityResolver:
    """
    Resolves entity names to ORM objects (FactFile/FactSymbol/FactRoute/FactDatabaseObject).
    """
    def __init__(self, db, analysis_id: int):
        self.db = db
        self.analysis_id = analysis_id

    def resolve(self, entity_name: str) -> Optional[Any]:
        """
        Resolve entity name to ORM object.
        Tries: FactSymbol by name, FactFile by path, FactRoute by path, then FactDatabaseObject.
        """
        from backend.models.fact_store import FactSymbol, FactFile, FactRoute, FactDatabaseObject

        # Try FactSymbol (functions, classes, methods)
        symbol = self.db.query(FactSymbol).filter(
            FactSymbol.analysis_id == self.analysis_id,
            FactSymbol.name.ilike(entity_name),
        ).first()
        if symbol:
            return symbol

        # Try FactFile (by path)
        file = self.db.query(FactFile).filter(
            FactFile.analysis_id == self.analysis_id,
            FactFile.path.ilike(f"%{entity_name}%"),
        ).first()
        if file:
            return file

        # Try FactRoute (by path)
        route = self.db.query(FactRoute).filter(
            FactRoute.analysis_id == self.analysis_id,
            FactRoute.path.ilike(f"%{entity_name}%"),
        ).first()
        if route:
            return route

        # Try FactDatabaseObject (by name)
        db_obj = self.db.query(FactDatabaseObject).filter(
            FactDatabaseObject.analysis_id == self.analysis_id,
            FactDatabaseObject.name.ilike(entity_name),
        ).first()
        if db_obj:
            return db_obj

        return None


class ToolDispatchTable:
    """
    Routes tool calls to underlying implementations.
    Exposes different tools for baseline vs. RIM side.
    """

    def __init__(
        self,
        tool_layer: RepositoryToolLayer,
        graph_traverser: Optional[FactStoreGraphTraverser] = None,
        target_resolver: Optional[TargetEntityResolver] = None,
    ):
        self.tool_layer = tool_layer
        self.graph_traverser = graph_traverser
        self.target_resolver = target_resolver

    def specs(self, include_rim: bool) -> List[ToolSpec]:
        """
        Return tool specs for system prompt.

        Args:
            include_rim: if True, include query_rim tool (RIM side only)

        Returns:
            List of ToolSpec objects for the prompt builder
        """
        base_tools = [
            ToolSpec(
                "read_file",
                "Read a portion of a source file. Returns line-numbered content.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to repo root"},
                        "start_line": {"type": "integer", "description": "Starting line number (default 1)"},
                        "end_line": {"type": "integer", "description": "Ending line number (default: entire file up to 1000 lines)"},
                    },
                    "required": ["path"],
                },
            ),
            ToolSpec(
                "find_files",
                "Find files matching a glob pattern. Returns list of matching files.",
                {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.tsx', 'src/**/*.py')"},
                        "limit": {"type": "integer", "description": "Max results (default 50)"},
                    },
                },
            ),
            ToolSpec(
                "get_symbol",
                "Look up symbol definitions (functions, classes, methods) by name.",
                {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Symbol name (substring match)"},
                    },
                    "required": ["name"],
                },
            ),
            ToolSpec(
                "get_file_outline",
                "Get an outline of symbols (functions, classes) in a file.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            ),
            ToolSpec(
                "search_repository",
                "Hybrid search: find symbols, files, and code snippets matching a query.",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Max results (default 10)"},
                    },
                    "required": ["query"],
                },
            ),
            ToolSpec(
                "get_callers",
                "Find symbols that call a given function/method.",
                {
                    "type": "object",
                    "properties": {
                        "symbol_name": {"type": "string", "description": "Function or method name"},
                    },
                    "required": ["symbol_name"],
                },
            ),
            ToolSpec(
                "get_callees",
                "Find functions/methods called by a given function/method.",
                {
                    "type": "object",
                    "properties": {
                        "symbol_name": {"type": "string", "description": "Function or method name"},
                    },
                    "required": ["symbol_name"],
                },
            ),
            ToolSpec(
                "search_code",
                "Search for text/regex in source code. Limited to first N files to avoid overwhelming results.",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Text or regex pattern to search for"},
                        "file_pattern": {"type": "string", "description": "Optional glob pattern to limit search scope"},
                        "max_matches": {"type": "integer", "description": "Max results (default 25)"},
                    },
                    "required": ["query"],
                },
            ),
        ]

        if include_rim and self.graph_traverser and self.target_resolver:
            base_tools.append(
                ToolSpec(
                    "query_rim",
                    "Query the Repository Intelligence Model for structural facts (who calls/imports/inherits what). Returns metadata only, never source code.",
                    {
                        "type": "object",
                        "properties": {
                            "entity_name": {"type": "string", "description": "Symbol, file, or route name to look up"},
                            "relationship_type": {
                                "type": "string",
                                "enum": ["CALLS", "IMPORTS", "INHERITS", "CONTAINS", "ROUTE_HANDLER", "DATABASE_ACCESS", "GENERIC"],
                                "description": "Type of relationship to explore",
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["FORWARD", "REVERSE"],
                                "default": "FORWARD",
                                "description": "FORWARD: what does entity do? REVERSE: who uses/calls entity?",
                            },
                        },
                        "required": ["entity_name", "relationship_type"],
                    },
                )
            )

        return base_tools

    def dispatch(self, tool_name: str, arguments: Dict[str, Any]) -> ToolObservation:
        """
        Dispatch tool call to underlying implementation.

        Catches all exceptions and returns ToolObservation(success=False, error=...).
        Never raises into the loop.
        """
        tool_call_id = f"{tool_name}:{hash(str(arguments))}"

        try:
            if tool_name == "read_file":
                return self._handle_read_file(arguments, tool_call_id)
            elif tool_name == "find_files":
                return self._handle_find_files(arguments, tool_call_id)
            elif tool_name == "get_symbol":
                return self._handle_get_symbol(arguments, tool_call_id)
            elif tool_name == "get_file_outline":
                return self._handle_get_file_outline(arguments, tool_call_id)
            elif tool_name == "search_repository":
                return self._handle_search_repository(arguments, tool_call_id)
            elif tool_name == "get_callers":
                return self._handle_get_callers(arguments, tool_call_id)
            elif tool_name == "get_callees":
                return self._handle_get_callees(arguments, tool_call_id)
            elif tool_name == "search_code":
                return self._handle_search_code(arguments, tool_call_id)
            elif tool_name == "query_rim":
                return self._handle_query_rim(arguments, tool_call_id)
            else:
                return ToolObservation(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    success=False,
                    error={"type": "unknown_tool", "message": f"Unknown tool: {tool_name}"},
                )
        except Exception as e:
            logger.error(f"Tool dispatch error for {tool_name}: {e}", exc_info=True)
            return ToolObservation(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                success=False,
                error={"type": "dispatch_error", "message": str(e)},
            )

    def _handle_read_file(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle read_file tool call."""
        path = arguments.get("path", "")
        start_line = arguments.get("start_line", 1)
        end_line = arguments.get("end_line", None)

        if not path:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="read_file", success=False,
                error={"type": "invalid_args", "message": "path is required"},
            )

        try:
            result = self.tool_layer.read_file(path, start_line, end_line)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="read_file", success=True, data=result,
            )
        except Exception as e:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="read_file", success=False,
                error={"type": "read_error", "message": str(e)},
            )

    def _handle_find_files(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle find_files tool call."""
        pattern = arguments.get("pattern", "*")
        limit = arguments.get("limit", 50)

        try:
            result = self.tool_layer.find_files(pattern, limit)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="find_files", success=True, data=result,
            )
        except Exception as e:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="find_files", success=False,
                error={"type": "search_error", "message": str(e)},
            )

    def _handle_get_symbol(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle get_symbol tool call."""
        name = arguments.get("name", "")

        if not name:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_symbol", success=False,
                error={"type": "invalid_args", "message": "name is required"},
            )

        try:
            result = self.tool_layer.get_symbol(name)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_symbol", success=True, data=result,
            )
        except Exception as e:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_symbol", success=False,
                error={"type": "search_error", "message": str(e)},
            )

    def _handle_get_file_outline(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle get_file_outline tool call."""
        path = arguments.get("path", "")

        if not path:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_file_outline", success=False,
                error={"type": "invalid_args", "message": "path is required"},
            )

        try:
            result = self.tool_layer.get_file_outline(path)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_file_outline", success=True, data=result,
            )
        except Exception as e:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_file_outline", success=False,
                error={"type": "outline_error", "message": str(e)},
            )

    def _handle_search_repository(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle search_repository tool call."""
        query = arguments.get("query", "")
        limit = arguments.get("limit", 10)

        if not query:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="search_repository", success=False,
                error={"type": "invalid_args", "message": "query is required"},
            )

        try:
            result = self.tool_layer.search_repository(query, limit)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="search_repository", success=True, data=result,
            )
        except Exception as e:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="search_repository", success=False,
                error={"type": "search_error", "message": str(e)},
            )

    def _handle_get_callers(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle get_callers tool call."""
        symbol_name = arguments.get("symbol_name", "")

        if not symbol_name:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_callers", success=False,
                error={"type": "invalid_args", "message": "symbol_name is required"},
            )

        try:
            result = self.tool_layer.get_callers(symbol_name)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_callers", success=True, data=result,
            )
        except Exception as e:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_callers", success=False,
                error={"type": "search_error", "message": str(e)},
            )

    def _handle_get_callees(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle get_callees tool call."""
        symbol_name = arguments.get("symbol_name", "")

        if not symbol_name:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_callees", success=False,
                error={"type": "invalid_args", "message": "symbol_name is required"},
            )

        try:
            result = self.tool_layer.get_callees(symbol_name)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_callees", success=True, data=result,
            )
        except Exception as e:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_callees", success=False,
                error={"type": "search_error", "message": str(e)},
            )

    def _handle_search_code(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle search_code tool call with file-scan cap."""
        query = arguments.get("query", "")
        file_pattern = arguments.get("file_pattern")
        max_matches = arguments.get("max_matches", 25)

        if not query:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="search_code", success=False,
                error={"type": "invalid_args", "message": "query is required"},
            )

        try:
            # Call with added max_files_scanned cap to prevent Azure flooding
            result = self.tool_layer.search_code(query, file_pattern, max_matches, max_files_scanned=40)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="search_code", success=True, data=result,
            )
        except TypeError:
            # Fallback for older RepositoryToolLayer that doesn't have max_files_scanned yet
            try:
                result = self.tool_layer.search_code(query, file_pattern, max_matches)
                return ToolObservation(
                    tool_call_id=tool_call_id, tool_name="search_code", success=True, data=result,
                )
            except Exception as e:
                return ToolObservation(
                    tool_call_id=tool_call_id, tool_name="search_code", success=False,
                    error={"type": "search_error", "message": str(e)},
                )
        except Exception as e:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="search_code", success=False,
                error={"type": "search_error", "message": str(e)},
            )

    def _handle_query_rim(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle query_rim tool call (RIM side only)."""
        if not self.graph_traverser or not self.target_resolver:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="query_rim", success=False,
                error={"type": "unavailable", "message": "query_rim not available on this side"},
            )

        entity_name = arguments.get("entity_name", "")
        relationship_type = arguments.get("relationship_type", "GENERIC")
        direction = arguments.get("direction", "FORWARD")

        if not entity_name:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="query_rim", success=False,
                error={"type": "invalid_args", "message": "entity_name is required"},
            )

        try:
            # Resolve entity
            target = self.target_resolver.resolve(entity_name)
            if not target:
                return ToolObservation(
                    tool_call_id=tool_call_id, tool_name="query_rim", success=True,
                    data={"found": False, "message": f"'{entity_name}' not found in this repository's index"},
                )

            # Map relationship type + direction to SemanticQueryClass
            query_class = self._map_to_query_class(relationship_type, direction)

            # Traverse
            intent = SemanticQueryIntent(
                query_class=query_class,
                target_raw_name=entity_name,
                direction=TraversalDirection.FORWARD if direction == "FORWARD" else TraversalDirection.REVERSE,
                confidence=1.0,
            )
            result = self.graph_traverser.traverse(intent, target)

            if not result.related_entities:
                return ToolObservation(
                    tool_call_id=tool_call_id, tool_name="query_rim", success=True,
                    data={
                        "found": True,
                        "related": [],
                        "message": result.explanation,
                    },
                )

            # Serialize related entities (cap to top 15)
            related_list = [
                {
                    "name": e.name,
                    "entity_type": e.entity_type,
                    "location": e.location,
                    "line_number": e.line_number,
                    "relationship_role": e.relationship_role,
                }
                for e in result.related_entities[:15]
            ]

            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="query_rim", success=True,
                data={
                    "found": True,
                    "related": related_list,
                    "message": result.explanation,
                },
            )

        except Exception as e:
            logger.error(f"query_rim error: {e}", exc_info=True)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="query_rim", success=False,
                error={"type": "traversal_error", "message": str(e)},
            )

    def _map_to_query_class(self, relationship_type: str, direction: str) -> SemanticQueryClass:
        """Map relationship_type + direction to SemanticQueryClass."""
        if relationship_type == "CALLS":
            return SemanticQueryClass.CALLS_FORWARD if direction == "FORWARD" else SemanticQueryClass.CALLS_REVERSE
        elif relationship_type == "IMPORTS":
            return SemanticQueryClass.IMPORTS_FORWARD if direction == "FORWARD" else SemanticQueryClass.IMPORTS_REVERSE
        elif relationship_type == "INHERITS":
            return SemanticQueryClass.INHERITS_FORWARD if direction == "FORWARD" else SemanticQueryClass.INHERITS_REVERSE
        elif relationship_type == "CONTAINS":
            return SemanticQueryClass.CONTAINMENT
        elif relationship_type == "ROUTE_HANDLER":
            return SemanticQueryClass.ROUTE_HANDLER
        elif relationship_type == "DATABASE_ACCESS":
            return SemanticQueryClass.DATABASE_ACCESS
        else:
            return SemanticQueryClass.GENERIC_LOOKUP
