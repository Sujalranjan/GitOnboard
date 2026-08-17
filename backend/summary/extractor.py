"""
Deterministic Evidence Extractor & Source Classifier - Extracts normalized,
atomic EvidenceItem records from package manifests, container configs, AST models, source routes, and doc chunks.
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .schemas import (
    EvidenceItem,
    EvidenceSourceType,
    SourceClassification,
)


class EvidenceExtractor:
    """
    Extracts deterministic evidence items across repository assets and assigns stable evidence IDs.
    """

    def __init__(self):
        self.evidence_counter = 0

    def _next_id(self) -> str:
        self.evidence_counter += 1
        return f"ev_{self.evidence_counter:04d}"

    @staticmethod
    def classify_source(file_path: str) -> SourceClassification:
        p = file_path.replace("\\", "/").lower().strip()
        fname = os.path.basename(p)

        # Vendored / Dependencies
        if any(v in p for v in ["node_modules/", "vendor/", ".venv/", "venv/", "site-packages/"]):
            return SourceClassification.VENDORED

        # Generated Code
        if any(g in p for g in ["generated/", "/pb/", "_pb2.py", ".min.js", "dist/", "build/", ".output/", ".next/", ".turbo/", ".cache/"]):
            return SourceClassification.GENERATED

        # Tests & Fixtures
        if (
            any(t in p for t in ["tests/", "test/", "__tests__/", "fixtures/", "mocks/"])
            or fname.startswith("test_")
            or fname.endswith("_test.py")
            or fname.endswith(".test.ts")
            or fname.endswith(".spec.ts")
            or fname.endswith(".test.js")
            or fname.endswith(".spec.js")
        ):
            return SourceClassification.TEST

        # Examples & Demos & Docs source
        if any(e in p for e in ["examples/", "samples/", "demo/", "tutorials/", "docs_src/"]):
            return SourceClassification.EXAMPLE

        # Documentation
        if any(fname.endswith(ext) for ext in [".md", ".markdown", ".rst", ".mmd", ".txt"]) and not fname.startswith("requirements"):
            return SourceClassification.DOCUMENTATION

        # Configuration & Manifests
        if fname in {
            "pyproject.toml", "package.json", "cargo.toml", "go.mod", "requirements.txt",
            "docker-compose.yml", "docker-compose.yaml", "dockerfile", ".env", ".env.example",
            "alembic.ini", "tsconfig.json", "next.config.js", "vite.config.ts"
        } or fname.startswith("docker-compose") or fname.startswith("dockerfile"):
            return SourceClassification.CONFIGURATION

        return SourceClassification.APPLICATION

    def extract_from_manifests(self, file_path: str, content: str) -> List[EvidenceItem]:
        items: List[EvidenceItem] = []
        fname = os.path.basename(file_path).lower()
        classification = self.classify_source(file_path)

        if fname == "pyproject.toml":
            in_deps = False
            for line_no, line in enumerate(content.splitlines(), start=1):
                clean = line.strip()
                if "dependencies" in clean and "=" in clean:
                    in_deps = True
                if in_deps:
                    match = re.search(r'["\']([a-zA-Z0-9_\-]+)', clean)
                    if match:
                        dep_name = match.group(1)
                        if dep_name not in {"project", "tool", "dependencies", "optional-dependencies"}:
                            items.append(
                                EvidenceItem(
                                    evidence_id=self._next_id(),
                                    source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
                                    source_classification=classification,
                                    file_path=file_path,
                                    line_start=line_no,
                                    line_end=line_no,
                                    snippet=clean,
                                    symbol_name=dep_name,
                                    context_metadata={"ecosystem": "pypi", "dependency": dep_name}
                                )
                            )
                if in_deps and clean.endswith("]"):
                    in_deps = False

        elif fname == "requirements.txt":
            for line_no, line in enumerate(content.splitlines(), start=1):
                clean = line.strip()
                if clean and not clean.startswith("#"):
                    match = re.match(r'^([a-zA-Z0-9_\-]+)', clean)
                    if match:
                        dep_name = match.group(1)
                        items.append(
                            EvidenceItem(
                                evidence_id=self._next_id(),
                                source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
                                source_classification=classification,
                                file_path=file_path,
                                line_start=line_no,
                                line_end=line_no,
                                snippet=clean,
                                symbol_name=dep_name,
                                context_metadata={"ecosystem": "pypi", "dependency": dep_name}
                            )
                        )

        elif fname == "package.json":
            try:
                data = json.loads(content)
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                for dep_name, version in deps.items():
                    items.append(
                        EvidenceItem(
                            evidence_id=self._next_id(),
                            source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
                            source_classification=classification,
                            file_path=file_path,
                            snippet=f'"{dep_name}": "{version}"',
                            symbol_name=dep_name,
                            context_metadata={"ecosystem": "npm", "dependency": dep_name, "version": version}
                        )
                    )
            except Exception:
                pass

        elif fname == "cargo.toml":
            in_deps = False
            for line_no, line in enumerate(content.splitlines(), start=1):
                clean = line.strip()
                if clean == "[dependencies]":
                    in_deps = True
                    continue
                elif clean.startswith("[") and clean.endswith("]"):
                    in_deps = False
                if in_deps and "=" in clean:
                    parts = clean.split("=")
                    dep_name = parts[0].strip().strip('"').strip("'")
                    items.append(
                        EvidenceItem(
                            evidence_id=self._next_id(),
                            source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
                            source_classification=classification,
                            file_path=file_path,
                            line_start=line_no,
                            line_end=line_no,
                            snippet=clean,
                            symbol_name=dep_name,
                            context_metadata={"ecosystem": "cargo", "dependency": dep_name}
                        )
                    )

        elif fname == "go.mod":
            in_req = False
            for line_no, line in enumerate(content.splitlines(), start=1):
                clean = line.strip()
                if clean.startswith("require ("):
                    in_req = True
                    continue
                elif clean.startswith("require "):
                    parts = clean.split()
                    if len(parts) >= 2:
                        dep_name = parts[1]
                        items.append(
                            EvidenceItem(
                                evidence_id=self._next_id(),
                                source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
                                source_classification=classification,
                                file_path=file_path,
                                line_start=line_no,
                                line_end=line_no,
                                snippet=clean,
                                symbol_name=dep_name,
                                context_metadata={"ecosystem": "go", "dependency": dep_name}
                            )
                        )
                elif in_req:
                    if clean == ")":
                        in_req = False
                    elif clean and not clean.startswith("//"):
                        parts = clean.split()
                        dep_name = parts[0]
                        items.append(
                            EvidenceItem(
                                evidence_id=self._next_id(),
                                source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
                                source_classification=classification,
                                file_path=file_path,
                                line_start=line_no,
                                line_end=line_no,
                                snippet=clean,
                                symbol_name=dep_name,
                                context_metadata={"ecosystem": "go", "dependency": dep_name}
                            )
                        )

        return items

    def extract_from_compose(self, file_path: str, content: str) -> List[EvidenceItem]:
        items: List[EvidenceItem] = []
        classification = self.classify_source(file_path)
        
        current_service = None
        for line_no, line in enumerate(content.splitlines(), start=1):
            clean = line.strip()
            svc_match = re.match(r'^([a-zA-Z0-9_\-]+):$', clean)
            if svc_match and line.startswith("  ") and not line.startswith("    "):
                current_service = svc_match.group(1)
            img_match = re.match(r'^image:\s*([a-zA-Z0-9_\-\./:]+)', clean)
            if img_match and current_service:
                image_name = img_match.group(1)
                items.append(
                    EvidenceItem(
                        evidence_id=self._next_id(),
                        source_type=EvidenceSourceType.CONFIG_ENTRY,
                        source_classification=classification,
                        file_path=file_path,
                        line_start=line_no,
                        line_end=line_no,
                        snippet=clean,
                        symbol_name=current_service,
                        context_metadata={"service": current_service, "image": image_name}
                    )
                )
        return items

    def extract_routes_from_source(self, file_path: str, content: str) -> List[EvidenceItem]:
        """
        Extracts API route declarations with exact file paths and line ranges.
        Deduplicates identical (method, path) declarations within the same file.
        """
        items: List[EvidenceItem] = []
        classification = self.classify_source(file_path)
        seen_in_file: Set[Tuple[str, str, int]] = set()

        # Python route patterns: @app.get('/...'), @router.post('/...')
        py_route_pat = re.compile(r'@(?:app|router|api_router|v1_router)\.(get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']')
        
        # JS/TS route patterns: app.get('/...'), router.post('/...')
        js_route_pat = re.compile(r'(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']')

        for line_no, line in enumerate(content.splitlines(), start=1):
            clean = line.strip()
            
            # Python
            m_py = py_route_pat.search(clean)
            if m_py:
                method = m_py.group(1).upper()
                route_path = m_py.group(2)
                key = (method, route_path, line_no)
                if key not in seen_in_file:
                    seen_in_file.add(key)
                    items.append(
                        EvidenceItem(
                            evidence_id=self._next_id(),
                            source_type=EvidenceSourceType.ROUTE_DECLARATION,
                            source_classification=classification,
                            file_path=file_path,
                            line_start=line_no,
                            line_end=line_no,
                            snippet=f"{method} {route_path}",
                            symbol_name=route_path,
                            context_metadata={"method": method, "path": route_path}
                        )
                    )

            # JS/TS
            m_js = js_route_pat.search(clean)
            if m_js and not clean.startswith("//") and not clean.startswith("*"):
                method = m_js.group(1).upper()
                route_path = m_js.group(2)
                key = (method, route_path, line_no)
                if key not in seen_in_file:
                    seen_in_file.add(key)
                    items.append(
                        EvidenceItem(
                            evidence_id=self._next_id(),
                            source_type=EvidenceSourceType.ROUTE_DECLARATION,
                            source_classification=classification,
                            file_path=file_path,
                            line_start=line_no,
                            line_end=line_no,
                            snippet=f"{method} {route_path}",
                            symbol_name=route_path,
                            context_metadata={"method": method, "path": route_path}
                        )
                    )

        return items
