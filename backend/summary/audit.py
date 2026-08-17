"""
Verbose Audit Logging Engine for Repository Summary Pipeline.
Configured via SUMMARY_VERBOSE_AUDIT environment variable (default: False).
When enabled, captures full provenance artifacts with automated secret redaction.
"""
from __future__ import annotations
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

SECRET_RULES = [
    (re.compile(r'(?i)(password|secret|token|key|api_key|jwt|auth)\s*[:=]\s*["\']?([^"\'\s,;]+)["\']?'), r'\1: [REDACTED]'),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), '[REDACTED_GITHUB_TOKEN]'),
    (re.compile(r'github_pat_[a-zA-Z0-9_]{82}'), '[REDACTED_GITHUB_PAT]'),
    (re.compile(r'ey[a-zA-Z0-9_\-]{20,}\.ey[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}'), '[REDACTED_JWT]'),
    (re.compile(r'Bearer\s+[a-zA-Z0-9_\-\.]+'), 'Bearer [REDACTED_TOKEN]'),
]


def redact_secrets(text: str) -> str:
    if not isinstance(text, str):
        return text
    sanitized = text
    for pattern, repl in SECRET_RULES:
        sanitized = pattern.sub(repl, sanitized)
    return sanitized


def sanitize_dict_or_list(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: sanitize_dict_or_list(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_dict_or_list(item) for item in data]
    elif isinstance(data, str):
        return redact_secrets(data)
    return data


class SummaryAuditCollector:
    """
    Collects full end-to-end telemetry across all summary pipeline stages.
    """

    def __init__(self, run_id: Optional[str] = None, base_dir: str = "evaluation/runs"):
        self.run_id = run_id or f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        self.base_dir = Path(base_dir)
        self.start_time = time.time()
        
        self.metadata: Dict[str, Any] = {}
        self.evidence_index: List[Dict[str, Any]] = []
        self.hierarchy: List[Dict[str, Any]] = []
        self.retrieval_decisions: Dict[str, Any] = {}
        self.context_sent_to_llm: str = ""
        self.llm_request: Dict[str, Any] = {}
        self.llm_response: Dict[str, Any] = {}
        self.validation_results: Dict[str, Any] = {}
        self.rejected_claims: List[Dict[str, Any]] = []
        self.final_summary_md: str = ""

    def persist_run_artifacts(self) -> Path:
        run_path = self.base_dir / self.run_id
        run_path.mkdir(parents=True, exist_ok=True)

        files_to_write = {
            "01_repository_metadata.json": sanitize_dict_or_list(self.metadata),
            "02_evidence_index.json": sanitize_dict_or_list(self.evidence_index),
            "03_hierarchy.json": sanitize_dict_or_list(self.hierarchy),
            "04_retrieval_decisions.json": sanitize_dict_or_list(self.retrieval_decisions),
            "05_context_sent_to_llm.json": {"raw_prompt_context": redact_secrets(self.context_sent_to_llm)},
            "06_llm_request.json": sanitize_dict_or_list(self.llm_request),
            "07_llm_response.json": sanitize_dict_or_list(self.llm_response),
            "08_validation_results.json": sanitize_dict_or_list(self.validation_results),
            "09_rejected_claims.json": sanitize_dict_or_list(self.rejected_claims),
            "10_final_summary.md": redact_secrets(self.final_summary_md),
            "11_audit_report.json": sanitize_dict_or_list(self.generate_coverage_report()),
        }

        for filename, content in files_to_write.items():
            full_file = run_path / filename
            if filename.endswith(".json"):
                with open(full_file, "w", encoding="utf-8") as f:
                    json.dump(content, f, indent=2)
            else:
                with open(full_file, "w", encoding="utf-8") as f:
                    f.write(content)

        logger.info(f"Summary audit artifacts persisted to {run_path}")
        return run_path

    def generate_coverage_report(self) -> Dict[str, Any]:
        total_ev = len(self.evidence_index)
        selected_ev = self.retrieval_decisions.get("selected_evidence_count", 0)
        unselected_ev = max(0, total_ev - selected_ev)

        return {
            "run_id": self.run_id,
            "duration_seconds": round(time.time() - self.start_time, 3),
            "evidence_coverage": {
                "total_evidence_created": total_ev,
                "evidence_selected_for_llm": selected_ev,
                "evidence_omitted": unselected_ev,
            },
            "architecture_coverage": {
                "deployable_units_discovered": len(self.hierarchy),
                "deployable_units_supplied": self.retrieval_decisions.get("supplied_units_count", 0),
            },
            "validation_metrics": {
                "accepted_claims": self.validation_results.get("accepted_claims_count", 0),
                "rejected_claims": len(self.rejected_claims),
                "fabricated_paths_detected": self.validation_results.get("fabricated_paths_count", 0),
                "false_contradictions_rejected": self.validation_results.get("false_contradictions_rejected_count", 0),
            }
        }
