"""
Repository Tools: Thin adapters delegating to RepositoryToolLayer, Fact Store, and RIM services.
"""
from __future__ import annotations

from typing import Any, Dict, List
from backend.agent.tools.contracts import AgentToolContext, ToolDefinition
from backend.models.fact_store import FactCapability, FactRoute
from backend.repository_tools.tools import RepositoryToolLayer


def _get_tool_layer(context: AgentToolContext) -> RepositoryToolLayer:
    return RepositoryToolLayer(
        repo_name=context.repository_id,
        db=context.db,
        repo_root=context.worktree_path,
        user_id=context.user_id,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tool Handlers
# ──────────────────────────────────────────────────────────────────────────────

def handle_search_code(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    tool_layer = _get_tool_layer(context)
    query = args["query"]
    limit = args.get("limit", 20)
    path_pattern = args.get("path_pattern")
    results = tool_layer.search_repository(query=query, path_pattern=path_pattern, limit=limit)
    return {"query": query, "match_count": len(results), "matches": results}


def handle_search_symbols(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    tool_layer = _get_tool_layer(context)
    pattern = args.get("pattern", "*")
    limit = args.get("limit", 20)
    files = tool_layer.find_files(pattern=pattern, limit=limit)
    return {"pattern": pattern, "files_found": files}


def handle_get_symbol(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    tool_layer = _get_tool_layer(context)
    name = args["name"]
    symbols = tool_layer.get_symbol(name)
    return {"name": name, "symbol_count": len(symbols), "symbols": symbols}


def handle_get_callers(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    tool_layer = _get_tool_layer(context)
    symbol_name = args["symbol_name"]
    callers = tool_layer.get_callers(symbol_name)
    return {"symbol_name": symbol_name, "caller_count": len(callers), "callers": callers}


def handle_get_callees(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    tool_layer = _get_tool_layer(context)
    symbol_name = args["symbol_name"]
    callees = tool_layer.get_callees(symbol_name)
    return {"symbol_name": symbol_name, "callee_count": len(callees), "callees": callees}


def handle_get_dependencies(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    tool_layer = _get_tool_layer(context)
    deps = tool_layer.get_dependencies()
    return {"dependencies": deps}


def handle_get_route(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    path_query = args["path"]
    method = args.get("method", "").upper()
    if not context.db:
        return {"routes": [], "message": "Database session not available in context"}

    query = context.db.query(FactRoute)
    if method:
        query = query.filter(FactRoute.method == method)
    routes = query.filter(FactRoute.path.ilike(f"%{path_query}%")).limit(20).all()

    serialized = [
        {"id": r.id, "method": r.method, "path": r.path, "handler_symbol_id": r.handler_symbol_id}
        for r in routes
    ]
    return {"path": path_query, "method": method, "route_count": len(serialized), "routes": serialized}


def handle_get_feature(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    name = args["name"]
    if not context.db:
        return {"capabilities": [], "message": "Database session not available in context"}

    caps = (
        context.db.query(FactCapability)
        .filter(FactCapability.name.ilike(f"%{name}%"))
        .limit(20)
        .all()
    )
    serialized = [
        {
            "id": c.id,
            "name": c.name,
            "type": c.capability_type,
            "status": c.status,
            "evidence_summary": c.evidence_summary,
        }
        for c in caps
    ]
    return {"query": name, "capabilities": serialized}


def handle_trace_feature(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    from backend.intelligence.feature_tracing import DeterministicTracer
    from backend.intelligence.store.fact_store import load_rim_from_fact_store

    seed_id = args.get("seed_id", "")
    analysis_id = args.get("analysis_id")

    if not context.db or not analysis_id:
        return {
            "trace": [],
            "seed_id": seed_id,
            "message": "Tracing requires analysis_id and active DB session",
        }

    model = load_rim_from_fact_store(context.db, analysis_id=analysis_id)
    tracer = DeterministicTracer(model)
    trace_result = tracer.trace_feature(seed_id)
    return {"seed_id": seed_id, "nodes_visited": len(trace_result.nodes), "trace": trace_result.to_dict()}


def handle_read_file(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    tool_layer = _get_tool_layer(context)
    path = args["path"]
    start_line = args.get("start_line", 1)
    end_line = args.get("end_line", 50)
    file_content = tool_layer.read_file(path=path, start_line=start_line, end_line=end_line)
    return file_content


# ──────────────────────────────────────────────────────────────────────────────
# Tool Definitions Catalog
# ──────────────────────────────────────────────────────────────────────────────

REPOSITORY_TOOLS: List[ToolDefinition] = [
    ToolDefinition(
        name="search_code",
        description="Search repository file contents for a string pattern or keyword",
        category="repository",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text pattern to search for"},
                "limit": {"type": "integer", "default": 20, "description": "Max results to return"},
                "path_pattern": {"type": "string", "description": "Optional glob filter (e.g. *.py)"},
            },
            "required": ["query"],
        },
        handler=handle_search_code,
    ),
    ToolDefinition(
        name="search_symbols",
        description="Find files and symbols matching a path/name pattern",
        category="repository",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "default": "*", "description": "Glob pattern for matching files"},
                "limit": {"type": "integer", "default": 20},
            },
        },
        handler=handle_search_symbols,
    ),
    ToolDefinition(
        name="get_symbol",
        description="Look up definition and locations of a code symbol (class, function, method)",
        category="repository",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Symbol name to look up"},
            },
            "required": ["name"],
        },
        handler=handle_get_symbol,
    ),
    ToolDefinition(
        name="get_callers",
        description="Get symbols and functions that invoke the specified symbol",
        category="repository",
        input_schema={
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "Target function/method name"},
            },
            "required": ["symbol_name"],
        },
        handler=handle_get_callers,
    ),
    ToolDefinition(
        name="get_callees",
        description="Get functions and methods invoked by the specified symbol",
        category="repository",
        input_schema={
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "Target function/method name"},
            },
            "required": ["symbol_name"],
        },
        handler=handle_get_callees,
    ),
    ToolDefinition(
        name="get_dependencies",
        description="Get the repository third-party package dependencies",
        category="repository",
        input_schema={"type": "object", "properties": {}},
        handler=handle_get_dependencies,
    ),
    ToolDefinition(
        name="get_route",
        description="Look up HTTP REST route definitions and handler mappings",
        category="repository",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Route path fragment to search for"},
                "method": {"type": "string", "description": "Optional HTTP method (GET, POST, etc.)"},
            },
            "required": ["path"],
        },
        handler=handle_get_route,
    ),
    ToolDefinition(
        name="get_feature",
        description="Look up Layer 6 architectural capabilities and detected features",
        category="repository",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Feature or capability name"},
            },
            "required": ["name"],
        },
        handler=handle_get_feature,
    ),
    ToolDefinition(
        name="trace_feature",
        description="Run a deterministic BFS execution trace from an endpoint to DB models",
        category="repository",
        input_schema={
            "type": "object",
            "properties": {
                "seed_id": {"type": "string", "description": "Starting symbol/route ID"},
                "analysis_id": {"type": "integer", "description": "Analysis ID"},
            },
            "required": ["seed_id", "analysis_id"],
        },
        handler=handle_trace_feature,
    ),
    ToolDefinition(
        name="read_file",
        description="Read file contents with bounded line range from the repository snapshot",
        category="repository",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "start_line": {"type": "integer", "default": 1, "description": "1-based starting line"},
                "end_line": {"type": "integer", "default": 50, "description": "1-based ending line"},
            },
            "required": ["path"],
        },
        handler=handle_read_file,
    ),
]
