"""
Unit tests for RepositoryUnderstandingContract evaluation and unknown tracking.
"""
from backend.agent.context.contracts import (
    CompletenessStatus,
    RepositoryUnderstandingContract,
)


def test_understanding_contract_complete():
    contract = RepositoryUnderstandingContract(
        required_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
        satisfied_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
        missing_categories=[],
        unknowns=[],
        completeness=CompletenessStatus.COMPLETE,
        explanation="Sufficient evidence collected to satisfy all defined contract categories.",
    )
    assert contract.completeness == CompletenessStatus.COMPLETE
    assert len(contract.missing_categories) == 0


def test_understanding_contract_partial():
    contract = RepositoryUnderstandingContract(
        required_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
        satisfied_categories=["capabilities", "symbols_or_files"],
        missing_categories=["entrypoints_or_routes", "dependencies_or_models"],
        unknowns=["No routes found matching keyword"],
        completeness=CompletenessStatus.PARTIAL,
        explanation="Partial evidence gathered.",
    )
    assert contract.completeness == CompletenessStatus.PARTIAL
    assert len(contract.missing_categories) == 2
    assert "No routes found matching keyword" in contract.unknowns


def test_understanding_contract_insufficient():
    contract = RepositoryUnderstandingContract(
        required_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
        satisfied_categories=[],
        missing_categories=["capabilities", "entrypoints_or_routes", "symbols_or_files", "dependencies_or_models"],
        unknowns=["No matching files or symbols found in repository"],
        completeness=CompletenessStatus.INSUFFICIENT,
        explanation="Insufficient evidence found for requirement.",
    )
    assert contract.completeness == CompletenessStatus.INSUFFICIENT
    assert len(contract.satisfied_categories) == 0
    assert len(contract.missing_categories) == 4
