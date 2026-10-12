"""
Centralized Jupyter Notebook (.ipynb) source resolution module.

Provides in-memory conversion of .ipynb notebooks into clean Python (py:percent) source,
maintaining .ipynb as the single canonical path across GitOnboard.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

import jupytext

logger = logging.getLogger(__name__)


@dataclass
class SourceDocument:
    """Represents a resolved source document for analysis or retrieval."""
    path: str
    source: str
    language: str
    source_type: str  # "source" or "notebook"
    conversion_error: Optional[str] = None
    cell_mapping: Optional[List[Dict[str, Any]]] = None


@lru_cache(maxsize=128)
def _convert_ipynb_cached(content_hash: str, raw_content: str) -> tuple[str, Optional[str]]:
    """
    Internal cached converter using content SHA256 as cache key.
    Returns (converted_source, error_message).
    """
    try:
        notebook = jupytext.reads(raw_content, fmt="ipynb")
        # Strip noisy cell metadata (e.g. Google Colab referenced_widgets, output IDs)
        for cell in getattr(notebook, "cells", []):
            if hasattr(cell, "metadata") and isinstance(cell.metadata, dict):
                # Retain only 'id' if present to satisfy nbformat schema without widget bloat
                cell_id = cell.metadata.get("id")
                cell.metadata = {"id": cell_id} if cell_id else {}
        # metadata_filter="-all" ensures uniform headers without notebook-specific clutter
        python_source = jupytext.writes(notebook, fmt="py:percent", metadata_filter="-all")
        return python_source, None
    except Exception as exc:
        logger.warning(f"[NOTEBOOK] Failed to convert notebook content: {exc}")
        return "", str(exc)


def resolve_source_document(path: str, raw_content: str) -> SourceDocument:
    """
    Resolves raw file content into a SourceDocument.

    For .ipynb files:
        Converts in-memory via Jupytext to py:percent formatted Python code.
        If conversion fails due to malformed JSON, returns an empty source with conversion_error set,
        ensuring the AST parser and tools never crash.

    For non-notebook files:
        Returns raw content unchanged.
    """
    if not path or not path.lower().endswith(".ipynb"):
        return SourceDocument(
            path=path,
            source=raw_content or "",
            language="Unknown",
            source_type="source",
            conversion_error=None,
        )

    # Compute content SHA256 for cache keying
    content_hash = hashlib.sha256(raw_content.encode("utf-8", errors="replace")).hexdigest()
    python_source, error = _convert_ipynb_cached(content_hash, raw_content)

    if error:
        return SourceDocument(
            path=path,
            source="",
            language="Python",
            source_type="notebook",
            conversion_error=error,
        )

    return SourceDocument(
        path=path,
        source=python_source,
        language="Python",
        source_type="notebook",
        conversion_error=None,
    )
