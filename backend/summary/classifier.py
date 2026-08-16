"""
Documentation Classifier - Deterministically classifies documentation into trust tiers.
"""
from __future__ import annotations
import os
from typing import Tuple
from .schemas import DocType, DocPriority


class DocClassifier:
    """
    Classifies repository documentation by importance and purpose.
    Ensures agent/tool instructions (AGENTS.md, CLAUDE.md, skill.md) are strictly
    segregated and never outrank primary software documentation.
    """

    def classify(self, path: str, content_preview: str = "") -> Tuple[DocType, DocPriority]:
        p = path.replace("\\", "/").strip().lower()
        fname = os.path.basename(p)

        # 0. Exclude vendored / generated / changelogs / licenses if unwanted
        if any(ign in p for ign in ["node_modules/", "vendor/", "dist/", "build/", "site-packages/"]):
            return DocType.GENERIC_DOCS, DocPriority.EXCLUDE

        # 1. Agent / Tool Instruction Files (Separate Trust Class - Lower Priority)
        if (
            fname in {"agents.md", "claude.md", "agent.md", "skill.md", "prompt.md", "copilot-instructions.md"}
            or "copilot-instructions" in fname
            or ".cursor/" in p
            or ".agents/" in p
            or ".github/copilot-instructions" in p
            or "customizations/skills" in p
        ):
            return DocType.AGENT_INSTRUCTIONS, DocPriority.AGENT_CONTEXT

        # 2. Primary README (Highest Priority)
        if fname in {"readme.md", "readme.markdown", "readme.rst", "readme"}:
            # Root or near-root README
            if p.count("/") <= 1:
                return DocType.PRIMARY_README, DocPriority.HIGHEST
            return DocType.PRIMARY_README, DocPriority.HIGH

        # 3. Architecture & System Design Documentation (Highest Priority)
        if (
            fname in {"architecture.md", "design.md", "system_design.md", "architecture.markdown"}
            or p.startswith("docs/architecture")
            or p.startswith("docs/design")
            or "/architecture" in p
            or "/design" in p
        ):
            return DocType.ARCHITECTURE, DocPriority.HIGHEST

        # 4. Contributing & Repository Guidelines (High Priority)
        if fname in {"contributing.md", "contributing.markdown", "governance.md"}:
            return DocType.CONTRIBUTING, DocPriority.HIGH

        # 5. Core Product / System Documentation in docs/ (High Priority)
        if p.startswith("docs/") or p.startswith("doc/"):
            if any(sub in p for sub in ["api", "endpoints", "swagger", "openapi"]):
                return DocType.API_DOCS, DocPriority.MEDIUM
            if any(sub in p for sub in ["guide", "tutorial", "howto", "setup", "getting_started"]):
                return DocType.GUIDES_TUTORIALS, DocPriority.MEDIUM
            if p.endswith(".mmd"):
                return DocType.DIAGRAMS, DocPriority.MEDIUM
            return DocType.PRODUCT_SYSTEM_DOCS, DocPriority.HIGH

        # 6. API Documentation (Medium Priority)
        if fname in {"api.md", "api_reference.md", "endpoints.md", "routes.md"}:
            return DocType.API_DOCS, DocPriority.MEDIUM

        # 7. Guides, Development, and Testing (Medium Priority)
        if fname in {"development.md", "testing.md", "setup.md", "install.md", "deployment.md", "decisions.md"}:
            return DocType.GUIDES_TUTORIALS, DocPriority.MEDIUM

        # 8. Diagrams (.mmd Mermaid files) (Medium Priority)
        if p.endswith(".mmd"):
            return DocType.DIAGRAMS, DocPriority.MEDIUM

        # 9. Generic / Other Documentation (Low Priority)
        return DocType.GENERIC_DOCS, DocPriority.LOW
