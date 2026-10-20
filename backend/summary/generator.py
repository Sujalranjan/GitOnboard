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
Your goal is to explain the project clearly so a developer can immediately understand what it does and how it is organized.

GUIDING PRINCIPLES:
1. Synthesize & Explain: Focus on the purpose, system responsibilities, and how pieces connect. Explain concepts in clear, direct technical language.
2. DO NOT Dump Configuration Files: Never copy-paste entire .env files, Dockerfiles, docker-compose files, shell script blocks, or boilerplate contribution guides. Summarize the operational model concisely instead.
3. DO NOT Enumerate Function Counts or Raw File Lists: Avoid reciting raw AST statistics (e.g. "authcontroller.js has 12 functions, 64 total functions"). Instead, describe the functional roles of the primary modules.
4. DO NOT Invent Workflows or Speculate: Use only the supplied evidence. Prefer clear explanation over false completeness. If a detail requires deeper investigation or is not in the evidence, state the limitation or omit it.
5. Repository Naming: Always identify the repository as '{repo_name}'. NEVER use raw internal UUID hashes as the project title or in the text.
6. Visual Architecture Diagram: Where an architectural relationship or data flow is evidenced, include a clean, valid ```mermaid flowchart or diagram (e.g. ```mermaid graph TD / flowchart LR) showing services and data boundaries.

REQUIRED STRUCTURE:
Output ONLY the final summary document in clean Markdown. Do NOT repeat instructions or include meta-commentary.

# {repo_name} — Project Overview

## 1. Purpose & Core Value
A concise 1-2 paragraph explanation of what the system does, the problems it solves, and its primary end-user or API capabilities.

## 2. Architecture & System Flow
High-level architectural pattern (e.g., microservices, modular monolith, event-driven) and how components connect.
Include a clean ```mermaid diagram illustrating the primary service boundaries, APIs, and data stores.

## 3. Major Components & Key Features
A concise breakdown of the principal services or modules and their responsibilities:
- Group related components logically (e.g., Core API, Worker/Inference Engine, Data Access, Security).
- Highlight key features (e.g., authentication, async jobs, streaming, external integrations).

## 4. Operational & Deployment Model
A brief developer summary of how the system runs (e.g. Docker multi-container composition, primary exposed ports, required database/cloud services). Synthesize the runtime model without dumping raw files.

## 5. Notes & Observations (Optional)
Any notable design constraints, verified discrepancies between documentation and implementation, or areas requiring deeper investigation.
"""


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
        content = response.content.strip()

        # Clean any accidental echoing of prompt instructions
        cleaned_lines = []
        skip_prefixes = (
            "CRITICAL NAMING RULE",
            "NAMING RULE:",
            "REQUIRED OUTPUT STRUCTURE",
            "EVIDENCE TRUST HIERARCHY",
            "DISCREPANCY DETECTION:",
            "DIAGRAMS & VISUALIZATIONS:",
        )
        for line in content.splitlines():
            trimmed = line.strip()
            if any(trimmed.startswith(prefix) for prefix in skip_prefixes):
                continue
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()
