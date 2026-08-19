"""
Trace Context Builder - Assembles deep, source-grounded context for feature traces.
Extracts bounded source code snippets, signatures, and Fact Store relationships.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session

from backend.models.fact_store import FactSymbol, FactRoute, FactRelationship, FactFile
from backend.repository_tools import resolve_repo_root, RepositoryToolLayer

logger = logging.getLogger(__name__)

MAX_SOURCE_LINES_PER_NODE = 60
MAX_NODES_TO_EXTRACT = 10


class TraceContextBuilder:
    """Assembles rich, source-grounded context for trace execution flows."""

    def __init__(
        self,
        db: Optional[Session] = None,
        analysis_id: Optional[int] = None,
        repo_name: Optional[str] = None,
        user_id: Optional[int] = None
    ):
        self.db = db
        self.analysis_id = analysis_id
        self.repo_name = repo_name
        self.user_id = user_id

    def build_context(self, trace_data: Dict[str, Any]) -> str:
        """
        Extracts bounded source snippets and Fact Store relationships for each node in the trace flow.
        """
        flow = []
        if isinstance(trace_data, dict):
            flow = trace_data.get("flow") or trace_data.get("nodes") or []
        elif isinstance(trace_data, list):
            flow = trace_data

        if not flow:
            return "No active trace nodes found in the trace data."

        # Setup tool layer for file extraction if repo details are present
        tool_layer = None
        if self.repo_name and self.user_id and self.db:
            try:
                repo_root = resolve_repo_root(self.repo_name, self.user_id, self.db)
                tool_layer = RepositoryToolLayer(
                    repo_name=self.repo_name,
                    analysis_id=self.analysis_id,
                    db=self.db,
                    repo_root=repo_root,
                    user_id=self.user_id
                )
            except Exception as e:
                logger.warning(f"TraceContextBuilder: Could not initialize RepositoryToolLayer: {e}")

        sections: List[str] = []
        sections.append("=== TRACE EXECUTION NODES & BOUNDED SOURCE CODE ===")

        for idx, node in enumerate(flow[:MAX_NODES_TO_EXTRACT]):
            name = node.get("name", "Unknown")
            typ = node.get("type", "component")
            file_path = node.get("file_id") or node.get("file_path", "")
            node_id = node.get("id")

            node_lines = [
                f"### Node {idx + 1}: `{name}` ({typ})",
                f"- **File Path**: `{file_path}`"
            ]

            # Query Fact Store details if database session is active
            start_line = None
            end_line = None
            docstring = ""
            route_str = ""

            if self.db and self.analysis_id:
                # Check for associated route
                try:
                    route_rec = self.db.query(FactRoute).filter(
                        FactRoute.analysis_id == self.analysis_id,
                        FactRoute.path.ilike(f"%{name}%")
                    ).first()
                    if route_rec:
                        route_str = f"{route_rec.method} {route_rec.path}"
                        node_lines.append(f"- **HTTP Route**: `{route_str}`")
                except Exception:
                    pass

                # Check for symbol metadata
                try:
                    sym_rec = self.db.query(FactSymbol).filter(
                        FactSymbol.analysis_id == self.analysis_id,
                        FactSymbol.name == name
                    ).first()
                    if sym_rec:
                        start_line = sym_rec.line_start
                        end_line = sym_rec.line_end
                        if sym_rec.metadata_json and isinstance(sym_rec.metadata_json, dict):
                            docstring = sym_rec.metadata_json.get("docstring", "")
                            if docstring:
                                node_lines.append(f"- **Docstring**: {docstring.strip()}")
                except Exception:
                    pass

            # Extract source snippet via tool_layer or snapshot
            source_snippet = ""
            if tool_layer and file_path:
                try:
                    s_line = start_line or 1
                    e_line = min(end_line or (s_line + MAX_SOURCE_LINES_PER_NODE), s_line + MAX_SOURCE_LINES_PER_NODE)
                    read_res = tool_layer.read_file(file_path, start_line=s_line, end_line=e_line)
                    raw_content = read_res.get("content", "")
                    if raw_content and raw_content.strip():
                        source_snippet = raw_content.strip()
                except Exception as e:
                    logger.debug(f"TraceContextBuilder: Could not read source for {file_path}: {e}")

            if source_snippet:
                node_lines.append("- **Verified Source Code**:\n```\n" + source_snippet + "\n```")
            else:
                node_lines.append("- **Source Code**: *(Snippet not locally available)*")

            sections.append("\n".join(node_lines))

        return "\n\n".join(sections)
