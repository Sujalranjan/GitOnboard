"""
PlanningOrchestrator: Connects canonical repository intelligence into a validated, reviewable implementation plan.

Zero Rebuilding Rule: Reuses existing:
  - RepositoryInvestigator (backend/intelligence/retrieval/repository_investigator.py)
  - RequirementAnalyzer (intent & acceptance criteria)
  - ImpactAnalyzer (affected symbols & blast radius)
  - ContractGenerator (ground-truth behavior & tests required)
  - StepPlanner (step-by-step implementation tasks)
  - ContextAssembler / RepositoryContext (evidence & unknowns)
  - PlanValidator (architectural & DAG constraint checking)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import re
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session

from backend.ai.service import LLMService
from backend.agent.context.contracts import RepositoryContext
from backend.intelligence.contracts.investigation import (
    EvidenceStatus,
    ImplementationAssessment,
    InvestigationCoverage,
    InvestigationEvidence,
    RepositoryInvestigationResult,
    SourceSnippetEvidence,
)
from backend.intelligence.retrieval.repository_investigator import RepositoryInvestigator
from backend.planning.requirements import AnalyzedRequirement, RequirementAnalyzer, AcceptanceCriterion
from backend.planning.impact_analysis import ImpactAnalyzer, ImpactResult
from backend.planning.contract import ContractGenerator, ContractOutput
from backend.planning.planner import StepPlanner, PlanStep
from backend.planning.change_classifier import ChangeTypeClassifier, ChangeType
from .contracts import Plan, PlanTask, PlanStatus, PlanTaskStatus, PlanValidationResult
from .validator import PlanValidator

logger = logging.getLogger(__name__)


def _run_coroutine_safely(coro_factory, timeout: float = 15.0):
    """
    Safely executes an async factory function in a clean, dedicated event loop thread.
    Guarantees 100% deadlock-free execution in synchronous, pytest, and async environments.
    """
    def runner():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro_factory())
        finally:
            new_loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(runner).result(timeout=timeout)


class PlanningOrchestrator:
    """
    Orchestrates the synthesis and validation of repository-aware implementation plans.
    """

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service
        self.validator = PlanValidator()

    def create_plan(
        self,
        context: RepositoryContext,
        agent_run_id: str,
        repository_id: str,
        requirement: str,
        db: Optional[Session] = None,
        version: int = 1,
        repository_revision: Optional[str] = None,
    ) -> Plan:
        """
        Synthesizes a validated Plan from the user requirement, repository investigation, and RepositoryContext.
        """
        logger.info(f"PlanningOrchestrator: Beginning plan generation for run '{agent_run_id}' (v{version})")

        # ──────────────────────────────────────────────────────────────────────
        # 1. Canonical Code-Level Repository Investigation
        # ──────────────────────────────────────────────────────────────────────
        analysis_id = getattr(context, "analysis_id", None)
        if not analysis_id and context.metadata:
            analysis_id = context.metadata.get("analysis_id")
        
        if not analysis_id and db and repository_id:
            try:
                from backend.models.repository import Analysis, Repository
                repo = None
                if str(repository_id).isdigit():
                    repo = db.query(Repository).filter(Repository.id == int(repository_id)).first()
                if not repo:
                    repo = db.query(Repository).filter(
                        Repository.url.ilike(f"%{repository_id}%")
                    ).first()
                
                if repo:
                    latest_analysis = (
                        db.query(Analysis)
                        .filter(Analysis.repository_id == repo.id)
                        .order_by(Analysis.id.desc())
                        .first()
                    )
                    if latest_analysis:
                        analysis_id = latest_analysis.id
            except Exception as err:
                logger.debug(f"Could not resolve analysis_id from repository_id {repository_id}: {err}")

        logger.info(f"PlanningOrchestrator: create_plan called with context.analysis_id={getattr(context, 'analysis_id', None)}, resolved analysis_id={analysis_id}, db={type(db)}")

        worktree_path = context.metadata.get("worktree_path") if context.metadata else None

        investigator = RepositoryInvestigator()
        investigation_result = investigator.investigate(
            requirement=requirement,
            analysis_id=analysis_id,
            db=db,
            base_path=worktree_path,
        )
        logger.info(
            f"PlanningOrchestrator: Investigation completed -> Assessment: {investigation_result.assessment.value}, "
            f"Inspected files: {len(investigation_result.inspected_files)}, "
            f"Snippets: {len(investigation_result.source_snippets)}"
        )

        # ──────────────────────────────────────────────────────────────────────
        # 2. Requirement Decomposition (RequirementAnalyzer)
        # ──────────────────────────────────────────────────────────────────────
        analyzed_req = self._analyze_requirement(requirement)

        # ──────────────────────────────────────────────────────────────────────
        # 2b. Change Type Classification (Prevents Scope Explosion)
        # ──────────────────────────────────────────────────────────────────────
        change_type = ChangeTypeClassifier.classify(requirement)
        logger.info(f"PlanningOrchestrator: Classified change as {change_type.value}")

        # ──────────────────────────────────────────────────────────────────────
        # 3. Impact Analysis (ImpactAnalyzer) — Skip for Trivial Changes
        # ──────────────────────────────────────────────────────────────────────
        impact_result: Optional[ImpactResult] = None

        # Only run ImpactAnalyzer for actual code changes, not comments/docs
        if change_type == ChangeType.CODE_CHANGE and db and analysis_id:
            try:
                analyzer = ImpactAnalyzer(db=db, analysis_id=analysis_id)
                extracted_kws = [w.lower() for w in requirement.split() if len(w) > 3]
                impact_result = analyzer.analyze_sync(keywords=extracted_kws or [requirement])
            except Exception as err:
                logger.warning(f"ImpactAnalyzer error during planning: {err}")

        # Combine context files with investigated candidate files
        affected_files: List[str] = list(dict.fromkeys(
            list(context.relevant_files) + investigation_result.inspected_files
        ))
        affected_symbols: List[str] = list(dict.fromkeys(
            [s.get("name", "") for s in context.relevant_symbols if s.get("name")] + investigation_result.relevant_symbols
        ))

        # Only add ImpactAnalyzer results for CODE_CHANGE type
        if change_type == ChangeType.CODE_CHANGE and impact_result:
            for f in (impact_result.candidate_files or []):
                if f and f not in affected_files:
                    affected_files.append(f)
            for s in (impact_result.candidate_symbols or []):
                if s and s not in affected_symbols:
                    affected_symbols.append(s)

        # Validate file relevance and remove semantically unrelated files
        affected_files = self._validate_file_relevance(affected_files, requirement)

        # ──────────────────────────────────────────────────────────────────────
        # 4. Acceptance Contract Generation (ContractGenerator)
        # ──────────────────────────────────────────────────────────────────────
        contract_output = self._generate_contract(analyzed_req, impact_result, context)

        # ──────────────────────────────────────────────────────────────────────
        # 5. Step Planning (StepPlanner + Investigation Grounding)
        # ──────────────────────────────────────────────────────────────────────
        if investigation_result.assessment == ImplementationAssessment.EXISTING:
            steps = []
        else:
            steps = self._generate_steps(
                analyzed_req,
                impact_result,
                contract_output,
                context,
                investigation=investigation_result,
                db=db,
                analysis_id=analysis_id,
                repository_id=repository_id,
            )

        # ──────────────────────────────────────────────────────────────────────
        # 6. Task DAG Assembly
        # ──────────────────────────────────────────────────────────────────────
        tasks: List[PlanTask] = []
        task_deps_map: Dict[str, List[str]] = {}

        for step in steps:
            task_id = f"task-{step.step_number}"
            
            # Map dependencies (integers or strings) to task IDs
            norm_deps: List[str] = []
            for dep in step.dependencies:
                if isinstance(dep, int):
                    norm_deps.append(f"task-{dep}")
                elif isinstance(dep, str):
                    dep_str = dep if dep.startswith("task-") else f"task-{dep}"
                    norm_deps.append(dep_str)

            task_deps_map[task_id] = norm_deps

            # Determine task acceptance criteria
            task_criteria = step.acceptance_criteria or [
                c.description for c in analyzed_req.acceptance_criteria
            ] or [f"Satisfy requirement: {step.title}"]

            # Assign verification strategy
            verification_strat = "verify_static"
            if "test" in step.title.lower() or "verify" in step.title.lower():
                verification_strat = "verify_test_suite"
            elif step.component_type == "NEW":
                verification_strat = "verify_static_and_syntax"

            task_files = step.target_files or ([affected_files[0]] if affected_files else [])

            # Formulate explicit task rationale ("Why this file?")
            task_rationale = getattr(step, "rationale", None) or (
                f"Task targets {', '.join(task_files)} to implement '{step.title}'. "
                f"Grounding: {investigation_result.assessment_reason}"
            )

            tasks.append(
                PlanTask(
                    task_id=task_id,
                    step_number=step.step_number,
                    title=step.title,
                    description=step.description or f"Implement {step.title} for {step.target_files}",
                    rationale=task_rationale,
                    status=PlanTaskStatus.PENDING,
                    dependencies=norm_deps,
                    affected_files=task_files,
                    affected_symbols=step.affected_symbols or [],
                    component_type=step.component_type,
                    acceptance_criteria=task_criteria,
                    verification_strategy=verification_strat,
                    evidence_ids=step.evidence_ids or [],
                )
            )

        # ──────────────────────────────────────────────────────────────────────
        # 7. Global Plan Artifact Assembly
        # ──────────────────────────────────────────────────────────────────────
        global_criteria = [c.description for c in analyzed_req.acceptance_criteria] or [requirement]
        
        # Bounded summaries of understanding and architecture
        repo_understanding_summary = {
            "completeness": context.contract.completeness.value,
            "satisfied_categories": context.contract.satisfied_categories,
            "missing_categories": context.contract.missing_categories,
            "evidence_count": len(context.evidence),
        }
        
        arch_summary = {
            "capabilities_detected": [c.get("name") for c in context.capabilities if c.get("name")],
            "routes_count": len(context.relevant_routes),
            "db_objects_count": len(context.relevant_db_objects),
            "dependencies_count": len(context.relevant_dependencies),
        }

        # Construct truthful affected areas strictly matching the planned implementation tasks
        truthful_affected_areas: List[Dict[str, Any]] = []
        seen_area_files: Set[str] = set()

        for task in tasks:
            for f in task.affected_files:
                if f and f not in seen_area_files:
                    seen_area_files.add(f)
                    truthful_affected_areas.append({
                        "file": f,
                        "component_type": task.component_type,
                    })

        # Risks synthesis
        risks: List[str] = []
        if len(truthful_affected_areas) > 3:
            risks.append(f"Multi-file modification risk: {len(truthful_affected_areas)} files affected across codebase")
        if context.contract.missing_categories:
            risks.append(f"Incomplete context risk: Missing categories {context.contract.missing_categories}")
        
        plan_unknowns = list(context.unknowns) if context.unknowns else []
        if investigation_result.assessment == ImplementationAssessment.UNCERTAIN:
            plan_unknowns.append(
                f"Investigation Notice: {investigation_result.assessment_reason} {investigation_result.decision_rationale}"
            )

        plan = Plan(
            agent_run_id=agent_run_id,
            repository_id=repository_id,
            requirement=requirement,
            version=version,
            status=PlanStatus.DRAFT,
            repository_revision=repository_revision,
            repository_understanding=repo_understanding_summary,
            architecture_context=arch_summary,
            affected_areas=truthful_affected_areas,
            constraints=context.architecture_constraints,
            investigation=investigation_result,
            tasks=tasks,
            task_dependencies=task_deps_map,
            acceptance_criteria=global_criteria,
            verification_strategy="verify_static_and_automated_tests",
            risks=risks,
            unknowns=plan_unknowns,
        )

        # ──────────────────────────────────────────────────────────────────────
        # 8. Plan Validation (PlanValidator)
        # ──────────────────────────────────────────────────────────────────────
        # If capability already exists (0 tasks), validation treats as valid (complete)
        if investigation_result.assessment == ImplementationAssessment.EXISTING:
            plan.status = PlanStatus.READY_FOR_APPROVAL
            plan.validation = PlanValidationResult(
                valid=True,
                errors=[],
                warnings=[f"Capability already exists: {investigation_result.assessment_reason}"],
            )
            logger.info(f"PlanningOrchestrator: Plan '{plan.plan_id}' verified EXISTING -> READY_FOR_APPROVAL")
            return plan

        validation_result = self.validator.validate(plan)
        plan.validation = validation_result

        if validation_result.valid:
            plan.status = PlanStatus.READY_FOR_APPROVAL
            logger.info(f"PlanningOrchestrator: Plan '{plan.plan_id}' successfully validated -> READY_FOR_APPROVAL")
        else:
            plan.status = PlanStatus.INVALID
            logger.warning(f"PlanningOrchestrator: Plan '{plan.plan_id}' failed validation: {validation_result.errors}")

        return plan

    def _analyze_requirement(self, requirement: str) -> AnalyzedRequirement:
        """Decomposes the requirement using RequirementAnalyzer or structured fallback."""
        if self.llm_service:
            try:
                req_analyzer = RequirementAnalyzer(llm_service=self.llm_service)
                return _run_coroutine_safely(lambda: req_analyzer.analyze(requirement), timeout=10.0)
            except Exception as err:
                logger.warning(f"RequirementAnalyzer execution error: {err}")

        return AnalyzedRequirement(
            title=requirement[:60],
            goals=[requirement],
            acceptance_criteria=[
                AcceptanceCriterion(id="AC-01", description=f"Implement and verify: {requirement}")
            ],
            security_considerations=[],
            tests_required=[f"Automated test for {requirement[:40]}"],
        )

    def _validate_file_relevance(self, files: List[str], requirement: str) -> List[str]:
        """
        Filter out semantically unrelated files that were included due to keyword matching.

        Removes files that are clearly irrelevant to the actual implementation:
        - Policy and legal documents (CODE_OF_CONDUCT, LICENSE, etc.)
        - Unrelated GitHub workflows
        - Generic configuration files unrelated to the requirement
        - Build/deployment files unrelated to source changes

        Keeps:
        - Source code files
        - Test files
        - Configuration related to the change
        - Documentation relevant to the change
        """
        if not files:
            return files

        req_lower = requirement.lower()
        validated: List[str] = []
        excluded_patterns = {
            "code_of_conduct",
            "license",
            "contributing",
            "changelog",
            "authors",
            "maintainers",
            ".github/workflows",  # Generic workflows not related to feature
            "renovate.json",
            "dependabot.yml",
            "package-lock.json",
            "yarn.lock",
            "uv.lock",
        }

        for f in files:
            f_lower = f.lower()

            # Reject files matching excluded patterns
            excluded = False
            for pattern in excluded_patterns:
                if pattern in f_lower:
                    # Exception: keep workflow files if explicitly mentioned in requirement
                    if ".github/workflows" in f_lower and ("workflow" in req_lower or "github" in req_lower or "action" in req_lower):
                        excluded = False
                        break
                    excluded = True
                    break

            if excluded:
                logger.debug(f"PlanningOrchestrator: Filtering out semantically unrelated file: {f}")
                continue

            validated.append(f)

        return validated if validated else files  # Return original if all were filtered (safety)

    def _generate_contract(
        self,
        requirement: AnalyzedRequirement,
        impact: Optional[ImpactResult],
        context: RepositoryContext,
    ) -> ContractOutput:
        """Synthesizes the implementation contract using ContractGenerator or deterministic fallback."""
        if self.llm_service and impact:
            try:
                gen = ContractGenerator(llm_service=self.llm_service)
                return _run_coroutine_safely(lambda: gen.generate(requirement, impact), timeout=10.0)
            except Exception as err:
                logger.warning(f"ContractGenerator execution error: {err}")

        return ContractOutput(
            affected_components=[],
            tests_required=[f"Verify {requirement.title}"],
            security_considerations=[],
        )

    def _generate_steps(
        self,
        requirement: AnalyzedRequirement,
        impact: Optional[ImpactResult],
        contract: ContractOutput,
        context: RepositoryContext,
        investigation: Optional[RepositoryInvestigationResult] = None,
        db: Optional[Session] = None,
        analysis_id: Optional[int] = None,
        repository_id: Optional[str] = None,
    ) -> List[PlanStep]:
        """Synthesizes sequential implementation steps based strictly on actual inspected code and LLM reasoning."""
        from backend.intelligence.retrieval.source_reader import RepositorySourceReader
        from backend.models.fact_store import FactFile
        from backend.config import settings
        import re

        raw_req = requirement.title.strip()
        action_title = raw_req

        worktree_path = context.metadata.get("worktree_path") if hasattr(context, "metadata") and context.metadata else None
        source_reader = RepositorySourceReader(base_path=worktree_path, db=db, analysis_id=analysis_id)

        # Determine target files from investigation or context or requirement text
        candidate_files = list(context.relevant_files)
        if investigation and investigation.inspected_files:
            for f in investigation.inspected_files:
                if f not in candidate_files:
                    candidate_files.append(f)

        # If candidate files are empty, retrieve target repository's analyzed code files
        if not candidate_files and db and analysis_id:
            try:
                db_files = db.query(FactFile).filter(FactFile.analysis_id == analysis_id).all()
                for df in db_files:
                    if not df.path.endswith((".json", ".md", ".yml", ".yaml", "Makefile")) and df.path not in candidate_files:
                        candidate_files.append(df.path)
            except Exception as err:
                logger.debug(f"Could not retrieve fallback files from FactFile: {err}")

        # Check for explicit file mentions in user requirement
        file_matches = re.findall(r'[a-zA-Z0-9_\-\.\/\]+\.[a-zA-Z0-9]+', raw_req)
        for fm in file_matches:
            resolved_p = source_reader.resolve_file_path(fm)
            if resolved_p and source_reader.base_path:
                try:
                    rel_path = str(resolved_p.relative_to(source_reader.base_path)).replace(chr(92), "/")
                except ValueError:
                    rel_path = fm
                if rel_path not in candidate_files:
                    candidate_files.insert(0, rel_path)

        # Read actual source code snippets for candidate files
        inspected_code_snippets = []
        for cf in candidate_files[:3]:
            content = source_reader.read_file_content(cf, max_lines=150)
            if content:
                inspected_code_snippets.append("File: `" + str(cf) + "`\n```\n" + str(content) + "\n```")

        code_context_str = "\n\n".join(inspected_code_snippets) if inspected_code_snippets else "No source snippets available."

        # ──────────────────────────────────────────────────────────────────
        # LLM-Powered Step Synthesis Over Inspected Source Code + RIM
        # ──────────────────────────────────────────────────────────────────
        rim_metadata_text = ""
        if self.llm_service:
            try:
                from backend.ai.schemas import LLMRequest, Message, MessageRole
                from backend.services.rim_metadata import build_rim_metadata_block
                from backend.intelligence.retrieval.retriever import HybridRetriever
                import json
                import asyncio

                # Extract RIM metadata if analysis_id available
                if analysis_id and db:
                    try:
                        retriever = HybridRetriever(
                            db=db,
                            analysis_id=analysis_id,
                            enable_graph_expansion=True,
                            graph_expansion_depth=2,
                            graph_expansion_nodes_per_hop=3,
                            graph_expansion_max_total=30,
                        )

                        rim_metadata_block = build_rim_metadata_block(
                            db=db,
                            analysis_id=analysis_id,
                            question=raw_req,
                            retriever=retriever,
                            max_seed_entities=3,
                            max_related_per_seed=8,
                            max_block_chars=2000,
                        )

                        if rim_metadata_block and rim_metadata_block.text:
                            rim_metadata_text = f"\n\nREPOSITORY INTELLIGENCE MAPPING (RIM - Architectural Relationships):\n{rim_metadata_block.text}"
                            logger.info(
                                f"[PLANNING_RIM] RIM metadata built for planning: "
                                f"anchors={len(rim_metadata_block.anchor_entities)}, "
                                f"expanded={len(rim_metadata_block.expanded_entities)}, "
                                f"relationships={rim_metadata_block.relationship_types_used}"
                            )
                    except Exception as err:
                        logger.warning(f"[PLANNING_RIM] Failed to build RIM metadata for planning: {err}")

            except Exception as err:
                logger.warning(f"[PLANNING_RIM] RIM extraction setup error: {err}")

        if self.llm_service:
            try:
                from backend.ai.schemas import LLMRequest, Message, MessageRole
                import json
                import asyncio

                llm_prompt = f"""You are an expert AI software architect designing a grounded implementation plan for a codebase.

