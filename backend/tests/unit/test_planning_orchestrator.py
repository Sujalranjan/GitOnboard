"""
Unit tests for PlanningOrchestrator (Phase 4).
"""
import pytest
from backend.agent.context.contracts import (
    CompletenessStatus,
    ContextBudget,
    ContextEvidence,
    RepositoryContext,
    RepositoryUnderstandingContract,
)
from backend.agent.planning.contracts import PlanStatus
from backend.agent.planning.orchestrator import PlanningOrchestrator


def test_planning_orchestrator_basic_flow():
    orchestrator = PlanningOrchestrator()

    contract = RepositoryUnderstandingContract(
        completeness=CompletenessStatus.COMPLETE,
        satisfied_categories=["entrypoints_or_routes", "symbols_or_files", "dependencies_or_models", "capabilities"],
        missing_categories=[],
        explanation="All required categories discovered.",
    )

    ctx = RepositoryContext(
        repository_id="test_repo",
        requirement="Add user login validation",
        contract=contract,
        capabilities=[{"name": "Authentication", "status": "CONFIRMED"}],
        relevant_files=["auth/login.py", "auth/validation.py"],
        relevant_symbols=[{"name": "login_user", "file_path": "auth/login.py"}],
        unknowns=["Session timeout not configured in repository"],
    )

    plan = orchestrator.create_plan(
        context=ctx,
        agent_run_id="run_test_plan",
        repository_id="test_repo",
        requirement="Add user login validation",
        version=1,
    )

    assert plan.plan_id.startswith("plan_")
    assert plan.version == 1
    assert plan.status == PlanStatus.READY_FOR_APPROVAL
    assert len(plan.tasks) >= 2
    assert plan.validation is not None
    assert plan.validation.valid is True
    assert "Session timeout not configured in repository" in plan.unknowns


def test_planning_orchestrator_unknown_propagation():
    orchestrator = PlanningOrchestrator()

    contract = RepositoryUnderstandingContract(
        completeness=CompletenessStatus.PARTIAL,
        satisfied_categories=["dependencies_or_models"],
        missing_categories=["capabilities"],
        explanation="Missing capabilities.",
    )

    ctx = RepositoryContext(
        repository_id="test_repo",
        requirement="Add quantum blockchain algorithm",
        contract=contract,
        unknowns=["No existing quantum blockchain capability found"],
    )

    plan = orchestrator.create_plan(
        context=ctx,
        agent_run_id="run_quantum",
        repository_id="test_repo",
        requirement="Add quantum blockchain algorithm",
    )

    assert plan.status == PlanStatus.READY_FOR_APPROVAL
    assert "No existing quantum blockchain capability found" in plan.unknowns
    assert plan.validation.valid is True
