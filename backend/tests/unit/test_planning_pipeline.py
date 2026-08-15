"""
Unit tests for the planning pipeline.

Uses MockLLMService with deterministic fixture responses.
Zero real API calls — runs fully offline.
"""
import json
import pytest
from typing import Type, TypeVar
from pydantic import BaseModel
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine

from backend.database import Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile, FactSymbol, FactRelationship, FactRoute
from backend.models.implementation import (
    Implementation, ImplementationContract, ImplementationPlan,
    ImplementationStatus, ComponentType,
)

from backend.ai.service import LLMService
from backend.ai.schemas import LLMRequest, LLMResponse
from backend.planning.requirements import RequirementAnalyzer, AnalyzedRequirement
from backend.planning.impact_analysis import ImpactAnalyzer, PlanningStatus
from backend.planning.contract import ContractGenerator, ContractOutput
from backend.planning.planner import StepPlanner, PlanStep

from backend.tests.fixtures.llm_responses.planning import (
    MOCK_REQUIREMENT_ANALYSIS,
    MOCK_CONTRACT_OUTPUT,
    MOCK_PLAN_STEPS,
)

T = TypeVar("T")


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed in FK-dependency order: user -> repo -> analysis -> fact tables
    user = User(id=1, github_id="gh_1", username="testuser")
    session.add(user)
    session.flush()

    repo = Repository(id=1, url="https://github.com/test/repo", user_id=1)
    session.add(repo)
    session.flush()

    analysis = Analysis(id=1, repository_id=1, status="Completed", engine_version="v1")
    session.add(analysis)
    session.flush()

    # Seed fact store for impact analysis
    f = FactFile(id="f1", analysis_id=1, path="backend/routers/auth.py", language="python")
    session.add(f)
    session.flush()

    sym1 = FactSymbol(id="s1", analysis_id=1, file_id="f1", name="google_login", symbol_type="function")
    sym2 = FactSymbol(id="s2", analysis_id=1, file_id="f1", name="GoogleOAuthService", symbol_type="class")
    session.add_all([sym1, sym2])
    session.flush()

    f2 = FactFile(id="f2", analysis_id=1, path="backend/services/google_oauth.py", language="python")
    session.add(f2)
    session.flush()

    route = FactRoute(id="r1", analysis_id=1, method="GET", path="/auth/google", symbol_id="s1")
    session.add(route)

    session.commit()
    yield session
    session.close()


class MockLLMService:
    """Deterministic mock LLM service using fixture responses."""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        # Planner calls generate (not generate_structured) for step list
        return LLMResponse(content=MOCK_PLAN_STEPS, model="mock", provider="mock")

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        import json
        if schema == AnalyzedRequirement:
            return schema.model_validate(MOCK_REQUIREMENT_ANALYSIS)
        if "ContractOutput" in schema.__name__:
            return schema.model_validate(MOCK_CONTRACT_OUTPUT)
        raise ValueError(f"No mock for schema {schema}")


# ──────────────────────────────────────────────────────────────────────────────
# Tests: RequirementAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_requirement_analyzer_extracts_criteria():
    """RequirementAnalyzer must extract AC-01, AC-02, AC-03 from mock fixture."""
    analyzer = RequirementAnalyzer(MockLLMService())
    result = await analyzer.analyze("Add Google OAuth login with JWT session.")
    assert result.title == "Add Google OAuth Login"
    assert len(result.acceptance_criteria) == 3
    ids = [c.id for c in result.acceptance_criteria]
    assert "AC-01" in ids
    assert "AC-02" in ids
    assert "AC-03" in ids


@pytest.mark.asyncio
async def test_requirement_analyzer_returns_tests():
    analyzer = RequirementAnalyzer(MockLLMService())
    result = await analyzer.analyze("Add Google OAuth login.")
    assert len(result.tests_required) >= 3


# ──────────────────────────────────────────────────────────────────────────────
# Tests: ImpactAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_impact_analyzer_finds_evidence(db):
    """Impact analysis must find keyword matches and produce EVID-xxx items."""
    analyzer = ImpactAnalyzer(db=db, analysis_id=1)
    result = await analyzer.analyze(keywords=["google", "oauth", "auth"])
    assert result.status == PlanningStatus.SUFFICIENT
    assert len(result.evidence_items) >= 2
    # All evidence IDs must follow EVID-NNN format
    for item in result.evidence_items:
        assert item.evidence_id.startswith("EVID-")