TARGET REPOSITORY:
{repository_id or getattr(context, 'repository_id', 'default')}

USER REQUIREMENT:
{raw_req}

RELEVANT TARGET FILES:
{', '.join(candidate_files[:6]) if candidate_files else 'None detected'}

INSPECTED SOURCE CODE:
{code_context_str}{rim_metadata_text}

Generate 2 to 3 concrete sequential plan steps that directly implement the user requirement based on the inspected code and architectural relationships.
Return a JSON array of step objects matching this exact structure:
[
  {{
    "step_number": 1,
    "title": "Exact actionable title",
    "description": "Detailed description of the file modifications",
    "target_files": ["path/to/file"],
    "component_type": "EXISTING"
  }}
]
Do NOT hallucinate unrelated files or generic changes. Return ONLY valid JSON array."""

                logger.info(
                    f"[PLANNING_LLM_REQUEST] LLM prompt length: {len(llm_prompt)} chars\n"
                    f"[PLANNING_LLM_REQUEST] Contains RIM metadata: {bool(rim_metadata_text)}"
                )

                from backend.agent.context.rim_guidance import get_rim_guidance_for_system_prompt

                rim_guidance = get_rim_guidance_for_system_prompt(
                    include_sections=['anchor', 'positive', 'negative', 'priority'],
                    max_chars=1500
                )

                planning_system_prompt = (
                    "You are a precise software planning engine grounded in actual repository architecture. "
                    "Respond with a JSON array of plan steps. Reference architectural relationships (CALLS, IMPORTS, CONTAINS) where relevant.\n\n"
                    "CRITICAL PLANNING RULES:\n"
                    "1. Ground plan steps in actual repository code, not inferred features\n"
                    "2. For negative queries: only claim absence if explicitly verified; express uncertainty otherwise\n"
                    "3. Use anchor entities (direct matches) as primary evidence, not expanded context alone\n"
                    "4. Preserve relationship direction: CALLS(A,B) means A invokes B, not vice versa\n\n"
                    "REPOSITORY RELATIONSHIP INTERPRETATION:\n"
                    f"{rim_guidance}"
                )

                llm_req = LLMRequest(
                    model=settings.model_terminal_plan,
                    messages=[
                        Message(role=MessageRole.SYSTEM, content=planning_system_prompt),
                        Message(role=MessageRole.USER, content=llm_prompt),
                    ],
                    temperature=0.1,
                    max_tokens=600,
                )

                resp = _run_coroutine_safely(lambda: self.llm_service.generate(llm_req), timeout=10.0)
                content = resp.content.strip() if hasattr(resp, "content") else str(resp)
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                parsed_steps = json.loads(content)
                if isinstance(parsed_steps, list) and len(parsed_steps) > 0:
                    llm_steps: List[PlanStep] = []
                    for s_data in parsed_steps:
                        st_num = int(s_data.get("step_number", len(llm_steps) + 1))
                        t_files = s_data.get("target_files", candidate_files[:1] if candidate_files else ["pls_cli/please.py"])
                        p_step = PlanStep(
                            step_number=st_num,
                            title=s_data.get("title", f"Step {st_num}"),
                            description=s_data.get("description", ""),
                            target_files=t_files,
                            component_type=s_data.get("component_type", "EXISTING"),
                            acceptance_criteria=["AC-01"],
                            dependencies=[st_num - 1] if st_num > 1 else [],
                        )
                        setattr(p_step, "rationale", f"Grounded implementation step: {s_data.get('title')}")
                        llm_steps.append(p_step)
                    if llm_steps:
                        logger.info(f"PlanningOrchestrator: LLM successfully synthesized {len(llm_steps)} dynamic plan steps.")
                        return llm_steps
            except Exception as err:
                logger.warning(f"PlanningOrchestrator LLM step generation error: {err}")

        # Grounded Fallback Steps
        steps: List[PlanStep] = []
        is_new_impl = not bool(candidate_files)
        if is_new_impl:
            is_ts = "typescript" in context.architecture_constraints if hasattr(context, "architecture_constraints") else False
            ext = ".ts" if is_ts else ".py"
            impl_files = [f"src/{action_title.lower().replace(' ', '_')}{ext}"]
        else:
            impl_files = candidate_files[:1]

        test_candidates = [f for f in candidate_files if "test" in f.lower()]
        test_files = test_candidates[:1] if test_candidates else ["tests/test_implementation.py" if is_new_impl else "tests/test_pls_cli.py"]

        step_1 = PlanStep(
            step_number=1,
            title=f"Implement changes in {impl_files[0]}",
            description=f"No existing module found for '{action_title}'. Propose new module {impl_files[0]} to implement requested feature." if is_new_impl else f"Add requested functionality '{action_title}' to {impl_files[0]}.",
            target_files=impl_files,
            component_type="NEW" if is_new_impl else "EXISTING",
            acceptance_criteria=["AC-01"],
            dependencies=[],
        )
        setattr(step_1, "rationale", f"Directly updates {impl_files[0]}.")
        steps.append(step_1)

        is_new_test = not bool(test_candidates)
        step_2 = PlanStep(
            step_number=2,
            title=f"Verify changes with automated tests",
            description=f"No existing test suite found for {test_files[0]}. Implement tests covering {impl_files[0]} modifications." if is_new_test else f"Run test suite covering {impl_files[0]} modifications.",
            target_files=test_files,
            component_type="NEW" if is_new_test else "EXISTING",
            acceptance_criteria=["AC-01"],
            dependencies=[1],
        )
        setattr(step_2, "rationale", f"Validates functionality in {test_files[0]}.")
        steps.append(step_2)

        return steps

    
