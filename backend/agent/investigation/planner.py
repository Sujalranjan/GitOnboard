"""
Main LLM Planner and Synthesizer for GitOnBoard.

Handles:
1. Requirement extraction and investigation subtask generation (Phase 3).
2. Final evidence synthesis from verified EvidenceCards without context bloat.
Runs against the Main/Cloud model (or designated provider) with strict token bounds.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from backend.agent.investigation.schemas import InvestigationSubtask
from backend.agent.investigation.state_store import InvestigationStateStore
from backend.ai.service import LLMService
from backend.ai.schemas import LLMRequest, Message, MessageRole
from backend.config import settings

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are an expert repository investigation architect.
Given a complex user question about a software repository and an overview of the codebase, decompose the inquiry into 2 to 4 actionable, verifiable investigation subtasks for local investigation workers.

Each subtask must contain:
1. "id": A unique identifier (e.g. "task_entrypoint", "task_auth_backend", "task_db_persistence").
2. "title": Short, descriptive title.
3. "description": The exact question this task must answer and implementation details to inspect.
4. "target_entities": Relevant files, symbols, modules, or relationships to start with.
5. "search_strategy": Specific search strategy and suggested repository tools (e.g., search_repository, read_file, get_file_outline, get_code_relationships).
6. "expected_output": Concrete facts that must be verified.
7. "completion_criteria": Specific conditions required to consider the task satisfied (e.g., "Must locate handler and inspect line numbers of token verification").
8. "dependencies": List of task IDs that must complete before this task can start.

Output ONLY a JSON array of subtasks matching this schema:
```json
[
  {
    "id": "task_1",
    "title": "Short title",
    "description": "Specific code implementation details to verify",
    "target_entities": ["expected/path/or/symbol"],
    "search_strategy": "Search for symbol X then read_file on file Y",
    "expected_output": "What concrete facts must be verified",
    "completion_criteria": "Must inspect and verify function foo in file bar",
    "dependencies": []
  }
]
```
Do NOT output commentary outside the JSON array.
"""

SYNTHESIZER_SYSTEM_PROMPT = """You are an expert technical documentation and code analysis synthesizer.
Your job is to answer the user's question completely, accurately, and professionally,
based STRICTLY on the repository findings, code excerpts, and file inspection reports provided below.

Your final output must be formatted in clean, rich GitHub Flavored Markdown for clear, high-impact browser visualization.

Presentation & Formatting Rules:
1. Heading Hierarchy:
   - Use `#` for title, `##` for primary sections, and `###` for sub-components or architectural flows.
2. Executive Summary:
   - Begin with a crisp overview summarizing the architecture or flow.
3. Code Inspection & Excerpts:
   - Always wrap code snippets in appropriate fenced code blocks with language tags (e.g. ```javascript, ```python).
   - Annotate code blocks with their file path and line numbers (e.g. `path/to/file.js (lines 40-65)`).
4. Data Structures & Flow Tables:
   - Use Markdown tables or bulleted step-by-step sequences for endpoints, parameters, token lifecycles, or state transitions.
5. Accuracy & Provenance:
   - Answer thoroughly using the facts in the findings dossier and inspected source files.
   - Cite exact file paths and line ranges where applicable.
6. CRITICAL DISTINCTION:
   - "Inspected but unverified/partially traced" means code was read (e.g. function calls seen), but deeper downstream implementation files were not yet inspected.
   - NEVER claim that code or an implementation "was not inspected" or "could not be found" if that file appears in the Files Read list or in the code excerpts.
   - If a file was read (e.g., authController.js or authHelpers.js), accurately state what functions and statements WERE observed, and identify specifically what remaining downstream calls (e.g., createSession) were not yet read.
7. Limitations & Gaps:
   - Place any unverified claims or remaining gaps in a dedicated `## Limitations & Unverified Code Paths` section at the end.
   - Do NOT speculate or invent repository details that are not in the findings dossier.
"""


