"""
Tool Dispatch Table: wraps RepositoryToolLayer and get_code_relationships tool.

Routes tool calls from the LLM to the appropriate backend, catches all exceptions.
Exposes different tool sets for baseline (no RIM) vs. RIM side (with get_code_relationships).
"""

import logging
from typing import Any, Dict, List, Optional

from backend.agent.loop.contracts import ToolObservation
from backend.config import settings
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
        # Determine include_rim from presence of graph_traverser/target_resolver
        # If both are None, this is baseline (no RIM); if both present, this is RIM mode
        self.include_rim = graph_traverser is not None and target_resolver is not None

    def specs(self, include_rim: bool) -> List[ToolSpec]:
        """
        Return tool specs for system prompt.

        WITHOUT RIM (baseline): Basic repository investigation tools
          - read_file: Read file content (authoritative implementation)
          - search_repository: Search by name/pattern/symbol
          - get_tree: Show directory structure

        WITH RIM: Advanced investigation tool set
          - All baseline tools +
          - get_file_outline: Outline symbols in file (recommended for files >200 lines)
          - search_code: Raw text/regex search (configs, Dockerfiles, exact patterns)
          - get_code_relationships: Bounded graph relationships (CALLS, IMPORTS, INHERITS, etc.)

        Args:
            include_rim: if True, include advanced code navigation + RIM tool

        Returns:
            List of ToolSpec objects for the prompt builder
        """
        # Always include: basic file access
        base_tools = [
            ToolSpec(
                "read_file",
                "Read a portion of a source file or an entire function/symbol. Returns line-numbered content. Authoritative tool for inspecting actual code implementation. Specify start_line and end_line for a slice (up to 250 lines returned at once), or specify 'symbol' to inspect a specific function/class directly.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to repo root"},
                        "start_line": {"type": "integer", "description": "Starting line number (default 1)"},
                        "end_line": {"type": "integer", "description": "Ending line number (safe read limit is 250 lines max per request)."},
                        "symbol": {"type": "string", "description": "Optional name of function, class, or method to read directly."},
                        "context_lines": {
                            "type": "integer",
                            "description": "Optional number of surrounding context lines to include before start_line and after end_line (default 0, max 25).",
                        },
                    },
                    "required": ["path"],
                },
            ),
            ToolSpec(
                "search_repository",
                "Search for symbols, definitions, references, and files across the repository by name or pattern. Use for normal repository discovery and finding relevant code files. Supports comma-separated multi-query batching (e.g., 'login,auth,token') and offset-based pagination.",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Symbol name, file name, or code pattern (e.g., 'login', 'auth.js', 'const token'). Comma-separated queries supported (e.g., 'mysql,db,connection'). Keep terms simple and code-like, not natural language descriptions."},
                        "limit": {"type": "integer", "description": "Max results per batch (default 10)"},
                        "offset": {"type": "integer", "description": "Starting position for pagination (default 0). To get next 10 results, use offset=10. Example: search_repository(query='auth', limit=10, offset=30) gets results 31-40."},
                    },
                    "required": ["query"],
                },
            ),
            ToolSpec(
                "get_tree",
                "Get directory tree structure of the repository from any path with specified depth. Use for architecture overview, folder orientation, and discovering top-level modules.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Starting path (e.g. 'backend', 'backend/routers'). Empty string = root (default)"},
                        "depth": {"type": "integer", "description": "Directory depth to show (0-10, default 0). depth=0 shows only immediate contents, depth=1 shows one level deeper, etc."},
                    },
                },
            ),
        ]

        # If RIM enabled, add advanced code navigation tools
        if include_rim:
            rim_tools = [
                ToolSpec(
                    "get_file_outline",
                    "Get an outline of symbols (functions, classes, methods) in a file. Highly recommended for structural inspection of large files (>200 lines) before calling read_file to pinpoint exact line ranges.",
                    {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path relative to repo root"},
                        },
                        "required": ["path"],
                    },
                ),
                ToolSpec(
                    "search_code",
                    "Search file contents using raw text or regex patterns. Use for exact lexical matches, regex searches, configuration files (Dockerfiles, JSON, YAML), or specific file patterns.",
                    {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Exact text or regex pattern to search for"},
                            "file_pattern": {"type": "string", "description": "Optional glob pattern to limit search scope (e.g., '*.py', '*.json', 'Dockerfile*'). Leave empty to search across all code files."},
                            "max_matches": {"type": "integer", "description": "Max results (default 25)"},
                        },
                        "required": ["query"],
                    },
                ),
            ]
            base_tools.extend(rim_tools)

        # Add get_code_relationships if RIM enabled (exposing clear name to LLM)
        if include_rim and self.graph_traverser and self.target_resolver:
            base_tools.append(
                ToolSpec(
                    "get_code_relationships",
                    "Query the repository code relationship graph for structural connections (CALLS, IMPORTS, INHERITS, CONTAINS, ROUTE_HANDLER, DATABASE_ACCESS, GENERIC). Use when asked about callers/callees, dependencies, imports, inheritance, route handlers, or database table queries. Do NOT use for raw text searches, comments, configuration files (Docker, YAML, JSON), or string literals (use search_code or search_repository instead). Returns structural facts and file locations.",
                    {
                        "type": "object",
                        "properties": {
                            "entity_name": {
                                "type": "string",
                                "description": "Symbol, function, class, file, route, or table name to query",
                            },
                            "relationship_type": {
                                "type": "string",
                                "enum": ["CALLS", "IMPORTS", "INHERITS", "CONTAINS", "ROUTE_HANDLER", "DATABASE_ACCESS", "GENERIC"],
                                "default": "GENERIC",
                                "description": "Type of relationship to explore (CALLS, IMPORTS, INHERITS, ROUTE_HANDLER, DATABASE_ACCESS, etc.)",
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["FORWARD", "REVERSE", "BOTH"],
                                "default": "FORWARD",
                                "description": "FORWARD: what does entity call/import/access? REVERSE: who calls/imports/accesses entity? BOTH: incoming and outgoing",
                            },
                            "scope": {
                                "type": "string",
                                "enum": ["LOCAL", "NEIGHBORHOOD", "GLOBAL"],
                                "default": "LOCAL",
                                "description": "LOCAL: 1-hop direct relationships (default). NEIGHBORHOOD: bounded multi-hop traversal (depth 1-3). GLOBAL: repository-wide relationship inspection.",
                            },
                            "depth": {
                                "type": "integer",
                                "default": 1,
                                "description": "Number of graph hops (1 for LOCAL, 1-3 for NEIGHBORHOOD/GLOBAL, default 1, max 3)",
                            },
                            "limit": {
                                "type": "integer",
                                "default": 15,
                                "description": "Maximum number of related results to return (default 15, max 50)",
                            },
                        },
                        "required": ["entity_name"],
                    },
                )
            )

        return base_tools

    def dispatch(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        max_content_tokens: Optional[int] = None,
        control_reservation_tokens: int = 60,
        tool_call_id: Optional[str] = None,
    ) -> ToolObservation:
        """
        Dispatch tool call to underlying implementation.

        Catches all exceptions and returns ToolObservation(success=False, error=...).
        Never raises into the loop.

        CRITICAL: Enforces tool restrictions based on mode (baseline vs RIM).
        Baseline can only access: read_file, search_repository, get_tree
        RIM can access: read_file, search_repository, get_tree, get_file_outline, search_code, get_code_relationships
        """
        if not tool_call_id:
            tool_call_id = f"{tool_name}:{hash(str(arguments))}"

        # ENFORCE TOOL RESTRICTIONS BY MODE
        allowed_baseline_tools = {"read_file", "search_repository", "get_tree"}
        allowed_rim_tools = {
            "read_file", "search_repository", "get_tree",
            "get_file_outline", "search_code", "get_code_relationships"
        }

        allowed_tools = allowed_rim_tools if self.include_rim else allowed_baseline_tools

        if tool_name not in allowed_tools:
            return ToolObservation(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                success=False,
                error={
                    "type": "tool_not_allowed",
                    "message": f"Tool '{tool_name}' is not available in {'RIM' if self.include_rim else 'baseline'} mode. "
                               f"Allowed tools: {', '.join(sorted(allowed_tools))}"
                },
            )

        try:
            if tool_name == "read_file":
                return self._handle_read_file(
                    arguments,
                    tool_call_id,
                    max_content_tokens=max_content_tokens,
                    control_reservation_tokens=control_reservation_tokens,
                )
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
            elif tool_name == "get_tree":
                return self._handle_get_tree(arguments, tool_call_id)
            elif tool_name == "get_code_relationships":
                return self._handle_get_code_relationships(arguments, tool_call_id)
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

    def _handle_read_file(
        self,
        arguments: Dict[str, Any],
        tool_call_id: str,
        max_content_tokens: Optional[int] = None,
        control_reservation_tokens: int = 60,
    ) -> ToolObservation:
        """Handle read_file tool call."""
        path = arguments.get("path") or arguments.get("file") or arguments.get("file_path") or ""
        start_line = arguments.get("start_line", 1)
        end_line = arguments.get("end_line", None)
        context_lines = arguments.get("context_lines", 0)

        if not path:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="read_file", success=False,
                error={"type": "invalid_args", "message": "path is required"},
            )

        kwargs: Dict[str, Any] = {"context_lines": context_lines}
        if "symbol" in arguments:
            kwargs["symbol"] = arguments["symbol"]
        if max_content_tokens is not None:
            kwargs["max_content_tokens"] = max_content_tokens
            kwargs["control_reservation_tokens"] = control_reservation_tokens

        try:
            try:
                result = self.tool_layer.read_file(
                    path,
                    start_line,
                    end_line,
                    **kwargs,
                )
            except TypeError:
                # Fallback if mock or tool_layer doesn't accept token reservation kwargs
                result = self.tool_layer.read_file(
                    path,
                    start_line,
                    end_line,
                    context_lines=context_lines,
                )
            # Check if result contains an error (file not found)
            if "error" in result:
                return ToolObservation(
                    tool_call_id=tool_call_id, tool_name="read_file", success=False,
                    error={"type": result.get("error"), "message": result.get("message")},
                )
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
        path = arguments.get("path") or arguments.get("file") or arguments.get("file_path") or ""

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
        default_limit = getattr(settings, "investigation_search_limit", 10)
        limit = arguments.get("limit", default_limit)
        offset = arguments.get("offset", 0)

        if not query:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="search_repository", success=False,
                error={"type": "invalid_args", "message": "query is required"},
            )

        try:
            result = self.tool_layer.search_repository(query, limit, offset)
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

        # DIAGNOSTIC: Log tool_layer state at dispatch entry
        logger.error(f"[tool_dispatch:search_code:DIAGNOSTIC] tool_layer.db={self.tool_layer.db is not None} tool_layer.analysis_id={self.tool_layer.analysis_id}")

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

    def _handle_get_tree(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle get_tree tool call."""
        path = arguments.get("path", "")
        depth = arguments.get("depth", 0)

        # Convert string parameters to integers if needed (from LLM tool calls)
        try:
            depth = int(depth) if depth is not None else 0
        except (ValueError, TypeError):
            depth = 0

        try:
            result = self.tool_layer.get_tree(path=path, depth=depth)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_tree", success=True, data=result,
            )
        except Exception as e:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_tree", success=False,
                error={"type": "tree_error", "message": str(e)},
            )

    def _handle_get_code_relationships(self, arguments: Dict[str, Any], tool_call_id: str) -> ToolObservation:
        """Handle get_code_relationships tool call (RIM side only)."""
        if not self.graph_traverser or not self.target_resolver:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_code_relationships", success=False,
                error={"type": "unavailable", "message": "get_code_relationships not available on this side"},
            )

        entity_name = str(
            arguments.get("entity_name")
            or arguments.get("symbol")
            or arguments.get("symbol_name")
            or arguments.get("name")
            or ""
        ).strip()
        relationship_type = str(arguments.get("relationship_type") or "GENERIC").upper().strip()
        direction = str(arguments.get("direction") or "FORWARD").upper().strip()
        scope = str(arguments.get("scope") or "LOCAL").upper().strip()
        depth = arguments.get("depth", 1)
        limit = arguments.get("limit", 15)

        if not entity_name:
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_code_relationships", success=False,
                error={"type": "invalid_args", "message": "entity_name is required (pass 'entity_name' or 'symbol')"},
            )

        if direction not in ("FORWARD", "REVERSE", "BOTH"):
            direction = "FORWARD"
        if scope not in ("LOCAL", "NEIGHBORHOOD", "GLOBAL"):
            scope = "LOCAL"

        if scope == "LOCAL":
            depth = 1
        else:
            try:
                depth = max(1, min(int(depth), 3))
            except (TypeError, ValueError):
                depth = 1

        try:
            limit = max(1, min(int(limit), 50))
        except (TypeError, ValueError):
            limit = 15

        try:
            # Resolve entity
            target = self.target_resolver.resolve(entity_name)
            if not target:
                logger.debug(f"[get_code_relationships] Entity '{entity_name}' not found in repository index")
                return ToolObservation(
                    tool_call_id=tool_call_id, tool_name="get_code_relationships", success=True,
                    data={
                        "found": False,
                        "resolution": "ENTITY_NOT_FOUND",
                        "message": f"'{entity_name}' was not found in this repository index.",
                        "fallback": {
                            "tool": "search_repository",
                            "query": entity_name
                        }
                    },
                )

            logger.debug(f"[get_code_relationships] Resolved '{entity_name}' to {type(target).__name__}")

            if hasattr(self.graph_traverser, "traverse_bounded"):
                result = self.graph_traverser.traverse_bounded(
                    target=target,
                    relationship_type=relationship_type,
                    direction=direction,
                    scope=scope,
                    depth=depth,
                    limit=limit,
                    target_raw_name=entity_name,
                )
            else:
                query_class = self._map_to_query_class(relationship_type, direction)
                intent = SemanticQueryIntent(
                    query_class=query_class,
                    target_raw_name=entity_name,
                    direction=TraversalDirection(direction) if direction in ("FORWARD", "REVERSE", "BOTH") else TraversalDirection.FORWARD,
                    confidence=1.0,
                )
                result = self.graph_traverser.traverse(intent, target)

            if not result.related_entities:
                logger.debug(f"[get_code_relationships] No related entities for '{entity_name}' ({relationship_type}, {direction})")
                return ToolObservation(
                    tool_call_id=tool_call_id, tool_name="get_code_relationships", success=True,
                    data={
                        "found": False,
                        "resolution": "NO_STATIC_EDGE_FOUND",
                        "message": f"No statically resolved {relationship_type} relationships found for '{entity_name}' ({direction}). Dynamic JavaScript/TypeScript constructs, runtime registration, or indirect references may exist.",
                        "fallback": {
                            "tool": "search_repository",
                            "query": entity_name
                        }
                    },
                )

            # Serialize related entities (cap to limit)
            related_list = []
            for e in result.related_entities[:limit]:
                item = {
                    "name": e.name,
                    "entity_type": e.entity_type,
                    "location": e.location,
                    "line_number": e.line_number,
                    "relationship_role": e.relationship_role,
                }
                if getattr(e, "path", None):
                    item["path"] = e.path
                if getattr(e, "relationships", None):
                    item["relationships"] = e.relationships
                related_list.append(item)

            from backend.models.fact_store import FactFile
            target_name = getattr(target, "name", getattr(target, "path", entity_name))
            target_type = getattr(target, "symbol_type", "file" if isinstance(target, FactFile) else "entity")
            target_loc = getattr(target, "path", target.file.path if getattr(target, "file", None) else "")
            target_line = getattr(target, "line_start", 1)

            logger.debug(f"[get_code_relationships] Found {len(related_list)} related entities for '{entity_name}'")
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_code_relationships", success=True,
                data={
                    "found": True,
                    "resolution": "STATIC_CONFIRMED",
                    "scope": scope,
                    "depth": depth,
                    "direction": direction,
                    "target": {
                        "name": target_name,
                        "type": target_type,
                        "location": target_loc,
                        "line": target_line,
                    },
                    "related": related_list,
                    "message": result.explanation,
                },
            )

        except Exception as e:
            logger.error(f"get_code_relationships error: {e}", exc_info=True)
            return ToolObservation(
                tool_call_id=tool_call_id, tool_name="get_code_relationships", success=False,
                error={"type": "traversal_error", "message": str(e)},
            )

    def _map_to_query_class(self, relationship_type: str, direction: str) -> SemanticQueryClass:
        """Map relationship_type + direction to SemanticQueryClass."""
        if relationship_type == "CALLS":
            return SemanticQueryClass.CALLS_FORWARD if direction != "REVERSE" else SemanticQueryClass.CALLS_REVERSE
        elif relationship_type == "IMPORTS":
            return SemanticQueryClass.IMPORTS_FORWARD if direction != "REVERSE" else SemanticQueryClass.IMPORTS_REVERSE
        elif relationship_type == "INHERITS":
            return SemanticQueryClass.INHERITS_FORWARD if direction != "REVERSE" else SemanticQueryClass.INHERITS_REVERSE
        elif relationship_type == "CONTAINS":
            return SemanticQueryClass.CONTAINMENT
        elif relationship_type == "ROUTE_HANDLER":
            return SemanticQueryClass.ROUTE_HANDLER
        elif relationship_type == "DATABASE_ACCESS":
            return SemanticQueryClass.DATABASE_ACCESS
        else:
            return SemanticQueryClass.GENERIC_LOOKUP
