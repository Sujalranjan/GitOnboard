"""
Deterministic fallback synthesizers for LLM tasks.
Invoked when all configured AI providers fail or are unavailable.
Always marks responses with ai_generated=False and provider='deterministic_fallback'.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeterministicFallbackSynthesizer:
    """Provides structured, verifiable deterministic fallbacks without AI generation."""

    @staticmethod
    def synthesize_trace_explanation(
        feature_query: str,
        trace_data: Dict[str, Any],
        context_details: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Synthesizes a structured, step-by-step trace walkthrough from deterministic
        graph facts, relationships, and code locations.
        """
        flow = []
        if isinstance(trace_data, dict):
            flow = trace_data.get("flow") or trace_data.get("nodes") or []
        elif isinstance(trace_data, list):
            flow = trace_data

        steps: List[str] = []
        for idx, node in enumerate(flow):
            name = node.get("name", "Unknown")
            typ = node.get("type", "component")
            file_id = node.get("file_id") or node.get("file_path", "")
            route = node.get("route", "")

            route_detail = f" [Endpoint: `{route}`]" if route else ""
            file_detail = f" in `{file_id}`" if file_id else ""
            steps.append(f"{idx + 1}. **{name}** ({typ}){route_detail}{file_detail}")

        if not steps:
            steps.append("No active execution path nodes were found in the trace graph.")

        explanation_lines = [
            f"# Deterministic Trace Flow: {feature_query}",
            "",
            "> **Deterministic fallback — No AI used.**",
            "> *This execution path was generated deterministically from static AST analysis, call graphs, and Fact Store relationships.*",
            "",
            "### Execution Sequence:",
            "",
            "\n".join(steps),
            "",
            "### Flow Summary:",
            f"The feature `{feature_query}` traverses {len(flow)} structural components from entrypoint through backend layers."
        ]

        return {
            "explanation": "\n".join(explanation_lines),
            "provider": "deterministic_fallback",
            "ai_generated": False,
        }
