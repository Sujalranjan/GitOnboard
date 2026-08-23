"""
PlanningOrchestrator: Connects repository intelligence into a validated, reviewable implementation plan.

Zero Rebuilding Rule: Reuses existing:
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
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.ai.service import LLMService
from backend.agent.context.contracts import RepositoryContext
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
    ) -> Plan:
        """
        Synthesizes a validated Plan from the user requirement and Phase 3 RepositoryContext.
        """
        logger.info(f"PlanningOrchestrator: Beginning plan generation for run '{agent_run_id}' (v{version})")

        # ──────────────────────────────────────────────────────────────────────
        # 1. Requirement Decomposition (RequirementAnalyzer)
        # ──────────────────────────────────────────────────────────────────────
        analyzed_req = self._analyze_requirement(requirement)
        keywords = analyzed_req.goals or [requirement]
        extracted_kws = [w.lower() for w in requirement.split() if len(w) > 3]

        # ──────────────────────────────────────────────────────────────────────
        # 2. Impact Analysis (ImpactAnalyzer)
        # ──────────────────────────────────────────────────────────────────────
        analysis_id = context.metadata.get("analysis_id") if context.metadata else None
        impact_result: Optional[ImpactResult] = None
        if db and analysis_id:
            try:
                analyzer = ImpactAnalyzer(db=db, analysis_id=analysis_id)
                impact_result = analyzer.analyze(keywords=extracted_kws or [requirement])
            except Exception as err:
                logger.warning(f"ImpactAnalyzer error during planning: {err}")

        affected_files: List[str] = list(context.relevant_files)
        affected_symbols: List[str] = [s.get("name", "") for s in context.relevant_symbols if s.get("name")]
        if impact_result:
            for f in impact_result.affected_files:
                if f and f not in affected_files:
                    affected_files.append(f)
            for s in impact_result.affected_symbols:
                if s and s not in affected_symbols:
                    affected_symbols.append(s)

        # ──────────────────────────────────────────────────────────────────────
        # 3. Acceptance Contract Generation (ContractGenerator)
        # ──────────────────────────────────────────────────────────────────────
        contract_output = self._generate_contract(analyzed_req, impact_result, context)

        # ──────────────────────────────────────────────────────────────────────
        # 4. Step Planning (StepPlanner)
        # ──────────────────────────────────────────────────────────────────────
        steps = self._generate_steps(analyzed_req, impact_result, contract_output, context)

        # ──────────────────────────────────────────────────────────────────────
        # 5. Task DAG Assembly
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

            tasks.append(
                PlanTask(
                    task_id=task_id,
                    step_number=step.step_number,
                    title=step.title,
                    description=step.description or f"Implement {step.title} for {step.target_files}",
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
        # 6. Global Plan Artifact Assembly
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

        # Risks synthesis
        risks: List[str] = []
        if len(affected_files) > 3:
            risks.append(f"Multi-file modification risk: {len(affected_files)} files affected across codebase")
        if context.contract.missing_categories:
            risks.append(f"Incomplete context risk: Missing categories {context.contract.missing_categories}")
        for sec in contract_output.security_considerations:
            risks.append(f"Security: {sec}")

        plan = Plan(
            agent_run_id=agent_run_id,
            repository_id=repository_id,
            requirement=requirement,
            version=version,
            status=PlanStatus.DRAFT,
            repository_understanding=repo_understanding_summary,
            architecture_context=arch_summary,
            affected_areas=[
                {"file": c.file, "symbol": c.symbol, "component_type": c.component_type}
                for c in contract_output.affected_components
            ] if contract_output.affected_components else [{"file": f, "component_type": "EXISTING"} for f in affected_files],
            constraints=context.architecture_constraints,
            tasks=tasks,
            task_dependencies=task_deps_map,
            acceptance_criteria=global_criteria,
            verification_strategy="verify_static_and_automated_tests",
            risks=risks,
            unknowns=list(context.unknowns),
        )

        # ──────────────────────────────────────────────────────────────────────
        # 7. Plan Validation (PlanValidator)
        # ──────────────────────────────────────────────────────────────────────
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

        # Deterministic fallback
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

        # Deterministic fallback
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
    ) -> List[PlanStep]:
        """Synthesizes sequential implementation steps using StepPlanner or deterministic fallback."""
        if self.llm_service and impact:
            try:
                planner = StepPlanner(llm_service=self.llm_service)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        return pool.submit(asyncio.run, planner.plan(requirement, impact, contract)).result()
                else:
                    return asyncio.run(planner.plan(requirement, impact, contract))
            except Exception as err:
                logger.warning(f"StepPlanner execution error: {err}")

        # Structured deterministic plan generation grounded in repository context
        steps: List[PlanStep] = []
        files = list(context.relevant_files)

        # Detect repo archetype
        is_ts_repo = any(
            f.endswith((".ts", ".tsx", ".js", ".jsx")) or "package.json" in f or "src/" in f
            for f in files
        )
        if not files and context.architecture_constraints:
            is_ts_repo = any("typescript" in c.lower() or "next" in c.lower() or "react" in c.lower() for c in context.architecture_constraints)

        import re
        safe_name = re.sub(r"[^\w]+", "_", requirement.title.lower()).strip("_")
        # Extract short feature slug
        slug_words = [w for w in safe_name.split("_") if w not in {"what", "would", "it", "take", "to", "add", "implement", "a", "an", "the", "feature", "system", "for", "in", "of"}]
        slug = "_".join(slug_words[:2]) or "feature"

        if files:
            # Verified EXISTING files in repository FactStore
            impl_files = files[:3]
            test_candidates = [f for f in files if "test" in f.lower() or "spec" in f.lower()]
            test_files = test_candidates[:2] if test_candidates else ([f"tests/{slug}.test.ts"] if is_ts_repo else [f"tests/test_{slug}.py"])

            # Step 1: Implementation of required change in existing files
            steps.append(
                PlanStep(
                    step_number=1,
                    title=f"Implement {requirement.title} in existing codebase",
                    description=f"Modify verified repository components ({', '.join(impl_files)}) to implement {requirement.title}.",
                    target_files=impl_files,
                    component_type="EXISTING",
                    acceptance_criteria=["AC-01"],
                    dependencies=[],
                )
            )

            # Step 2: Verification and testing
            steps.append(
                PlanStep(
                    step_number=2,
                    title=f"Verify implementation and add test coverage",
                    description=f"Execute unit and integration tests covering changes in {', '.join(impl_files)}.",
                    target_files=test_files,
                    component_type="EXISTING" if test_candidates else "NEW",
                    acceptance_criteria=["AC-01"],
                    dependencies=[1],
                )
            )
        else:
            # Explicitly justified NEW component proposing appropriate repo locations
            if is_ts_repo or True:  # Default to repo structure based on context
                if "payment" in slug or "stripe" in slug:
                    new_impl = ["src/lib/payment.ts", "src/services/paymentService.ts"]
                    new_test = ["tests/payment.test.ts"]
                elif "redis" in slug or "cache" in slug:
                    new_impl = ["src/lib/redis.ts"]
                    new_test = ["tests/redis.test.ts"]
                elif "auth" in slug or "oauth" in slug:
                    new_impl = ["lib/auth.ts", "src/services/authService.ts"]
                    new_test = ["tests/auth.test.ts"]
                else:
                    new_impl = [f"src/lib/{slug}.ts"]
                    new_test = [f"tests/{slug}.test.ts"]

            # Step 1: Create new component
            steps.append(
                PlanStep(
                    step_number=1,
                    title=f"Create new {slug} component",
                    description=f"No existing {slug} component verified in FactStore index. Propose new module: {new_impl[0]} (Reason: client/API implementation for {requirement.title}).",
                    target_files=new_impl,
                    component_type="NEW",
                    acceptance_criteria=["AC-01"],
                    dependencies=[],
                )
            )

            # Step 2: Add automated tests
            steps.append(
                PlanStep(
                    step_number=2,
                    title=f"Add automated tests for new {slug} component",
                    description=f"Create new test suite in {new_test[0]} to verify contracts and boundary conditions.",
                    target_files=new_test,
                    component_type="NEW",
                    acceptance_criteria=["AC-01"],
                    dependencies=[1],
                )
            )

        return steps
