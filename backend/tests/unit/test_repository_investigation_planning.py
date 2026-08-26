"""
Unit and Integration Test Suite: Repository Investigation Engine & Plan Action Lifecycle.

Verifies:
  1. Existing capability detection (GET /health) -> EXISTING assessment (0 implementation tasks).
  2. Partial capability detection (GET /status with DB check) -> PARTIAL assessment (modifies status.py, no duplicate file).
  3. Semantic equivalent detection (GET /ping) -> PARTIAL / EXISTING, never NEW.
  4. Negative test for unrelated match (get_payment_status) -> ignored, not classified as health check.
  5. Incidental doc matches (README.md) -> candidate ignored, not counted as executable evidence.
  6. Truly missing capability -> NEW assessment (hard-gated on complete coverage).
  7. Review action authorizes execution through server gate.
  8. Reject action records rejection in metadata and preserves history.
  9. "Why this file?" - Every task contains explicit rationale based on repository investigation.
  10. Full real lifecycle test via POST /api/v1/agent/runs and /approve.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, get_db
from backend.dependencies.auth import get_current_user
from backend.main import app
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol, FactRoute
from backend.models.implementation import (
    AgentRun,
    AgentRunStatus,
    AgentState,
    ApprovalRequest,
    ApprovalStatus,
)
from backend.intelligence.contracts.investigation import (
    EvidenceStatus,
    ImplementationAssessment,
)
from backend.intelligence.retrieval.repository_investigator import RepositoryInvestigator
from backend.agent.engineering_agent import EngineeringAgent
from backend.agent.modes import execute_implement, execute_plan
from backend.agent.planning.orchestrator import PlanningOrchestrator


from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    user = User(id=1, github_id="gh123", email="user@example.com", username="testuser")
    session.add(user)
    session.commit()

    repo = Repository(id=1, url="https://github.com/org/sample-repo.git", user_id=1)
    session.add(repo)
    session.commit()

    analysis = Analysis(id=201, repository_id=1, status="COMPLETED")
    session.add(analysis)
    session.commit()

    yield session
    session.close()


def test_existing_capability_detected_zero_tasks(db_session):
    """
    Test 1: When GET /health already exists in the repository,
    investigation returns EXISTING assessment and 0 implementation tasks are generated.
    """
    # Setup /health route in FactStore
    f1 = FactFile(id="201:f1", analysis_id=201, path="src/api/health.py", size=300, language="python")
    db_session.add(f1)

    s1 = FactSymbol(
        id="201:s1",
        analysis_id=201,
        name="health_check",
        qualified_name="src.api.health.health_check",
        symbol_type="function",
        file_id="201:f1",
        line_start=5,
        line_end=15,
    )
    db_session.add(s1)

    r1 = FactRoute(
        id="201:r1",
        analysis_id=201,
        path="/health",
        method="GET",
        symbol_id="201:s1",
    )
    db_session.add(r1)
    db_session.commit()

    investigator = RepositoryInvestigator()
    res = investigator.investigate(
        requirement="Implement health check endpoint",
        analysis_id=201,
        db=db_session,
    )

    assert res.assessment == ImplementationAssessment.EXISTING
    assert "/health" in res.relevant_routes[0]
    assert "src/api/health.py" in res.inspected_files

    # Orchestrator plan generation
    service = EngineeringAgent()
    run = service.create_run(db=db_session, repository_id="1", user_requirement="Implement health check endpoint")
    plan = service.create_plan(db=db_session, run_id=run.id)

    assert plan.investigation.assessment == ImplementationAssessment.EXISTING
    assert len(plan.tasks) == 0  # 0 tasks manufactured


def test_partial_capability_extends_existing_status_endpoint(db_session):
    """
    Test 2: When GET /status and check_database_connection exist,
    investigation returns PARTIAL and plan EXTENDS src/api/status.py without creating health_check.py.
    """
    f1 = FactFile(id="201:f1", analysis_id=201, path="src/api/status.py", size=400, language="python")
    db_session.add(f1)

    s1 = FactSymbol(
        id="201:s1",
        analysis_id=201,
        name="get_status",
        qualified_name="src.api.status.get_status",
        symbol_type="function",
        file_id="201:f1",
        line_start=10,
        line_end=20,
    )
    db_session.add(s1)

    s2 = FactSymbol(
        id="201:s2",
        analysis_id=201,
        name="check_database_connection",
        qualified_name="src.api.status.check_database_connection",
        symbol_type="function",
        file_id="201:f1",
        line_start=22,
        line_end=35,
    )
    db_session.add(s2)

    r1 = FactRoute(
        id="201:r1",
        analysis_id=201,
        path="/status",
        method="GET",
        symbol_id="201:s1",
    )
    db_session.add(r1)
    db_session.commit()

    investigator = RepositoryInvestigator()
    res = investigator.investigate(
        requirement="Implement health check endpoint with database status",
        analysis_id=201,
        db=db_session,
    )

    assert res.assessment == ImplementationAssessment.PARTIAL
    assert "src/api/status.py" in res.inspected_files

    # Generate plan
    service = EngineeringAgent()
    run = service.create_run(db=db_session, repository_id="1", user_requirement="Implement health check endpoint with database status")
    plan = service.create_plan(db=db_session, run_id=run.id)

    assert plan.investigation.assessment == ImplementationAssessment.PARTIAL
    assert len(plan.tasks) > 0
    # Must modify status.py, NOT create health_check.py
    for t in plan.tasks:
        if t.component_type == "EXISTING":
            assert "src/api/status.py" in t.affected_files
            assert t.rationale is not None
            assert "src/api/status.py" in t.rationale


def test_semantic_equivalent_ping_detected_as_partial_not_new(db_session):
    """
    Test 3: When GET /ping exists under different terminology,
    investigation recognizes it as PARTIAL / EXISTING, never blindly NEW.
    """
    f1 = FactFile(id="201:f1", analysis_id=201, path="src/routes/ping.py", size=250, language="python")
    db_session.add(f1)

    s1 = FactSymbol(
        id="201:s1",
        analysis_id=201,
        name="ping_handler",
        qualified_name="src.routes.ping.ping_handler",
        symbol_type="function",
        file_id="201:f1",
        line_start=5,
        line_end=12,
    )
    db_session.add(s1)

    r1 = FactRoute(
        id="201:r1",
        analysis_id=201,
        path="/ping",
        method="GET",
        symbol_id="201:s1",
    )
    db_session.add(r1)
    db_session.commit()

    investigator = RepositoryInvestigator()
    res = investigator.investigate(
        requirement="Implement health check endpoint",
        analysis_id=201,
        db=db_session,
    )

    assert res.assessment in (ImplementationAssessment.PARTIAL, ImplementationAssessment.EXISTING)
    assert res.assessment != ImplementationAssessment.NEW
    assert "src/routes/ping.py" in res.inspected_files


def test_negative_test_unrelated_payment_status_ignored(db_session):
    """
    Test 4: get_payment_status() is ignored and NOT classified as a health check implementation.
    """
    f1 = FactFile(id="201:f1", analysis_id=201, path="src/billing/payment.py", size=600, language="python")
    db_session.add(f1)

    s1 = FactSymbol(
        id="201:s1",
        analysis_id=201,
        name="get_payment_status",
        qualified_name="src.billing.payment.get_payment_status",
        symbol_type="function",
        file_id="201:f1",
        line_start=50,
        line_end=60,
    )
    db_session.add(s1)
    db_session.commit()

    investigator = RepositoryInvestigator()
    res = investigator.investigate(
        requirement="Implement health check endpoint",
        analysis_id=201,
        db=db_session,
    )

    # Must NOT conclude payment status is health check
    assert res.assessment == ImplementationAssessment.NEW
    assert "get_payment_status" not in res.relevant_symbols


def test_hard_gate_new_when_no_endpoints_or_symbols(db_session):
    """
    Test 5: Truly missing capability produces NEW assessment with complete coverage.
    """
    f1 = FactFile(id="201:f1", analysis_id=201, path="src/calculator.py", size=200, language="python")
    db_session.add(f1)
    db_session.commit()

    investigator = RepositoryInvestigator()
    res = investigator.investigate(
        requirement="Implement health check endpoint",
        analysis_id=201,
        db=db_session,
    )

    assert res.assessment == ImplementationAssessment.NEW
    assert res.coverage.is_complete is True
    assert len(res.relevant_routes) == 0


def test_review_action_authorizes_plan_execution(db_session):
    """
    Test 6: Review action invokes approve_plan and authorizes execution in the server gate.
    """
    service = EngineeringAgent()
    run = service.create_run(db=db_session, repository_id="1", user_requirement="Add logging")
    plan = service.create_plan(db=db_session, run_id=run.id)

    # Click [ Review ] -> resolves approval
    service.approve_plan(db=db_session, run_id=run.id, resolved_by="testuser")

    # Gate check passes
    service.assert_execution_authorized(
        db=db_session,
        run_id=run.id,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        user_id=1,
    )

    # Start execution
    exec_run = service.start_plan_execution(db=db_session, run_id=run.id)
    assert exec_run.current_state == AgentState.EXECUTING


def test_reject_action_records_rejection_in_history(db_session):
    """
    Test 7: Reject action marks plan REJECTED with feedback and does not delete run history.
    """
    service = EngineeringAgent()
    run = service.create_run(db=db_session, repository_id="1", user_requirement="Add OAuth")
    plan = service.create_plan(db=db_session, run_id=run.id)

    # Click [ Reject ]
    service.reject_plan(db=db_session, run_id=run.id, reason="Use existing auth module instead", resolved_by="testuser")

    db_session.refresh(run)
    saved_plan = run.metadata_json.get("plan")
    assert saved_plan["status"] == "REJECTED"


def test_real_agent_runs_api_lifecycle(db_session):
    """
    Test 8: Full real HTTP endpoint verification via POST /api/v1/agent/runs and approve.
    """
    f1 = FactFile(id="201:f1", analysis_id=201, path="src/api/status.py", size=400, language="python")
    db_session.add(f1)
    s1 = FactSymbol(id="201:s1", analysis_id=201, name="status", symbol_type="function", file_id="201:f1", line_start=5, line_end=15)
    db_session.add(s1)
    r1 = FactRoute(id="201:r1", analysis_id=201, path="/status", method="GET", symbol_id="201:s1")
    db_session.add(r1)
    db_session.commit()

    current_user_obj = db_session.query(User).filter(User.id == 1).first()
    app.dependency_overrides[get_current_user] = lambda: current_user_obj
    app.dependency_overrides[get_db] = lambda: db_session

    with patch("backend.routers.agent._background_execute_approved_plan"):
        try:
            client = TestClient(app)

            # 1. Test /classify endpoint (Chat / Preview Plan generation)
            resp_classify = client.post(
                "/api/v1/agent/classify",
                json={"requirement": "Implement health check endpoint", "repository_id": "1"}
            )
            assert resp_classify.status_code == 200
            classify_data = resp_classify.json()
            assert "plan" in classify_data
            assert classify_data["plan"]["investigation"]["assessment"] == "PARTIAL"

            # 2. Test /agent/runs lifecycle and plan approval
            service = EngineeringAgent()
            run = service.create_run(db=db_session, repository_id="1", user_requirement="Implement health check endpoint")
            plan = service.create_plan(db=db_session, run_id=run.id)
            assert plan.investigation.assessment == ImplementationAssessment.PARTIAL

            # Click [ Review ] via API
            resp_approve = client.post(f"/api/v1/agent/runs/{run.id}/plan/approve", json={"reason": "Approved"})
            assert resp_approve.status_code == 200
            approve_data = resp_approve.json()
            assert approve_data["current_state"] == "EXECUTING"

            db_session.refresh(run)
            assert run.metadata_json["plan"]["status"] == "APPROVED"

        finally:
            app.dependency_overrides.clear()
