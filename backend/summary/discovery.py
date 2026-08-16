"""
Documentation Discovery - Scans repository snapshot for markdown and mermaid documentation.
"""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List, Optional
from sqlalchemy.orm import Session

from backend.models.fact_store import FactFile
from .schemas import DiscoveredDoc, DocType, DocPriority
from .classifier import DocClassifier

IGNORED_DIRECTORIES = {
    ".git", "node_modules", "venv", ".venv", "env", ".env",
    "__pycache__", "build", "dist", ".idea", ".vscode", "vendor",
    "site-packages", "target", "bin", "obj"
}

DOC_EXTENSIONS = {".md", ".markdown", ".mmd", ".rst"}
MAX_DISCOVERY_FILE_SIZE = 150 * 1024  # 150 KB max per file for reading


class DocDiscovery:
    """
    Discovers all documentation (.md, .mmd) files in the repository.
    Can discover directly from snapshot filesystem or fallback to Fact Store.
    """

    def __init__(self, classifier: Optional[DocClassifier] = None):
        self.classifier = classifier or DocClassifier()

    def discover_from_directory(self, repo_root: Path | str) -> List[DiscoveredDoc]:
        root_path = Path(repo_root).resolve()
        if not root_path.exists() or not root_path.is_dir():
            return []

        docs: List[DiscoveredDoc] = []

        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

            for file in files:
                ext = Path(file).suffix.lower()
                if ext not in DOC_EXTENSIONS:
                    continue

                full_path = Path(root) / file
                rel_path = str(full_path.relative_to(root_path)).replace("\\", "/")

                try:
                    file_size = full_path.stat().st_size
                except Exception:
                    file_size = 0

                content = ""
                headings: List[str] = []
                line_count = 0

                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        raw_content = f.read(MAX_DISCOVERY_FILE_SIZE)
                        content = raw_content
                        lines = raw_content.splitlines()
                        line_count = len(lines)
                        for line in lines:
                            stripped = line.strip()
                            if stripped.startswith("#"):
                                headings.append(stripped[:100])
                except Exception:
                    pass

                doc_type, priority = self.classifier.classify(rel_path, content)

                if priority == DocPriority.EXCLUDE:
                    continue

                docs.append(
                    DiscoveredDoc(
                        path=rel_path,
                        filename=file,
                        doc_type=doc_type,
                        priority=priority,
                        raw_size=file_size,
                        line_count=line_count,
                        headings=headings[:20],
                        content=content,
                        token_estimate=len(content) // 4,
                    )
                )

        # Sort docs by priority desc, then path asc
        docs.sort(key=lambda d: (-d.priority.value, d.path))
        return docs

    def discover_from_fact_store(self, db: Session, analysis_id: int) -> List[DiscoveredDoc]:
        """Fallback discovery using relational Fact Store file records."""
        records = (
            db.query(FactFile)
            .filter(
                FactFile.analysis_id == analysis_id,
                FactFile.is_documentation == True,
            )
            .all()
        )

        docs: List[DiscoveredDoc] = []
        for r in records:
            doc_type, priority = self.classifier.classify(r.path, "")
            if priority == DocPriority.EXCLUDE:
                continue
            docs.append(
                DiscoveredDoc(
                    path=r.path,
                    filename=os.path.basename(r.path),
                    doc_type=doc_type,
                    priority=priority,
                    raw_size=r.size or 0,
                    line_count=0,
                    headings=[],
                    content="",
                    token_estimate=0,
                )
            )

        docs.sort(key=lambda d: (-d.priority.value, d.path))
        return docs
