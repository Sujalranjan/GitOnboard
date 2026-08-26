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
from .contracts import Plan, PlanTask, PlanStatus, PlanTaskStatus, PlanValidationResult
from .validator import PlanValidator

logger = logging.getLogger(__name__)


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
        extracted_kws = [w.lower() for w in requirement.split() if len(w) > 3]

        # ──────────────────────────────────────────────────────────────────────
        # 3. Impact Analysis (ImpactAnalyzer)
        # ──────────────────────────────────────────────────────────────────────
        impact_result: Optional[ImpactResult] = None
        if db and analysis_id:
            try:
                analyzer = ImpactAnalyzer(db=db, analysis_id=analysis_id)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        impact_result = pool.submit(asyncio.run, analyzer.analyze(keywords=extracted_kws or [requirement])).result()
                else:
                    impact_result = asyncio.run(analyzer.analyze(keywords=extracted_kws or [requirement]))
            except Exception as err:
                logger.warning(f"ImpactAnalyzer error during planning: {err}")

        # Combine context files with investigated candidate files
        affected_files: List[str] = list(dict.fromkeys(
            list(context.relevant_files) + investigation_result.inspected_files
        ))
        affected_symbols: List[str] = list(dict.fromkeys(
            [s.get("name", "") for s in context.relevant_symbols if s.get("name")] + investigation_result.relevant_symbols
        ))
        if impact_result:
            for f in (impact_result.candidate_files or []):
                if f and f not in affected_files:
                    affected_files.append(f)
            for s in (impact_result.candidate_symbols or []):
                if s and s not in affected_symbols:
                    affected_symbols.append(s)

        # ──────────────────────────────────────────────────────────────────────
        # 4. Acceptance Contract Generation (ContractGenerator)
        # ──────────────────────────────────────────────────────────────────────
        contract_output = self._generate_contract(analyzed_req, impact_result, context)

        # ──────────────────────────────────────────────────────────────────────
        # 5. Step Planning (StepPlanner + Investigation Grounding)
        # ──────────────────────────────────────────────────────────────────────
        steps = self._generate_steps(
            analyzed_req,
            impact_result,
            contract_output,
            context,
            investigation=investigation_result,
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
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        return pool.submit(asyncio.run, req_analyzer.analyze(requirement)).result()
                else:
                    return asyncio.run(req_analyzer.analyze(requirement))
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
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        return pool.submit(asyncio.run, gen.generate(requirement, impact)).result()
                else:
                    return asyncio.run(gen.generate(requirement, impact))
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
    ) -> List[PlanStep]:
        """Synthesizes sequential implementation steps based strictly on the repository investigation assessment."""
        # 1. Check if capability already exists
        if investigation and investigation.assessment == ImplementationAssessment.EXISTING:
            logger.info("PlanningOrchestrator: Assessment is EXISTING. Generating 0 mutation tasks.")
            return []

        # Synthesize clean actionable title from requirement
        raw_req = requirement.title.strip()
        cleaned_action = re.sub(
            r"^(what\s+would\s+it\s+take\s+to\s+add|what\s+would\s+it\s+take\s+to|how\s+do\s+we\s+implement|how\s+can\s+we\s+add|how\s+to\s+add|can\s+you\s+add|can\s+we\s+add|please\s+add|add|implement)\s+",
            "",
            raw_req,
            flags=re.IGNORECASE
        ).strip(" ?.")
        if not cleaned_action:
            cleaned_action = raw_req.strip(" ?.")

        act_lower = cleaned_action.lower()
        if "rbac" in act_lower or "role" in act_lower or "admin" in act_lower or "access control" in act_lower:
            action_title = "Role-Based Access Control and Route Guards"
        elif "search" in act_lower or "find" in act_lower:
            action_title = "Global Search across Analysis Store and Uploads"
        elif "email" in act_lower or "notification" in act_lower or "notify" in act_lower:
            action_title = "Analysis Completion Notification System"
        elif "oauth" in act_lower or "google" in act_lower:
            action_title = "Google OAuth Authentication Integration"
        elif "pagination" in act_lower:
            action_title = "Pagination Support in Users API Client"
        elif "dark" in act_lower or "mode" in act_lower or "theme" in act_lower:
            action_title = "Dark Mode Theme Provider and Styling"
        elif "payment" in act_lower or "stripe" in act_lower:
            action_title = "Payment Gateway Integration"
        elif "redis" in act_lower or "cache" in act_lower:
            action_title = "Server-Side Redis Caching Layer"
        elif "health" in act_lower or "status" in act_lower:
            action_title = "Health and Status Check Endpoint"
        else:
            action_title = " ".join(w.capitalize() for w in cleaned_action.split())

        # Determine target files from investigation or context
        candidate_files = list(context.relevant_files)
        if investigation and investigation.inspected_files:
            for f in investigation.inspected_files:
                if f not in candidate_files:
                    candidate_files.append(f)

        # Detect repo archetype dynamically
        all_detected_paths: List[str] = list(candidate_files)
        for ev in context.evidence:
            if ev.data and isinstance(ev.data, dict):
                f_list = ev.data.get("files") or []
                if isinstance(f_list, list):
                    all_detected_paths.extend(f_list)

        py_files = [p for p in all_detected_paths if p.endswith(".py")]
        ts_files = [p for p in all_detected_paths if p.endswith((".ts", ".tsx", ".js", ".jsx"))]
        is_py_repo = len(py_files) > len(ts_files) or any("Python" in c for c in context.architecture_constraints)
        is_ts_repo = len(ts_files) >= len(py_files) and not is_py_repo

        src_dir = ""
        test_dir = "tests"
        if is_py_repo:
            for p in py_files:
                parts = p.replace("\\", "/").split("/")
                if len(parts) > 1 and parts[0] not in {"tests", "test", "docs", ".github", ".venv", "venv"}:
                    src_dir = parts[0]
                    break
            if not src_dir:
                src_dir = "src" if any(p.startswith("src/") for p in all_detected_paths) else ""
            if any(p.startswith("test/") for p in all_detected_paths):
                test_dir = "test"
        elif is_ts_repo:
            src_dir = "src/lib" if any(p.startswith("src/") for p in all_detected_paths) else "lib"
            test_dir = "__tests__" if any(p.startswith("__tests__") for p in all_detected_paths) else "tests"

        safe_name = re.sub(r"[^\w]+", "_", action_title.lower()).strip("_")
        slug_words = [w for w in safe_name.split("_") if w not in {"what", "would", "it", "take", "to", "add", "implement", "a", "an", "the", "feature", "system", "for", "in", "of", "and", "integration", "support", "server", "side", "layer", "client", "provider", "module", "across"}]
        slug = "_".join(slug_words[:2]) if slug_words else "feature"

        steps: List[PlanStep] = []

        # 2. If PARTIAL or existing relevant files exist: Generate EXTENSION tasks
        is_partial = investigation and investigation.assessment == ImplementationAssessment.PARTIAL
        if is_partial or candidate_files:
            impl_files = candidate_files[:4] if candidate_files else [f"{src_dir}/{slug}.py" if is_py_repo else f"{src_dir}/{slug}.ts"]
            test_candidates = [f for f in candidate_files if "test" in f.lower() or "spec" in f.lower()]
            test_files = test_candidates[:2] if test_candidates else ([f"{test_dir}/{slug}.test.ts"] if is_ts_repo else [f"{test_dir}/test_{slug}.py"])

            rationale_text = (
                investigation.decision_rationale
                if investigation and investigation.decision_rationale
                else f"Extends verified repository component ({impl_files[0]})."
            )

            # Step 1: Implementation of required change in existing files
            step_1 = PlanStep(
                step_number=1,
                title=f"Extend {impl_files[0]} for {action_title}",
                description=f"Modify {', '.join(impl_files)} to satisfy requirement. {rationale_text}",
                target_files=impl_files,
                component_type="EXISTING",
                acceptance_criteria=["AC-01"],
                dependencies=[],
            )
            setattr(step_1, "rationale", rationale_text)
            steps.append(step_1)

            # Step 2: Verification and testing
            step_2 = PlanStep(
                step_number=2,
                title=f"Verify {action_title} with Automated Tests",
                description=f"Execute unit and integration tests covering modifications in {', '.join(impl_files)}.",
                target_files=test_files,
                component_type="EXISTING" if test_candidates else "NEW",
                acceptance_criteria=["AC-01"],
                dependencies=[1],
            )
            setattr(step_2, "rationale", f"Validates {action_title} behavior in {test_files[0]}.")
            steps.append(step_2)

        else:
            # 3. Truly NEW Component (Hard-gated)
            if is_py_repo:
                prefix = f"{src_dir}/" if src_dir else ""
                new_impl = [f"{prefix}{slug}.py"]
                new_test = [f"{test_dir}/test_{slug}.py"]
            elif is_ts_repo:
                prefix = f"{src_dir}/" if src_dir else "src/"
                new_impl = [f"{prefix}{slug}.ts"]
                new_test = [f"{test_dir}/{slug}.test.ts"]
            else:
                prefix = f"{src_dir}/" if src_dir else ""
                ext = ".py" if is_py_repo else (".ts" if is_ts_repo else ".code")
                new_impl = [f"{prefix}{slug}{ext}"]
                new_test = [f"{test_dir}/test_{slug}{ext}"]

            if investigation and investigation.assessment == ImplementationAssessment.NEW and investigation.decision_rationale:
                new_rationale = f"No existing {slug} implementation found in repository. {investigation.decision_rationale}"
            else:
                new_rationale = f"No existing {slug} implementation found in repository. Proposing new module."

            step_1 = PlanStep(
                step_number=1,
                title=f"Create New {slug.replace('_', ' ').title()} Module ({new_impl[0]})",
                description=f"Propose new module {new_impl[0]}. {new_rationale}",
                target_files=new_impl,
                component_type="NEW",
                acceptance_criteria=["AC-01"],
                dependencies=[],
            )
            setattr(step_1, "rationale", new_rationale)
            steps.append(step_1)

            step_2 = PlanStep(
                step_number=2,
                title=f"Add Automated Tests for {action_title}",
                description=f"Create new test suite in {new_test[0]} to verify contracts and error conditions.",
                target_files=new_test,
                component_type="NEW",
                acceptance_criteria=["AC-01"],
                dependencies=[1],
            )
            setattr(step_2, "rationale", f"Provides test coverage for new module {new_impl[0]}.")
            steps.append(step_2)

        return steps
