"""
Deterministic Fallback Generator - Emits a high-density, evidence-backed Markdown summary
directly from verified RepositoryClaim and DeployableUnit records when LLM synthesis is unavailable.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from .schemas import (
    DeployableUnit,
    RepositoryClaim,
    VerificationStatus,
)


def generate_deterministic_fallback(
    repo_name: str,
    deployable_units: List[DeployableUnit],
    verified_claims: List[RepositoryClaim],
    metrics: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Produces an authoritative, fact-grounded Markdown summary strictly from verified facts.
    Does not invent qualitative assertions or unsupported architectural claims.
    """
    metrics = metrics or {}
    sections = []

    # 1. Title & Overview
    sections.append(f"# {repo_name} — Repository Summary (Deterministic Verification)")
    
    total_files = metrics.get("total_files", "Unknown")
    lines_of_code = metrics.get("lines_of_code", "Unknown")
    
    sections.append(
        f"## 1. Overview & Scale\n"
        f"- **Repository**: {repo_name}\n"
        f"- **Scale**: {total_files} tracked files, {lines_of_code} lines of code.\n"
        f"- **Analysis Mode**: Deterministic static analysis and dependency verification."
    )

    # 2. Deployable Units
    if deployable_units:
        unit_lines = ["## 2. Deployable Units & Projects"]
        for u in deployable_units:
            ep_str = ", ".join(f"{e}" for e in u.entrypoints) if u.entrypoints else "None specified"
            unit_lines.append(
                f"- **{u.name}** ({(u.unit_type.value if hasattr(u.unit_type, 'value') else u.unit_type)})\n"
                f"  - Root Path: {u.root_path}\n"
                f"  - Entrypoints: {ep_str}"
            )
        sections.append("\n".join(unit_lines))

    # 3. Verified Technology Stack
    strongly_supported = [c for c in verified_claims if c.status == VerificationStatus.STRONGLY_SUPPORTED]
    supported = [c for c in verified_claims if c.status == VerificationStatus.SUPPORTED]
    declared_unused = [c for c in verified_claims if c.status == VerificationStatus.DECLARED_UNUSED]

    tech_lines = ["## 3. Technology Stack & Dependencies"]
    if strongly_supported:
        tech_lines.append("### Active Application Technologies")
        for c in strongly_supported:
            tech_lines.append(f"- **{c.subject}**: Active application usage verified.")
    if supported:
        tech_lines.append("### Configured & Supporting Technologies")
        for c in supported:
            tech_lines.append(f"- **{c.subject}**: Configured or referenced.")
    if declared_unused:
        tech_lines.append("### Declared but Unused Dependencies")
        for c in declared_unused:
            tech_lines.append(f"- **{c.subject}**: Present in manifest but no active application usage detected.")
    
    sections.append("\n".join(tech_lines))

    # 4. Discrepancies & Unverified Claims
    contradicted = [c for c in verified_claims if c.status == VerificationStatus.CONTRADICTED]
    doc_unverified = [c for c in verified_claims if c.status == VerificationStatus.DOCUMENTED_UNVERIFIED]

    if contradicted or doc_unverified:
        disc_lines = ["## 4. Discrepancies & Documented Claims"]
        if contradicted:
            disc_lines.append("### Positive Code Discrepancies")
            for c in contradicted:
                disc_lines.append(f"- **{c.subject}**: Documented in project materials, but positive conflicting code evidence exists.")
        if doc_unverified:
            disc_lines.append("### Unverified Documented Features")
            for c in doc_unverified:
                disc_lines.append(f"- **{c.subject}**: Documented in project materials but not directly detected in static codebase scan.")
        sections.append("\n".join(disc_lines))

    return "\n\n".join(sections)
