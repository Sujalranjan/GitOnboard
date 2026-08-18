"""
Phase 3 Atomic Claim Extractor - Deterministically extracts independently verifiable
atomic factual claims from raw Writer output (both structured JSON and Markdown sections).
NO secondary LLM is used.
"""
from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional

from .schemas import AtomicClaim, ClaimType, SupportStatus


class AtomicClaimExtractor:
    """
    Deterministically transforms Writer output into a list of AtomicClaims.
    """

    @classmethod
    def extract_claims(
        cls,
        raw_writer_output: Any,
        repo_id: str,
    ) -> List[AtomicClaim]:
        claims: List[AtomicClaim] = []
        claim_counter = 0

        def next_claim_id() -> str:
            nonlocal claim_counter
            claim_counter += 1
            return f"{repo_id}_C{claim_counter:03d}"

        # 1. Handle Structured Dictionary / JSON payload
        parsed_dict = None
        if isinstance(raw_writer_output, dict):
            parsed_dict = raw_writer_output
        elif isinstance(raw_writer_output, str):
            trimmed = raw_writer_output.strip()
            if trimmed.startswith("{") and trimmed.endswith("}"):
                try:
                    parsed_dict = json.loads(trimmed)
                except Exception:
                    parsed_dict = None

        if parsed_dict:
            # Overview sentences
            overview = parsed_dict.get("overview", {})
            ov_text = overview.get("text", "") if isinstance(overview, dict) else str(overview)
            ov_citations = overview.get("evidence_ids", []) if isinstance(overview, dict) else []
            if ov_text:
                for sent in cls._split_into_sentences(ov_text):
                    claims.append(
                        AtomicClaim(
                            claim_id=next_claim_id(),
                            repository=repo_id,
                            text=sent,
                            claim_type=cls._infer_sentence_type(sent),
                            citations=list(ov_citations),
                            support_status=SupportStatus.UNRESOLVED,
                        )
                    )

            # Deployable Units
            for unit in parsed_dict.get("deployable_units", []):
                if isinstance(unit, dict):
                    u_name = unit.get("name", "UnknownUnit")
                    u_path = unit.get("root_path", "/")
                    u_type = unit.get("unit_type", "service")
                    u_cites = unit.get("evidence_ids", [])
                    u_sum = unit.get("summary", "")

                    # Path assertion
                    claims.append(
                        AtomicClaim(
                            claim_id=next_claim_id(),
                            repository=repo_id,
                            text=f"Deployable unit '{u_name}' exists at root path '{u_path}'.",
                            claim_type=ClaimType.PATH,
                            citations=list(u_cites),
                            support_status=SupportStatus.UNRESOLVED,
                        )
                    )
                    # Unit type assertion
                    claims.append(
                        AtomicClaim(
                            claim_id=next_claim_id(),
                            repository=repo_id,
                            text=f"Unit '{u_name}' is categorized as '{u_type}'.",
                            claim_type=ClaimType.ARCHITECTURE,
                            citations=list(u_cites),
                            support_status=SupportStatus.UNRESOLVED,
                        )
                    )
                    if u_sum:
                        claims.append(
                            AtomicClaim(
                                claim_id=next_claim_id(),
                                repository=repo_id,
                                text=f"Unit '{u_name}' role: {u_sum}",
                                claim_type=ClaimType.BEHAVIOR,
                                citations=list(u_cites),
                                support_status=SupportStatus.UNRESOLVED,
                            )
                        )

            # Technologies
            for tech in parsed_dict.get("technologies", []):
                if isinstance(tech, dict):
                    t_name = tech.get("name", "")
                    t_cat = tech.get("category", "Framework")
                    t_status = tech.get("status", "supported")
                    t_cites = tech.get("evidence_ids", [])

                    claims.append(
                        AtomicClaim(
                            claim_id=next_claim_id(),
                            repository=repo_id,
                            text=f"The project uses {t_name} ({t_cat}). Status: {t_status}.",
                            claim_type=ClaimType.TECHNOLOGY,
                            citations=list(t_cites),
                            support_status=SupportStatus.UNRESOLVED,
                        )
                    )

            # Data & Storage
            data_storage = parsed_dict.get("data_and_storage", {})
            if isinstance(data_storage, dict):
                db_cites = data_storage.get("evidence_ids", [])
                for db in data_storage.get("databases", []):
                    claims.append(
                        AtomicClaim(
                            claim_id=next_claim_id(),
                            repository=repo_id,
                            text=f"The project uses database '{db}'.",
                            claim_type=ClaimType.DATABASE,
                            citations=list(db_cites),
                            support_status=SupportStatus.UNRESOLVED,
                        )
                    )

            # Operations & Deployment
            ops = parsed_dict.get("operations_and_deployment", {})
            if isinstance(ops, dict):
                ops_cites = ops.get("evidence_ids", [])
                for k, v in ops.items():
                    if k != "evidence_ids" and v:
                        claims.append(
                            AtomicClaim(
                                claim_id=next_claim_id(),
                                repository=repo_id,
                                text=f"Deployment configuration '{k}': {v}",
                                claim_type=ClaimType.DEPLOYMENT,
                                citations=list(ops_cites),
                                support_status=SupportStatus.UNRESOLVED,
                            )
                        )

            # Discrepancies / Contradictions
            for disc in parsed_dict.get("discrepancies", []):
                if isinstance(disc, dict):
                    claimed = disc.get("claimed_in_doc", "")
                    actual = disc.get("actual_code_fact", "")
                    d_cites = disc.get("evidence_ids", [])
                    claims.append(
                        AtomicClaim(
                            claim_id=next_claim_id(),
                            repository=repo_id,
                            text=f"Documentation claims '{claimed}', but actual code exhibits '{actual}'.",
                            claim_type=ClaimType.CONTRADICTION,
                            citations=list(d_cites),
                            support_status=SupportStatus.UNRESOLVED,
                        )
                    )

            # Unverified Doc Claims
            for unv in parsed_dict.get("unverified_doc_claims", []):
                if isinstance(unv, dict):
                    u_claim = unv.get("claim", "")
                    u_eid = unv.get("doc_evidence_id", "")
                    u_reason = unv.get("reason", "")
                    claims.append(
                        AtomicClaim(
                            claim_id=next_claim_id(),
                            repository=repo_id,
                            text=f"Unverified doc claim: '{u_claim}' ({u_reason})",
                            claim_type=ClaimType.OTHER,
                            citations=[u_eid] if u_eid else [],
                            support_status=SupportStatus.UNRESOLVED,
                        )
                    )

        # 2. Handle Raw Markdown Text
        if not claims and isinstance(raw_writer_output, str):
            lines = raw_writer_output.splitlines()
            current_section = "GENERAL"
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.startswith("#"):
                    current_section = line_str.lstrip("#").strip()
                    continue
                
                # Check for list items or plain text lines
                if line_str.startswith(("-", "*", "•", "1.", "2.", "3.", "4.", "5.")):
                    cleaned = re.sub(r'^[-*•\d.]+\s*', '', line_str)
                    if cleaned:
                        claims.append(
                            AtomicClaim(
                                claim_id=next_claim_id(),
                                repository=repo_id,
                                text=cleaned,
                                claim_type=cls._infer_type_from_section_and_text(current_section, cleaned),
                                citations=cls._extract_citations_from_text(cleaned),
                                support_status=SupportStatus.UNRESOLVED,
                            )
                        )
                else:
                    for sent in cls._split_into_sentences(line_str):
                        claims.append(
                            AtomicClaim(
                                claim_id=next_claim_id(),
                                repository=repo_id,
                                text=sent,
                                claim_type=cls._infer_type_from_section_and_text(current_section, sent),
                                citations=cls._extract_citations_from_text(sent),
                                support_status=SupportStatus.UNRESOLVED,
                            )
                        )

        return claims

    @staticmethod
    def _split_into_sentences(text: str) -> List[str]:
        # Split on period, exclamation, or question mark followed by space or newline
        splits = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in splits if s.strip() and len(s.strip()) > 5]

    @staticmethod
    def _infer_sentence_type(sentence: str) -> ClaimType:
        lower = sentence.lower()
        if any(w in lower for w in ["uses", "framework", "written in", "language", "built with", "fastapi", "flask", "django", "express", "react", "next.js", "spring", "rails"]):
            return ClaimType.TECHNOLOGY
        if any(w in lower for w in ["database", "postgres", "mysql", "sqlite", "mongo", "redis"]):
            return ClaimType.DATABASE
        if any(w in lower for w in ["docker", "compose", "deploy", "kubernetes", "k8s", "port"]):
            return ClaimType.DEPLOYMENT
        if any(w in lower for w in ["endpoint", "/api/", "route", "http get", "http post"]):
            return ClaimType.API
        if any(w in lower for w in ["contradict", "discrepancy", "mismatch", "conflict"]):
            return ClaimType.CONTRADICTION
        if any(w in lower for w in ["file", "path", "directory", "folder", ".py", ".ts", ".js", ".go", ".java"]):
            return ClaimType.FILE
        return ClaimType.OTHER

    @staticmethod
    def _infer_type_from_section_and_text(section: str, text: str) -> ClaimType:
        sec_lower = section.lower()
        if "tech" in sec_lower or "stack" in sec_lower:
            return ClaimType.TECHNOLOGY
        if "discrepanc" in sec_lower or "contradict" in sec_lower or "note" in sec_lower:
            return ClaimType.CONTRADICTION
        if "data" in sec_lower or "storage" in sec_lower:
            return ClaimType.DATABASE
        if "component" in sec_lower or "architecture" in sec_lower:
            return ClaimType.ARCHITECTURE
        if "operational" in sec_lower or "deploy" in sec_lower or "docker" in sec_lower:
            return ClaimType.DEPLOYMENT
        return AtomicClaimExtractor._infer_sentence_type(text)

    @staticmethod
    def _extract_citations_from_text(text: str) -> List[str]:
        return re.findall(r'\b(ev_[a-zA-Z0-9_-]+|EVID-[a-zA-Z0-9_-]+)\b', text)
