"""
Structural Markdown Chunker - Splits documentation files into heading-aware (H1/H2)
semantic chunks with domain classification and line-level provenance.
"""
from __future__ import annotations
import re
from typing import List, Optional
from pydantic import BaseModel, Field


class DocChunk(BaseModel):
    chunk_id: str
    file_path: str
    heading: str
    domain: str
    text: str
    line_start: int
    line_end: int


def classify_heading_domain(heading: str, file_path: str) -> str:
    h = heading.lower()
    p = file_path.lower()
    
    if any(k in p for k in ["agents.md", "claude.md", ".cursor", ".agents", "skill.md"]):
        return "agent_instructions"
        
    if any(k in h for k in ["overview", "about", "introduction", "features", "what is"]) or heading == "(Top Level)":
        return "overview"
    if any(k in h for k in ["architecture", "design", "structure", "components", "data flow", "system"]):
        return "architecture"
    if any(k in h for k in ["api", "endpoints", "routes", "rest", "openapi", "graphql", "swagger"]):
        return "api"
    if any(k in h for k in ["install", "setup", "docker", "deploy", "requirements", "getting started", "run", "configuration", "env"]):
        return "deployment"
    if any(k in h for k in ["guide", "tutorial", "test", "contributing", "license", "usage"]):
        return "guides"
        
    return "overview" if any(fname in p for fname in ["readme.md", "readme.markdown"]) else "generic"


class StructuralMarkdownChunker:
    """
    Splits markdown documents into discrete chunks delineated by H1 (#) and H2 (##) headings.
    Preserves exact line ranges and tags each chunk with its semantic domain.
    """

    @staticmethod
    def chunk_document(file_path: str, content: str) -> List[DocChunk]:
        if not content or not content.strip():
            return []

        lines = content.splitlines()
        chunks: List[DocChunk] = []

        current_heading = "(Top Level)"
        current_lines: List[str] = []
        chunk_start_line = 1
        chunk_index = 0

        heading_pattern = re.compile(r'^(#{1,2})\s+(.+)$')

        for line_num, line in enumerate(lines, start=1):
            match = heading_pattern.match(line.strip())
            if match:
                if current_lines:
                    text = "\n".join(current_lines).strip()
                    if text:
                        chunk_index += 1
                        chunks.append(
                            DocChunk(
                                chunk_id=f"{file_path}#chunk_{chunk_index}",
                                file_path=file_path,
                                heading=current_heading,
                                domain=classify_heading_domain(current_heading, file_path),
                                text=text,
                                line_start=chunk_start_line,
                                line_end=line_num - 1,
                            )
                        )
                current_heading = match.group(2).strip()
                current_lines = [line]
                chunk_start_line = line_num
            else:
                current_lines.append(line)

        # Flush final chunk
        text = "\n".join(current_lines).strip()
        if text:
            chunk_index += 1
            chunks.append(
                DocChunk(
                    chunk_id=f"{file_path}#chunk_{chunk_index}",
                    file_path=file_path,
                    heading=current_heading,
                    domain=classify_heading_domain(current_heading, file_path),
                    text=text,
                    line_start=chunk_start_line,
                    line_end=len(lines),
                )
            )

        return chunks
