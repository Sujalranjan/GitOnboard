"""
Summary Generator - Synthesizes grounded repository summaries via LLMService.
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional

from backend.ai.service import LLMService
from backend.ai.schemas import LLMRequest, Message, MessageRole
from .schemas import BudgetedDocContext

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert software architect and technical documentation writer.
Your task is to produce a grounded, comprehensive, high-integrity Markdown repository summary.

EVIDENCE TRUST HIERARCHY:
1. [VERIFIED CODE EVIDENCE] (Static analysis, language profiles, detected routes, functions, entrypoints) is the HIGHEST ground truth.
2. [PRIMARY DOCUMENTATION] (README.md, ARCHITECTURE.md, core docs) describes official design and product intent.
3. [SUPPORTING DOCUMENTATION] (API references, guides, diagrams) provides operational context.
4. [AGENT / TOOL INSTRUCTIONS] (AGENTS.md, CLAUDE.md, skill.md) are contextual developer tool instructions ONLY.
   CRITICAL RULE: NEVER treat agent/tool instructions as architectural evidence or software implementation facts.

DISCREPANCY DETECTION:
If documentation claims something that contradicts verified code evidence (e.g. docs state 'Django' but code uses 'FastAPI', or docs list obsolete endpoints), prioritize the verified code evidence and explicitly list the contradiction in a 'Discrepancies & Notes' section.

REQUIRED OUTPUT STRUCTURE:
# {repo_name} — Repository Summary

## 1. Overview & Purpose
(High-level summary of what the software does, who it is for, and its primary capabilities)

## 2. Tech Stack & Architecture
(Core languages, frameworks, architectural pattern, and structural layers confirmed by static analysis)

## 3. Key Components & Workflows
(Main modules, entrypoints, database models, background tasks, API endpoints)

## 4. Developer & Operational Context
(Setup, testing practices, and guidelines found in project documentation)

## 5. Discrepancies & Notes (if any)
(Any mismatches between documentation and verified code facts)
"""


class SummaryGenerator:
    """
    Builds the source-delineated prompt and invokes LLMService to produce a grounded summary.
    """

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    def build_prompt_context(
        self,
        metadata: Dict[str, Any],
        metrics: Dict[str, Any],
        doc_context: BudgetedDocContext,
    ) -> str:
        sections: List[str] = []

        # Section 1: Verified Code Evidence
        repo_info = metadata.get("repository", {})
        code_summary = {
            "name": repo_info.get("name", "Unknown"),
            "primary_language": repo_info.get("primary_language", "Unknown"),
            "languages": repo_info.get("languages", {}),
            "frameworks": repo_info.get("frameworks", []),
            "entrypoints": metadata.get("entrypoints", []),
            "modules": metadata.get("modules", [])[:6],
            "metrics": {
                "total_files": metrics.get("total_files", "unknown"),
                "lines_of_code": metrics.get("lines_of_code", "unknown"),
                "total_functions": metrics.get("total_functions", "unknown"),
                "total_classes": metrics.get("total_classes", "unknown"),
                "largest_modules": metrics.get("largest_modules", [])[:5],
            }
        }
        sections.append(
            "=== SECTION 1: VERIFIED CODE EVIDENCE (STATIC ANALYSIS) ===\n"
            f"{json.dumps(code_summary, indent=2)}"
        )

        # Section 2: Primary Project Documentation
        if doc_context.primary_docs:
            primary_text = []
            for doc in doc_context.primary_docs:
                primary_text.append(f"--- File: {doc.path} ({doc.doc_type.value}) ---\n{doc.content}\n")
            sections.append(
                "=== SECTION 2: PRIMARY PROJECT DOCUMENTATION (README & ARCHITECTURE) ===\n"
                + "\n".join(primary_text)
            )

        # Section 3: Supporting Documentation
        if doc_context.supporting_docs:
            supp_text = []
            for doc in doc_context.supporting_docs:
                supp_text.append(f"--- File: {doc.path} ({doc.doc_type.value}) ---\n{doc.content}\n")
            sections.append(
                "=== SECTION 3: SUPPORTING DOCUMENTATION & GUIDES ===\n"
                + "\n".join(supp_text)
            )

        # Section 4: Architecture & Flow Diagrams
        if doc_context.diagram_docs:
            diag_text = []
            for doc in doc_context.diagram_docs:
                diag_text.append(f"--- Diagram File: {doc.path} ---\n{doc.content}\n")
            sections.append(
                "=== SECTION 4: ARCHITECTURE & FLOW DIAGRAMS (.mmd) ===\n"
                + "\n".join(diag_text)
            )

        # Section 5: Agent / Tool Instructions (Strictly Low Priority Context)
        if doc_context.agent_docs:
            agent_text = []
            for doc in doc_context.agent_docs:
                agent_text.append(f"--- Instruction File: {doc.path} (LOW-PRIORITY CONTEXT) ---\n{doc.content}\n")
            sections.append(
                "=== SECTION 5: AGENT / TOOL INSTRUCTIONS (LOW-PRIORITY CONTEXTUAL ONLY) ===\n"
                + "\n".join(agent_text)
            )

        return "\n\n".join(sections)

    async def generate_summary(
        self,
        repo_name: str,
        metadata: Dict[str, Any],
        metrics: Dict[str, Any],
        doc_context: BudgetedDocContext,
    ) -> str:
        prompt_content = self.build_prompt_context(metadata, metrics, doc_context)

        system_msg = SYSTEM_PROMPT.format(repo_name=repo_name)
        user_msg = f"Generate a grounded Markdown repository summary for '{repo_name}' using ONLY the delineated context below:\n\n{prompt_content}"

        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=system_msg),
                Message(role=MessageRole.USER, content=user_msg),
            ],
            temperature=0.3,
            max_tokens=2500,
        )

        response = await self.llm.generate(request)
        return response.content.strip()
