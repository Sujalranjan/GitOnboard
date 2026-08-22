"""
Unit tests for VerificationStrategyResolver in Phase 7.
"""
from backend.agent.planning.contracts import PlanTask
from backend.agent.tasks.contracts import TaskExecutionContext
from backend.agent.verification.contracts import VerificationType
from backend.agent.verification.strategy import VerificationStrategyResolver


def test_strategy_resolver_explicit_static():
    resolver = VerificationStrategyResolver()
    task = PlanTask(
        task_id="t-1",
        step_number=1,
        title="Add helper function",
        description="Add util helper",
        affected_files=["utils/helpers.py"],
        verification_strategy="verify_static",
    )
    strategy = resolver.resolve(task_definition=task)
    assert len(strategy.checks) == 1
    assert strategy.checks[0].type == VerificationType.STATIC


def test_strategy_resolver_explicit_dynamic():
    resolver = VerificationStrategyResolver()
    task = PlanTask(
        task_id="t-2",
        step_number=2,
        title="Implement feature with unit tests",
        description="Add feature and tests",
        affected_files=["feature.py", "tests/test_feature.py"],
        verification_strategy="verify_dynamic",
    )
    strategy = resolver.resolve(task_definition=task)
    assert len(strategy.checks) == 2
    types = [c.type for c in strategy.checks]
    assert VerificationType.STATIC in types
    assert VerificationType.DYNAMIC in types


def test_strategy_resolver_explicit_contract():
    resolver = VerificationStrategyResolver()
    task = PlanTask(
        task_id="t-3",
        step_number=3,
        title="Implement endpoint schema",
        description="Update api contract",
        affected_files=["routes/api.py"],
        acceptance_criteria=["Endpoint returns status 200 with user schema"],
        verification_strategy="verify_contract",
    )
    strategy = resolver.resolve(task_definition=task)
    types = [c.type for c in strategy.checks]
    assert VerificationType.STATIC in types
    assert VerificationType.CONTRACT in types


def test_strategy_resolver_final_verification():
    resolver = VerificationStrategyResolver()
    strategy = resolver.resolve(is_final=True)
    assert strategy.is_final_verification is True
    types = [c.type for c in strategy.checks]
    assert VerificationType.STATIC in types
    assert VerificationType.DYNAMIC in types
    assert VerificationType.CONTRACT in types
