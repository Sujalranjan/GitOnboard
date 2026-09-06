"""
Pydantic contracts for inspection tools.
Defines all return types for inspect_file, inspect_symbol, read_symbol, etc.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SymbolMetadata(BaseModel):
    """Metadata about a single symbol without reading source."""
    symbol_id: str
    name: str
    qualified_name: str
    symbol_type: str  # function, class, method, variable, interface, etc.
    file_path: str
    line_start: int
    line_end: int
    language: str  # python, javascript, typescript, jsx, tsx
    signature: Optional[str] = None  # from metadata_json if available
    docstring: Optional[str] = None
    parent_symbol: Optional[str] = None  # for methods, nested functions


class SymbolRelationship(BaseModel):
    """A single relationship edge in the symbol graph."""
    name: str
    file_path: Optional[str] = None
    symbol_id: Optional[str] = None
    qualified_name: Optional[str] = None


class SymbolRelationships(BaseModel):
    """All relationships for a symbol."""
    calls: List[SymbolRelationship] = Field(default_factory=list)
    called_by: List[SymbolRelationship] = Field(default_factory=list)
    imports: List[Dict[str, Any]] = Field(default_factory=list)  # List[{"module": str}]
    imported_by: List[str] = Field(default_factory=list)  # List of file paths
    uses: List[SymbolRelationship] = Field(default_factory=list)
    used_by: List[SymbolRelationship] = Field(default_factory=list)


class InspectSymbolResult(BaseModel):
    """Result of inspect_symbol() tool."""
    symbol_id: str
    name: str
    qualified_name: str
    symbol_type: str
    file_path: str
    line_start: int
    line_end: int
    language: str
    signature: Optional[str] = None
    docstring: Optional[str] = None
    parent_symbol: Optional[str] = None
    relationships: SymbolRelationships = Field(default_factory=SymbolRelationships)
    success: bool = True
    error: Optional[str] = None
    candidates: Optional[List[Dict[str, Any]]] = None  # If ambiguous symbols found


class FileSymbol(BaseModel):
    """Single symbol in file outline."""
    name: str
    qualified_name: str
    symbol_type: str  # function, class, method, variable, interface
    line_start: int
    line_end: int
    symbol_id: str
    parent_symbol: Optional[str] = None


class InspectFileResult(BaseModel):
    """Result of inspect_file() tool."""
    file_path: str
    language: str  # python, javascript, typescript, jsx, tsx
    total_lines: int
    file_size_kb: float
    symbols: List[FileSymbol] = Field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class SourceReadResult(BaseModel):
    """Result of read_symbol(), read_lines(), or read_file() tools."""
    file_path: str
    source: str  # numbered source code (e.g. "   42 | code line")
    raw_text: str  # unnumbered source
    line_start: int
    line_end: int
    total_lines: int
    file_size_kb: float
    language: Optional[str] = None
    symbol_id: Optional[str] = None
    symbol_name: Optional[str] = None
    estimated_tokens: int = 0
    success: bool = True
    error: Optional[str] = None
    warning: Optional[str] = None
    from_source: str = "filesystem"  # filesystem or blob_storage


class TokenEstimate(BaseModel):
    """Token estimation for source code."""
    raw_text: str
    estimated_tokens: int
    estimation_method: str  # "approximate" or "tokenizer"


# Error responses use the success: False field on any result model
