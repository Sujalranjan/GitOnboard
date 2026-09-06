"""
Inspection tools for Phase 2L repository exploration.

Public API:
- inspect_file() - Get file structure and symbol outline
- inspect_symbol() - Get metadata about a specific symbol
- read_symbol() - Read exact source code of a symbol
- read_lines() - Read specific line range from a file
- read_file() - Read entire file

All tools reuse RepositoryToolLayer and QueryLayer infrastructure.
"""

from .contracts import (
    InspectFileResult,
    InspectSymbolResult,
    SourceReadResult,
    SymbolMetadata,
    FileSymbol,
    SymbolRelationships,
)

from .file_inspector import inspect_file
from .symbol_inspector import inspect_symbol
from .source_reader import read_symbol, read_lines, read_file

__all__ = [
    # Contracts
    "InspectFileResult",
    "InspectSymbolResult",
    "SourceReadResult",
    "SymbolMetadata",
    "FileSymbol",
    "SymbolRelationships",
    # Tools
    "inspect_file",
    "inspect_symbol",
    "read_symbol",
    "read_lines",
    "read_file",
]
