from typing import Protocol, Any, List, Optional
from pydantic import BaseModel, Field
from pathlib import Path

class Diagnostic(BaseModel):
    message: str
    line: int
    column: int
    severity: str = "ERROR"

class ParsedFile(BaseModel):
    file_path: str = Field(..., description="The path of the parsed file.")
    language: str = Field(..., description="The language of the file.")
    ast: Any = Field(..., description="The language-specific AST object.")
    source: str = Field(..., description="The raw source code.")
    diagnostics: List[Diagnostic] = Field(default_factory=list, description="Parser errors or warnings.")
    metadata: dict = Field(default_factory=dict, description="Additional metadata (symbols, imports, etc).")

class LanguageProvider(Protocol):
    language: str
    
    def parse(self, file_path: str, source: str) -> ParsedFile:
        """
        Parses the source code and returns a ParsedFile containing the AST and any diagnostics.
        Must preserve source locations and comments if supported.
        Must recover from syntax errors where possible.
        """
        ...
