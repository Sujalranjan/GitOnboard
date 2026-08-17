"""
Task-Specific Retrieval Engine - Assembles extensible, dual-path Context Packs
(Structured Code Evidence + Structural Doc Chunks) mapped to explicit evidence_ids.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .schemas import (
    DeployableUnit,
    EvidenceItem,
    EvidenceSourceType,
    RepositoryClaim,
    SourceClassification,
    VerificationStatus,
)
from .chunker import DocChunk


class ContextPack(BaseModel):
    task_name: str
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    doc_chunks: List[DocChunk] = Field(default_factory=list)
    summary_facts: Dict[str, Any] = Field(default_factory=dict)


class AdaptiveContextBundle(BaseModel):
    identity_pack: ContextPack
    architecture_pack: ContextPack
    api_surface_pack: ContextPack
    data_ops_pack: ContextPack
    claims_discrepancies_pack: ContextPack

    def build_llm_prompt_context(self) -> str:
        sections = []

        # 1. Identity & Tech Stack Pack
        id_lines = ["=== 1. IDENTITY & TECH STACK EVIDENCE ==="]
        for ev in self.identity_pack.evidence_items:
            id_lines.append(f"[{ev.evidence_id}] ({ev.source_type.value} in {ev.file_path}): {ev.snippet}")
        for chunk in self.identity_pack.doc_chunks:
            id_lines.append(f"[DOC: {chunk.file_path}#{chunk.heading}]\n{chunk.text}\n")
        sections.append("\n".join(id_lines))

        # 2. Architecture & Deployable Units Pack
        arch_lines = ["=== 2. ARCHITECTURE & DEPLOYABLE UNITS ==="]
        for u in self.architecture_pack.summary_facts.get("units", []):
            arch_lines.append(f"- Unit: {u.get('name')} (Type: {u.get('type')}, Path: {u.get('path')}, Entrypoints: {u.get('entrypoints')})")
        for ev in self.architecture_pack.evidence_items:
            arch_lines.append(f"[{ev.evidence_id}] ({ev.file_path}): {ev.snippet}")
        for chunk in self.architecture_pack.doc_chunks:
            arch_lines.append(f"[DOC: {chunk.file_path}#{chunk.heading}]\n{chunk.text}\n")
        sections.append("\n".join(arch_lines))

        # 3. API Surface Pack
        api_lines = ["=== 3. API SURFACE & CAPABILITIES ==="]
        for ev in self.api_surface_pack.evidence_items:
            api_lines.append(f"[{ev.evidence_id}] ({ev.file_path}): {ev.snippet}")
        for chunk in self.api_surface_pack.doc_chunks:
            api_lines.append(f"[DOC: {chunk.file_path}#{chunk.heading}]\n{chunk.text}\n")
        sections.append("\n".join(api_lines))

        # 4. Data Layer & Operations Pack
        ops_lines = ["=== 4. DATA & OPERATIONS EVIDENCE ==="]
        for ev in self.data_ops_pack.evidence_items:
            ops_lines.append(f"[{ev.evidence_id}] ({ev.file_path}): {ev.snippet}")
        for chunk in self.data_ops_pack.doc_chunks:
            ops_lines.append(f"[DOC: {chunk.file_path}#{chunk.heading}]\n{chunk.text}\n")
        sections.append("\n".join(ops_lines))

        # 5. Verified Claims & Discrepancies Pack
        claim_lines = ["=== 5. VERIFIED CLAIMS & DISCREPANCIES ==="]
        for c in self.claims_discrepancies_pack.summary_facts.get("claims", []):
            claim_lines.append(f"- Claim: {c.get('subject')} | Status: {c.get('status')} | Reasoning: {c.get('reasoning')} | Evidence: {c.get('evidence_ids')}")
        sections.append("\n".join(claim_lines))

        return "\n\n".join(sections)


class TaskSpecificRetriever:
    """
    Assembles dual-path context packs based on domain policies.
    """

    @staticmethod
    def assemble_bundle(
        evidence_items: List[EvidenceItem],
        doc_chunks: List[DocChunk],
        deployable_units: List[DeployableUnit],
        verified_claims: List[RepositoryClaim],
        metrics: Optional[Dict[str, Any]] = None,
    ) -> AdaptiveContextBundle:
        metrics = metrics or {}

        # 1. Identity Pack
        identity_ev = [
            ev for ev in evidence_items
            if ev.source_type == EvidenceSourceType.MANIFEST_DEPENDENCY
        ][:20]
        identity_chunks = [
            c for c in doc_chunks
            if c.domain == "overview" or c.heading.lower() in {"(top level)", "overview", "about"}
        ][:3]

        # 2. Architecture Pack
        arch_ev = [
            ev for ev in evidence_items
            if ev.source_classification == SourceClassification.APPLICATION
            and ev.source_type in {EvidenceSourceType.AST_DEFINITION, EvidenceSourceType.IMPORT_STATEMENT}
        ][:15]
        arch_chunks = [c for c in doc_chunks if c.domain == "architecture"][:3]
        unit_dicts = [
            {"name": u.name, "type": (u.unit_type.value if hasattr(u.unit_type, 'value') else u.unit_type), "path": u.root_path, "entrypoints": u.entrypoints}
            for u in deployable_units
        ]

        # 3. API Surface Pack
        api_ev = [
            ev for ev in evidence_items
            if ev.source_type == EvidenceSourceType.ROUTE_DECLARATION
        ][:20]
        api_chunks = [c for c in doc_chunks if c.domain == "api"][:3]

        # 4. Data & Operations Pack
        ops_ev = [
            ev for ev in evidence_items
            if ev.source_type in {EvidenceSourceType.CONFIG_ENTRY, EvidenceSourceType.DB_MODEL_SCHEMA}
        ][:20]
        ops_chunks = [c for c in doc_chunks if c.domain == "deployment"][:3]

        # 5. Claims & Discrepancies Pack
        claim_dicts = [
            {"subject": c.subject, "status": c.status.value, "reasoning": c.verification_reasoning, "evidence_ids": (c.supporting_evidence_ids or c.evidence_ids)}
            for c in verified_claims
        ]

        return AdaptiveContextBundle(
            identity_pack=ContextPack(
                task_name="identity",
                evidence_items=identity_ev,
                doc_chunks=identity_chunks,
                summary_facts={"metrics": metrics},
            ),
            architecture_pack=ContextPack(
                task_name="architecture",
                evidence_items=arch_ev,
                doc_chunks=arch_chunks,
                summary_facts={"units": unit_dicts},
            ),
            api_surface_pack=ContextPack(
                task_name="api_surface",
                evidence_items=api_ev,
                doc_chunks=api_chunks,
            ),
            data_ops_pack=ContextPack(
                task_name="data_ops",
                evidence_items=ops_ev,
                doc_chunks=ops_chunks,
            ),
            claims_discrepancies_pack=ContextPack(
                task_name="claims_discrepancies",
                summary_facts={"claims": claim_dicts},
            ),
        )
