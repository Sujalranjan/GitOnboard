"""
REST API router for AI-assisted implementations (Version 4).

Endpoints:
  POST /api/repos/{repo_name}/implementations   — Start planning pipeline
  GET  /api/implementations/{id}               — Retrieve implementation with contract & plan
  POST /api/implementations/{id}/plan/regenerate — Re-run planning
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.ai.service import get_llm_service, LLMService
from backend.models.repository import Repository
from backend.models.implementation import (
    Implementation,
    ImplementationContract,
    ImplementationPlan,
    ImplementationStatus,
    ComponentType,
    PlanStepStatus,
)
from backend.planning.requirements import RequirementAnalyzer
from backend.planning.impact_analysis import ImpactAnalyzer, PlanningStatus
from backend.planning.contract import ContractGenerator
from backend.planning.planner import StepPlanner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["implementations"])


# ──────────────────────────────────────────────────────────────────────────────
# Request / Response schemas
# ──────────────────────────────────────────────────────────────────────────────

class StartImplementationRequest(BaseModel):
    requirement: str
    branch_name: Optional[str] = None


class PlanStepResponse(BaseModel):
    id: str
    step_number: int
    title: str
    description: str
    target_files: List[str]
    affected_symbols: List[str]
    component_type: str
    acceptance_criteria: List[str]
    evidence_ids: List[str]
    expected_changes: Optional[str]
    dependencies: List[Any]
    status: str


class ContractResponse(BaseModel):
    id: str
    acceptance_criteria: List[Any]
    affected_components: List[Any]
    evidence_manifest: List[Any]
    tests_required: List[str]
    security_considerations: List[str]


class ImplementationResponse(BaseModel):
    id: str
    repository_id: int
    title: str
    raw_requirement: str
    branch_name: Optional[str]
    status: str
    contract: Optional[ContractResponse]
    plan_steps: List[PlanStepResponse]
    created_at: str
    updated_at: str


# ──────────────────────────────────────────────────────────────────────────────
# Background planning task
# ──────────────────────────────────────────────────────────────────────────────

async def _run_planning_pipeline(
    implementation_id: str,
    requirement: str,
    db: Session,
    llm: LLMService,
) -> None:
    """
    Full planning pipeline (runs in background):
    1. RequirementAnalyzer -> AnalyzedRequirement
    2. ImpactAnalyzer -> ImpactResult (+ NEEDS_CONTEXT check)
    3. ContractGenerator -> ContractOutput
    4. StepPlanner -> List[PlanStep]
    5. Persist to database
    """
    impl = db.query(Implementation).filter(Implementation.id == implementation_id).first()
    if not impl:
        logger.error(f"Planning pipeline: Implementation {implementation_id} not found.")
        return

    try:
        # Step 1 — Requirement Analysis
        impl.status = ImplementationStatus.PLANNING
        db.commit()

        analyzer = RequirementAnalyzer(llm)
        analyzed = await analyzer.analyze(requirement)

        # Step 2 — Impact Analysis
        keywords = [w.lower() for w in analyzed.title.split() if len(w) > 3]
        impact_analyzer = ImpactAnalyzer(db=db, analysis_id=0)  # analysis_id resolved below
        # Resolve latest analysis_id for the repository
        from backend.models.repository import Analysis
        latest_analysis = (
            db.query(Analysis)
            .filter(Analysis.repository_id == impl.repository_id)
            .order_by(Analysis.created_at.desc())
            .first()
        )
        if latest_analysis:
            impact_analyzer.analysis_id = latest_analysis.id

        impact = await impact_analyzer.analyze(keywords=keywords)

        if impact.status == PlanningStatus.NEEDS_CONTEXT:
            impl.status = ImplementationStatus.NEEDS_CONTEXT
            db.commit()
            logger.warning(f"Planning pipeline: NEEDS_CONTEXT for {implementation_id}. Insufficient evidence.")
            return

        # Step 3 — Contract Generation
        contract_gen = ContractGenerator(llm)
        contract_output = await contract_gen.generate(analyzed, impact)

        # Step 4 — Step Planning
        planner = StepPlanner(llm)
        plan_steps = await planner.plan(analyzed, impact, contract_output)

        # Step 5 — Persist
        impl.title = analyzed.title
        impl.status = ImplementationStatus.READY

        # Save contract
        contract = ImplementationContract(
            implementation_id=implementation_id,
            acceptance_criteria=[c.dict() for c in analyzed.acceptance_criteria],
            affected_components=[c.dict() for c in contract_output.affected_components],
            evidence_manifest=[e.to_dict() for e in impact.evidence_items],
            tests_required=contract_output.tests_required,
            security_considerations=contract_output.security_considerations,
        )
        db.add(contract)

        # Save plan steps
        for step in plan_steps:
            plan_row = ImplementationPlan(
                implementation_id=implementation_id,
                step_number=step.step_number,
                title=step.title,
                description=step.description,
                target_files=step.target_files,
                affected_symbols=step.affected_symbols,
                component_type=ComponentType(step.component_type) if step.component_type in ("EXISTING", "NEW") else ComponentType.EXISTING,
                acceptance_criteria=step.acceptance_criteria,
                evidence_ids=step.evidence_ids,
                expected_changes=step.expected_changes,
                dependencies=step.dependencies,
            )
            db.add(plan_row)

        db.commit()
        logger.info(f"Planning pipeline: READY for {implementation_id} ({len(plan_steps)} steps).")

    except Exception as e:
        logger.exception(f"Planning pipeline FAILED for {implementation_id}: {e}")
        if impl:
            impl.status = ImplementationStatus.FAILED
            db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/repos/{repo_name}/implementations",
    response_model=ImplementationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an AI-assisted implementation",
)
async def start_implementation(
    repo_name: str,
    body: StartImplementationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
) -> ImplementationResponse:
    """
    Submit a natural language requirement to start the planning pipeline.
    Returns immediately with status=QUEUED; planning runs in the background.
    """
    # Resolve repository
    repo = db.query(Repository).filter(Repository.url.contains(repo_name)).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found.")

    impl = Implementation(
        repository_id=repo.id,
        title=body.requirement[:80],  # Placeholder until analyzer runs
        raw_requirement=body.requirement,
        branch_name=body.branch_name,
        status=ImplementationStatus.QUEUED,
    )
    db.add(impl)
    db.commit()
    db.refresh(impl)

    background_tasks.add_task(_run_planning_pipeline, impl.id, body.requirement, db, llm)

    return _serialize_impl(impl)


@router.get(
    "/implementations/{implementation_id}",
    response_model=ImplementationResponse,
    summary="Get implementation with contract and plan",
)
async def get_implementation(
    implementation_id: str,
    db: Session = Depends(get_db),
) -> ImplementationResponse:
    impl = db.query(Implementation).filter(Implementation.id == implementation_id).first()
    if not impl:
        raise HTTPException(status_code=404, detail="Implementation not found.")
    return _serialize_impl(impl)


@router.post(
    "/implementations/{implementation_id}/plan/regenerate",
    response_model=ImplementationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run impact analysis and planning",
)
async def regenerate_plan(
    implementation_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm_service),
) -> ImplementationResponse:
    impl = db.query(Implementation).filter(Implementation.id == implementation_id).first()
    if not impl:
        raise HTTPException(status_code=404, detail="Implementation not found.")

    # Clear existing contract and steps
    db.query(ImplementationContract).filter(
        ImplementationContract.implementation_id == implementation_id
    ).delete()
    db.query(ImplementationPlan).filter(
        ImplementationPlan.implementation_id == implementation_id
    ).delete()
    impl.status = ImplementationStatus.QUEUED
    db.commit()

    background_tasks.add_task(_run_planning_pipeline, impl.id, impl.raw_requirement, db, llm)
    db.refresh(impl)
    return _serialize_impl(impl)


# ──────────────────────────────────────────────────────────────────────────────
# Serialization helper
# ──────────────────────────────────────────────────────────────────────────────

def _serialize_impl(impl: Implementation) -> ImplementationResponse:
    contract = None
    if impl.contract:
        c = impl.contract
        contract = ContractResponse(
            id=c.id,
            acceptance_criteria=c.acceptance_criteria or [],
            affected_components=c.affected_components or [],
            evidence_manifest=c.evidence_manifest or [],
            tests_required=c.tests_required or [],
            security_considerations=c.security_considerations or [],
        )

    plan_steps = []
    for step in (impl.plan_steps or []):
        plan_steps.append(PlanStepResponse(
            id=step.id,
            step_number=step.step_number,
            title=step.title,
            description=step.description,
            target_files=step.target_files or [],
            affected_symbols=step.affected_symbols or [],
            component_type=step.component_type.value if step.component_type else "EXISTING",
            acceptance_criteria=step.acceptance_criteria or [],
            evidence_ids=step.evidence_ids or [],
            expected_changes=step.expected_changes,
            dependencies=step.dependencies or [],
            status=step.status.value if step.status else "PENDING",
        ))

    return ImplementationResponse(
        id=impl.id,
        repository_id=impl.repository_id,
        title=impl.title,
        raw_requirement=impl.raw_requirement,
        branch_name=impl.branch_name,
        status=impl.status.value if impl.status else "QUEUED",
        contract=contract,
        plan_steps=plan_steps,
        created_at=impl.created_at.isoformat() if impl.created_at else "",
        updated_at=impl.updated_at.isoformat() if impl.updated_at else "",
    )