class MainInvestigationPlanner:
    """
    Main LLM component responsible for planning the investigation and synthesizing the final answer.
    """

    def __init__(self, llm_service: LLMService, model: Optional[str] = None):
        self.llm_service = llm_service
        self.model = model
        self.last_plan_fallback_used = False

    async def create_plan(self, question: str, repo_summary: str = "") -> List[InvestigationSubtask]:
        """
        Decompose a multi-subquestion query into concrete investigation subtasks with strict validation.
        """
        self.last_plan_fallback_used = False
        prompt = (
            f"USER QUESTION:\n{question}\n\n"
            f"REPOSITORY OVERVIEW:\n{repo_summary or 'Full-stack application'}\n\n"
            f"Decompose this inquiry into 2-4 concrete, verifiable investigation tasks as a JSON array."
        )

        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=PLANNER_SYSTEM_PROMPT),
                Message(role=MessageRole.USER, content=prompt),
            ],
            model=self.model,
            temperature=0.1,
            max_tokens=2048,
        )

        try:
            resp = await self.llm_service.generate(request)
            raw_text = resp.content.strip()
            tasks_data = self._extract_json_array(raw_text)
            subtasks = self._validate_and_build_subtasks(tasks_data)
            if subtasks:
                return subtasks
        except Exception as e:
            logger.warning(f"[MainPlanner] LLM plan generation failed: {e}. Falling back to dynamic rule-based plan.")

        # Honest, dynamic fallback plan when model fails or outputs invalid schema
        self.last_plan_fallback_used = True
        return self._generate_dynamic_fallback_plan(question)

    def _validate_and_build_subtasks(self, tasks_data: List[Dict[str, Any]]) -> List[InvestigationSubtask]:
        """Validate generated tasks, reject duplicates and invalid dependencies."""
        if not tasks_data:
            return []

        subtasks: List[InvestigationSubtask] = []
        seen_ids = set()

        for item in tasks_data:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("id", "")).strip()
            title = str(item.get("title", "")).strip()
            description = str(item.get("description", "")).strip()

            # Reject empty IDs or titles
            if not task_id or not title:
                continue

            # Reject duplicate IDs
            if task_id in seen_ids:
                task_id = f"{task_id}_{len(seen_ids)+1}"
            seen_ids.add(task_id)

            target_entities = [str(e).strip() for e in item.get("target_entities", []) if str(e).strip()]
            search_strategy = str(item.get("search_strategy", "")).strip() or "Use search_repository and read_file"
            expected_output = str(item.get("expected_output", "")).strip() or title
            completion_criteria = str(item.get("completion_criteria", "")).strip() or f"Verify facts for {title}"
            dependencies = [str(d).strip() for d in item.get("dependencies", []) if str(d).strip() and str(d).strip() != task_id]

            subtasks.append(
                InvestigationSubtask(
                    id=task_id,
                    title=title,
                    description=description or title,
                    target_entities=target_entities,
                    search_strategy=search_strategy,
                    expected_output=expected_output,
                    completion_criteria=completion_criteria,
                    dependencies=dependencies,
                )
            )

        # Sanitize dependencies so no task depends on an unknown task ID
        valid_ids = {t.id for t in subtasks}
        for t in subtasks:
            t.dependencies = [dep for dep in t.dependencies if dep in valid_ids]

        return subtasks

    def _generate_dynamic_fallback_plan(self, question: str) -> List[InvestigationSubtask]:
        """Generate a transparent dynamic fallback plan based on the question."""
        cleaned_q = question.strip()
        q_snippet = cleaned_q[:80] + ("..." if len(cleaned_q) > 80 else "")

        return [
            InvestigationSubtask(
                id="task_entrypoints_discovery",
                title=f"Trace Entrypoints & Core Logic for: {q_snippet}",
                description=f"Identify source files, entrypoints, and routing relevant to: {cleaned_q}",
                search_strategy="Use search_repository to find relevant symbols and endpoints, then read_file on identified handlers.",
                expected_output="Primary implementation functions and source file paths.",
                completion_criteria="Must inspect discovered entry point files and record concrete facts.",
            ),
            InvestigationSubtask(
                id="task_data_and_dependencies",
                title="Verify Data Models, Services, and State",
                description=f"Inspect models, storage, schema, and security/state logic supporting: {q_snippet}",
                search_strategy="Use get_code_relationships and read_file to inspect downstream services and models.",
                expected_output="Verified database schemas, service calls, and configuration parameters.",
                completion_criteria="Must verify data access patterns or persistence logic.",
                dependencies=["task_entrypoints_discovery"],
            ),
        ]

    async def synthesize_answer(self, question: str, store: InvestigationStateStore) -> str:
        """
        Synthesize the final comprehensive answer using only the verified evidence dossier.
        Consumes bounded prompt tokens while preserving all findings and transparency reports.
        """
        dossier = store.format_evidence_dossier(max_chars=settings.investigation_max_observation_chars)
        user_prompt = (
            f"ORIGINAL QUESTION:\n{question}\n\n"
            f"{dossier}\n\n"
            f"Provide your complete, comprehensive Markdown answer now based strictly on the verified findings above."
        )

        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=SYNTHESIZER_SYSTEM_PROMPT),
                Message(role=MessageRole.USER, content=user_prompt),
            ],
            model=self.model,
            temperature=0.2,
            max_tokens=settings.investigation_synthesis_max_tokens,
        )

        resp = await self.llm_service.generate(request)
        return resp.content.strip()

    def _extract_json_array(self, text: str) -> List[Dict[str, Any]]:
        try:
            val = json.loads(text)
            if isinstance(val, list):
                return val
        except Exception:
            pass
        m = re.search(r"(\[.*\])", text, re.DOTALL)
        if m:
            try:
                val = json.loads(m.group(1))
                if isinstance(val, list):
                    return val
            except Exception:
                pass
        return []
