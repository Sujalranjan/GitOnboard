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

SYSTEM_PROMPT = """You are a senior software architect creating a concise, developer-friendly project overview.
Your goal is to explain the project clearly so a developer can immediately understand what it does, how it is organized, and how to get started.

GUIDING PRINCIPLES:
1. Synthesize & Explain: Focus on project purpose, architecture, core features, key workflows, and setup. Explain concepts in clear, direct technical language.
2. Be as Concise as Possible, but as Detailed as Necessary:
   - For focused repositories, maintain a clean, high-impact 4-5 section summary.
   - For complex, multi-service, or large systems, allow the summary to expand to explain critical architectural layers, verified API endpoints, or data flows without omitting key details.
3. DO NOT Dump Configuration Files or File Trees: Never copy-paste entire .env files, Dockerfiles, docker-compose files, shell script blocks, raw file trees, or boilerplate contribution guides.
4. DO NOT Enumerate Function Counts or Raw Metrics: Avoid reciting mechanical AST statistics (e.g., 'has 12 functions, 64 total functions'). Instead, describe the functional roles of the primary modules.
5. Grounding & Accuracy: Use ONLY the supplied evidence. Never invent features, endpoints, CLI commands, or relationships. If a detail requires deeper investigation or is omitted from the evidence, state the limitation or omit it.
6. Repository Naming: Always identify the repository as '{repo_name}'. NEVER use raw internal UUID hashes as the project title or in the text.
7. Visual Architecture Diagram: Where an architectural relationship or data flow is evidenced, include a clean, valid ```mermaid flowchart or diagram (e.g., ```mermaid graph TD / flowchart LR) showing services and data boundaries. NEVER print diagram nodes as plain text lines outside a ```mermaid code fence.
8. Conditional Tables & Commands: Include copyable quickstart commands (in bash/sh code blocks) or verified API endpoint tables ONLY when genuine supporting data exists in the evidence.
9. Single Pass Generation: Output the document EXACTLY ONCE from start to finish. Never duplicate or restart the document.

REQUIRED STRUCTURE:
Output ONLY the final summary document in clean Markdown. Do NOT repeat instructions, do NOT repeat the document, and do NOT include meta-commentary.

# {repo_name} — Project Overview

## 1. Purpose & Core Value
A concise explanation (1-2 paragraphs) of what the system does, the problems it solves, and its primary end-user or API capabilities.

## 2. Architecture & System Flow
High-level architectural pattern (e.g., microservices, modular monolith, event-driven) and how components connect.
Include a clean ```mermaid diagram illustrating primary service boundaries, inter-service communication, and persistent stores.

## 3. Major Components & Key Features
A breakdown of the principal services or modules and their responsibilities:
- Group related components logically (e.g., Core API, Worker/Inference Engine, Data Access, Security).
- Highlight key capabilities (e.g., authentication, async jobs, streaming, external integrations).
- If evidenced, include a compact table of core endpoints or workflows.

## 4. Operational & Deployment Model
A developer-focused summary of how the system runs (e.g., Docker containerization, exposed ports, runtime dependencies).
- Include verified quickstart / run commands in code blocks when present in evidence.

## 5. Notes & Observations (Optional)
Notable design constraints, verified discrepancies between documentation and implementation, or areas requiring deeper investigation."""


class SummaryGenerator:
    """
    Builds the source-delineated prompt and invokes LLMService to produce a grounded summary.
    """

    def __init__(self, llm_service: LLMService, model: Optional[str] = None):
        self.llm = llm_service
        self.model = model

    def build_prompt_context(
        self,
        metadata: Dict[str, Any],
        metrics: Dict[str, Any],
        doc_context: BudgetedDocContext,
    ) -> str:
        sections: List[str] = []

        # Section 1: Verified Code Evidence
        repo_info = metadata.get("repository", {})
        # Resolve modules from metadata or fallback to largest_modules
        resolved_modules = metadata.get("modules", [])
        if not resolved_modules:
            largest = metrics.get("largest_modules", [])
            resolved_modules = [
                {"name": m.get("module", ""), "function_count": m.get("count", 0)}
                for m in largest[:6]
            ]


        # Format modules by name and purpose/role if available
        module_names = [
            m.get("name") if isinstance(m, dict) else str(m)
            for m in resolved_modules[:8]
            if m
        ]

        code_summary = {
            "name": repo_info.get("name", "Unknown"),
            "primary_language": repo_info.get("primary_language", "Unknown"),
            "languages": repo_info.get("languages", {}),
            "frameworks": metadata.get("frameworks") or repo_info.get("frameworks", []),
            "entrypoints": metadata.get("entrypoints", []),
            "key_modules": module_names,
            "architecture_style": metadata.get("architecture", {}).get("style", "modular"),
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
            model=self.model,
            temperature=0.3,
            max_tokens=2500,
        )

        response = await self.llm.generate(request)
        return response.content.strip()