@pytest.mark.asyncio
async def test_impact_analyzer_needs_context_when_empty(db):
    """Impact analysis must return NEEDS_CONTEXT when no evidence found."""
    analyzer = ImpactAnalyzer(db=db, analysis_id=1)
    result = await analyzer.analyze(keywords=["xyzzy_nonexistent_keyword_12345"])
    assert result.status == PlanningStatus.NEEDS_CONTEXT


@pytest.mark.asyncio
async def test_impact_analyzer_classifies_existing_vs_new(db):
    """Symbol validation must distinguish EXISTING (in DB) from NEW (not in DB)."""
    analyzer = ImpactAnalyzer(db=db, analysis_id=1)
    result = await analyzer.analyze(
        keywords=["auth"],
        proposed_symbols=["google_login", "PaymentService"],
    )
    assert "google_login" in result.existing_symbols
    assert "PaymentService" in result.new_symbols


@pytest.mark.asyncio
async def test_impact_analyzer_finds_routes(db):
    """Route keyword search must find /auth/google route."""
    analyzer = ImpactAnalyzer(db=db, analysis_id=1)
    result = await analyzer.analyze(keywords=["auth"])
    route_items = [i for i in result.evidence_items if i.source == "ROUTE"]
    assert len(route_items) >= 1
    assert any("auth" in (i.route_match or "") for i in route_items)


@pytest.mark.asyncio
async def test_impact_analyzer_context_block_is_untrusted(db):
    """Context block must begin with <untrusted_repo_context> injection defense."""
    analyzer = ImpactAnalyzer(db=db, analysis_id=1)
    result = await analyzer.analyze(keywords=["auth"])
    assert result.context_summary.startswith("<untrusted_repo_context>")
    assert "untrusted repository data" in result.context_summary.lower() or "UNTRUSTED" in result.context_summary


# ──────────────────────────────────────────────────────────────────────────────
# Tests: ContractGenerator
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_contract_generator_produces_components(db):
    """Contract must include affected components with evidence_ids cited."""
    analyzer_req = RequirementAnalyzer(MockLLMService())
    analyzed = await analyzer_req.analyze("Add Google OAuth login.")

    analyzer_impact = ImpactAnalyzer(db=db, analysis_id=1)
    impact = await analyzer_impact.analyze(keywords=["google", "auth"])

    contract_gen = ContractGenerator(MockLLMService())
    contract = await contract_gen.generate(analyzed, impact)

    assert len(contract.affected_components) >= 1
    assert len(contract.tests_required) >= 1
    for comp in contract.affected_components:
        assert comp.component_type in ("EXISTING", "NEW")


# ──────────────────────────────────────────────────────────────────────────────
# Tests: StepPlanner
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_step_planner_produces_ordered_steps(db):
    """Planner must produce steps ordered by step_number with AC linkage."""
    analyzer_req = RequirementAnalyzer(MockLLMService())
    analyzed = await analyzer_req.analyze("Add Google OAuth login.")

    analyzer_impact = ImpactAnalyzer(db=db, analysis_id=1)
    impact = await analyzer_impact.analyze(keywords=["google", "auth"])

    contract_gen = ContractGenerator(MockLLMService())
    contract = await contract_gen.generate(analyzed, impact)

    planner = StepPlanner(MockLLMService())
    steps = await planner.plan(analyzed, impact, contract)

    assert len(steps) >= 2
    step_numbers = [s.step_number for s in steps]
    assert step_numbers == sorted(step_numbers), "Steps must be in ascending order"
    # Every step must link to at least one AC
    for step in steps:
        assert len(step.acceptance_criteria) >= 1 or step.component_type == "NEW"


@pytest.mark.asyncio
async def test_step_planner_classifies_component_types(db):
    """Plan steps must declare component_type as EXISTING or NEW."""
    analyzer_req = RequirementAnalyzer(MockLLMService())
    analyzed = await analyzer_req.analyze("Add Google OAuth login.")

    analyzer_impact = ImpactAnalyzer(db=db, analysis_id=1)
    impact = await analyzer_impact.analyze(keywords=["auth"])

    contract_gen = ContractGenerator(MockLLMService())
    contract = await contract_gen.generate(analyzed, impact)

    planner = StepPlanner(MockLLMService())
    steps = await planner.plan(analyzed, impact, contract)

    for step in steps:
        assert step.component_type in ("EXISTING", "NEW")
