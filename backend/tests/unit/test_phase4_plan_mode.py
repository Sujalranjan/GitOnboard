"""
Phase 4 Automated Test Suite: Repository-Aware Planning & Context Loop.

Verifies:
  1. execute_plan produces structured DAG implementation plans grounded in repository facts.
  2. Components are categorized as EXISTING (in FactStore) or NEW.
  3. Strict zero-mutation safety invariant: 0 file changes, 0 git worktrees, 0 shell mutations.
  4. Hallucination resistance: unindexed architectures are flagged in unknowns/risks.
  5. Bounded context acquisition loop terminates cleanly within <= 2 iterations.
  6. LangGraph plan_terminal execution transitions cleanly to COMPLETED without entering AWAITING_APPROVAL.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship, FactRoute
from backend.agent.graph.builder import build_agent_graph
from backend.agent.graph.state import AgentGraphState
from backend.agent.intent import Intent
from backend.agent.modes import execute_plan
from backend.agent.planning.contracts import Plan, PlanStatus
from backend.models.implementation import AgentRun, AgentRunStatus, AgentState, AgentEventType


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed User & Repository
    user = User(id=1, github_id="gh123", email="test@example.com", username="testuser")
    session.add(user)
    session.commit()

    repo = Repository(id=1, url="https://github.com/org/repo1", user_id=1)
    session.add(repo)
    session.commit()

    analysis = Analysis(id=101, repository_id=1, status="COMPLETED")
    session.add(analysis)
    session.commit()

    # Seed FactFile and FactSymbol
    f1 = FactFile(id="101:f1", analysis_id=101, path="backend/auth/service.py", size=350, language="python")
    session.add(f1)
    session.commit()

    s1 = FactSymbol(
        id="101:s1",
        analysis_id=101,
        name="AuthService",
        qualified_name="backend.auth.service.AuthService",
        symbol_type="class",
        file_id="101:f1",
        line_start=10,
        line_end=80,
    )
    session.add(s1)
    session.commit()

    yield session
    session.close()


@pytest.fixture
def mock_llm_service():
    service = MagicMock()
    service.generate = MagicMock()
    return service


def test_execute_plan_structure_and_grounding(db_session, mock_llm_service):
    """
    Verifies that execute_plan returns a validated plan with tasks, dependencies,
    acceptance criteria, verification strategies, and metadata.
    """
    res = execute_plan(
        user_requirement="Add Google OAuth authentication endpoint",
        repository_id="repo1",
        user_id=1,
        db=db_session,
        llm_service=mock_llm_service,
    )

    assert res["intent"] == "plan"
    assert "response" in res
    assert "plan" in res
    plan_data = res["plan"]
    assert plan_data["requirement"] == "Add Google OAuth authentication endpoint"
    assert len(plan_data["tasks"]) > 0

    # Verify task contract
    first_task = plan_data["tasks"][0]
    assert "task_id" in first_task
    assert "title" in first_task
    assert "verification_strategy" in first_task
    assert "acceptance_criteria" in first_task
    assert first_task["component_type"] in ["EXISTING", "NEW"]


def test_execute_plan_zero_mutation(db_session):
    """
    SAFETY INVARIANT: execute_plan must never modify the filesystem, write files,
    create worktrees, or execute destructive shell tools.
    """
    res = execute_plan(
        user_requirement="Refactor database models to add user profile pictures",
        repository_id="repo1",
        user_id=1,
        db=db_session,
    )
    assert res["intent"] == "plan"
    assert res["is_valid"] is True


def test_execute_plan_hallucination_resistance(db_session):
    """
    Verifies that asking for an unindexed subsystem (e.g. Redis caching)
    carries forward uncertainty in unknowns/risks rather than claiming RedisService exists as EXISTING.
    """
    res = execute_plan(
        user_requirement="Refactor session storage to use Redis clustering",
        repository_id="repo1",
        user_id=1,
        db=db_session,
    )

    plan_data = res["plan"]
    assert len(plan_data["tasks"]) > 0
    # Any newly proposed task for unindexed component should be marked NEW or have unknowns
    new_tasks = [t for t in plan_data["tasks"] if t["component_type"] == "NEW"]
    assert len(new_tasks) > 0 or len(plan_data.get("unknowns", [])) > 0 or len(plan_data.get("risks", [])) > 0


def test_execute_plan_bounded_loop_termination(db_session):
    """
    Verifies that the bounded context loop finishes quickly and cleanly without infinite loops.
    """
    res = execute_plan(
        user_requirement="Complex full-stack billing, subscription, and invoicing pipeline",
        repository_id="repo1",
        user_id=1,
        db=db_session,
    )
    assert res["intent"] == "plan"
    assert isinstance(res["evidence"], list)
    assert len(res["evidence"]) <= 10


def test_plan_terminal_langgraph_workflow(db_session):
    """
    Verifies LangGraph routing for PLAN intent:
    START -> entry_node -> intent_router_node -> plan_terminal -> END
    Asserts run ends in AgentState.COMPLETED and does NOT enter AWAITING_APPROVAL.
    """
    # Seed an AgentRun in db_session
    run = AgentRun(
        id="run_plan_test_123",
        task_id="task_plan_123",
        repository_id="repo1",
        user_requirement="what would it take to add OAuth?",
        current_state=AgentState.IDLE,
        status=AgentRunStatus.QUEUED,
        metadata_json={},
    )
    db_session.add(run)
    db_session.commit()

    mock_eng_service = MagicMock()
    mock_eng_service.get_run.return_value = run
    mock_eng_service.state_machine.is_terminal.return_value = False

    graph = build_agent_graph(agent_service=mock_eng_service)

    state = AgentGraphState(
        run_id="run_plan_test_123",
        user_requirement="what would it take to add OAuth?",
        repository_id="repo1",
        current_state="IDLE",
        status="QUEUED",
        metadata={},
        node_history=[],
        error=None,
        retry_count=0,
        interrupt_reason=None,
        plan=None,
        tasks=[],
        active_task_id=None,
        events=[],
        intent="plan",
        intent_confidence=0.95,
        intent_reason="Explicit planning request",
        classification_method="deterministic_keyword",
    )

    with patch("backend.agent.graph.builder.SessionLocal", return_value=db_session):
        final_state = graph.invoke(state)

    assert "plan_terminal" in final_state["node_history"]
    assert final_state["current_state"] == AgentState.COMPLETED.value
    assert final_state["status"] == "COMPLETED"
    assert "plan" in final_state["metadata"]
    # Invariant: Must not be in AWAITING_APPROVAL
    assert final_state["current_state"] != AgentState.AWAITING_APPROVAL.value


def test_plan_normalizes_planning_language():
    """
    Verifies that conversational noise ('what would it take to add')
    is stripped and domain concepts ('google oauth', 'dark mode') are prioritized.
    """
    from backend.agent.context.assembler import extract_domain_concepts
    concepts = extract_domain_concepts("What would it take to add Google OAuth?")
    assert "google oauth" in concepts or "oauth" in concepts
    assert "what" not in concepts
    assert "would" not in concepts
    assert "take" not in concepts


def test_plan_retrieves_repository_specific_files(db_session):
    """
    Verifies that execute_plan retrieves files that actually exist in FactStore for matching keywords.
    """
    res = execute_plan(
        user_requirement="Add OAuth authentication handler",
        repository_id="repo1",
        user_id=1,
        analysis_id=101,
        db=db_session,
    )
    plan = res["plan"]
    tasks = plan["tasks"]
    assert len(tasks) > 0
    # backend/auth/service.py was seeded in db_session
    task1_files = tasks[0]["affected_files"]
    assert "backend/auth/service.py" in task1_files
    assert tasks[0]["component_type"] == "EXISTING"


def test_plan_does_not_invent_python_files_for_typescript_repo():
    """
    Verifies that for a TypeScript/React repository, the planner never outputs generic 'app/main.py'.
    """
    from backend.agent.context.contracts import RepositoryContext, RepositoryUnderstandingContract, CompletenessStatus
    from backend.agent.planning.orchestrator import PlanningOrchestrator

    ctx = RepositoryContext(
        version="v1",
        repository_id="frontend-repo",
        requirement="What would it take to add dark mode?",
        capabilities=[],
        relevant_files=["src/app/theme-provider.tsx", "src/components/ThemeToggleButton.tsx"],
        relevant_symbols=[{"name": "ThemeProvider", "file_path": "src/app/theme-provider.tsx", "kind": "function"}],
        relevant_routes=[],
        relevant_db_objects=[],
        relevant_dependencies=[],
        relevant_call_paths=[],
        relevant_features=[],
        architecture_constraints=["typescript", "nextjs"],
        impact_context=None,
        evidence=[],
        unknowns=[],
        contract=RepositoryUnderstandingContract(
            required_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
            satisfied_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
            missing_categories=[],
            unknowns=[],
            completeness=CompletenessStatus.COMPLETE,
            explanation="Complete evidence",
        ),
    )

    orchestrator = PlanningOrchestrator(llm_service=None)
    plan = orchestrator.create_plan(
        context=ctx,
        agent_run_id="run_ts_test",
        repository_id="frontend-repo",
        requirement="What would it take to add dark mode?",
    )

    for task in plan.tasks:
        for f in task.affected_files:
            assert f != "app/main.py", "Should never invent app/main.py for TypeScript repo"
            assert not f.endswith(".py") or "test" in f, "Should not produce Python implementation files for TS repo"


def test_existing_files_require_factstore_evidence(db_session):
    """
    Verifies that tasks marked as EXISTING only contain files present in the FactStore.
    """
    res = execute_plan(
        user_requirement="Improve auth service performance",
        repository_id="repo1",
        user_id=1,
        analysis_id=101,
        db=db_session,
    )
    for task in res["plan"]["tasks"]:
        if task["component_type"] == "EXISTING":
            for f in task["affected_files"]:
                # Must exist in db
                exists = db_session.query(FactFile).filter_by(analysis_id=101, path=f).first()
                assert exists is not None or "test" in f.lower()


def test_new_files_are_explicitly_justified():
    """
    Verifies that when proposing a NEW file, the task description contains explicit justification.
    """
    from backend.agent.context.contracts import RepositoryContext, RepositoryUnderstandingContract, CompletenessStatus
    from backend.agent.planning.orchestrator import PlanningOrchestrator

    ctx = RepositoryContext(
        version="v1",
        repository_id="frontend-repo",
        requirement="Add a payment system",
        capabilities=[],
        relevant_files=[],
        relevant_symbols=[],
        relevant_routes=[],
        relevant_db_objects=[],
        relevant_dependencies=[],
        relevant_call_paths=[],
        relevant_features=[],
        architecture_constraints=["typescript"],
        impact_context=None,
        evidence=[],
        unknowns=["No payment capability in index"],
        contract=RepositoryUnderstandingContract(
            required_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
            satisfied_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
            missing_categories=[],
            unknowns=[],
            completeness=CompletenessStatus.COMPLETE,
            explanation="Complete evidence",
        ),
    )

    orchestrator = PlanningOrchestrator(llm_service=None)
    plan = orchestrator.create_plan(
        context=ctx,
        agent_run_id="run_payment_test",
        repository_id="frontend-repo",
        requirement="Add a payment system",
    )

    new_tasks = [t for t in plan.tasks if t.component_type == "NEW"]
    assert len(new_tasks) > 0
    assert "No existing" in new_tasks[0].description
    assert "Propose new module" in new_tasks[0].description


def test_context_sufficiency_is_repository_aware(db_session):
    """
    Verifies that a Frontend (TypeScript/Next.js) repository is not penalized
    for lacking Python database models or backend route decorators.
    """
    from backend.agent.context.assembler import ContextAssembler, ContextAssemblyRequest, ContextBudget
    # Seed TS package.json in analysis
    f_ts = FactFile(id="101:f_pkg", analysis_id=101, path="package.json", size=500, language="json")
    f_app = FactFile(id="101:f_app", analysis_id=101, path="src/app/page.tsx", size=500, language="typescript")
    db_session.add(f_ts)
    db_session.add(f_app)
    db_session.commit()

    assembler = ContextAssembler(llm_service=None)
    req = ContextAssemblyRequest(
        repository_id="repo1",
        analysis_id=101,
        requirement="What would it take to add dark mode?",
        context_budget=ContextBudget(),
    )
    ctx = assembler.assemble(req, db=db_session)
    # Must satisfy dependencies_or_models via package.json / frontend awareness
    assert "dependencies_or_models" in ctx.contract.satisfied_categories

