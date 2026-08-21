"""
Unit tests for RepositoryContext and ContextEvidence data models.
"""
from backend.agent.context.contracts import (
    CompletenessStatus,
    ContextAssemblyRequest,
    ContextBudget,
    ContextEvidence,
    RepositoryContext,
    RepositoryUnderstandingContract,
)


def test_context_evidence_model():
    ev = ContextEvidence(
        source_type="rim_symbol",
        source_id="UserAuthService.authenticate",
        relevance=0.95,
        confidence=1.0,
        summary="User authentication method located in auth.py",
        data={"file_path": "backend/auth.py", "signature": "def authenticate(user, password)"},
    )
    assert ev.source_type == "rim_symbol"
    assert ev.relevance == 0.95
    assert ev.data["file_path"] == "backend/auth.py"


def test_context_budget_defaults():
    budget = ContextBudget()
    assert budget.max_files == 15
    assert budget.max_symbols == 30
    assert budget.max_routes == 15
    assert budget.max_total_evidence_size_kb == 256


def test_repository_context_bounded_summary():
    contract = RepositoryUnderstandingContract(
        required_categories=["capabilities", "symbols"],
        satisfied_categories=["capabilities", "symbols"],
        missing_categories=[],
        unknowns=["No payment gateway found"],
        completeness=CompletenessStatus.COMPLETE,
        explanation="All contract criteria satisfied",
    )

    ctx = RepositoryContext(
        version="v1",
        repository_id="sample-repo",
        requirement="Add oauth login support",
        capabilities=[{"id": "cap_auth", "name": "Authentication"}],
        relevant_files=["auth.py", "models.py"],
        relevant_symbols=[{"name": "login"}, {"name": "logout"}],
        evidence=[
            ContextEvidence(
                source_type="capability",
                source_id="cap_auth",
                summary="Auth capability exists",
            )
        ],
        unknowns=["No payment gateway found"],
        contract=contract,
        metadata={"duration_ms": 42.5},
    )

    summary = ctx.to_bounded_summary()
    assert summary["version"] == "v1"
    assert summary["repository_id"] == "sample-repo"
    assert summary["completeness"] == "COMPLETE"
    assert summary["counts"]["capabilities"] == 1
    assert summary["counts"]["relevant_files"] == 2
    assert summary["counts"]["relevant_symbols"] == 2
    assert summary["counts"]["unknowns"] == 1
    assert summary["unknowns"] == ["No payment gateway found"]
