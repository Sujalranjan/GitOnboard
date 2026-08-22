"""
Verification Strategy Resolver for Phase 7 Verification-Driven Execution.

Determines the appropriate verification vectors and check specifications for a task:
  1. Explicit task verification strategy (e.g. verify_static, verify_dynamic, verify_contract, verify_all)
  2. Task acceptance criteria and affected file heuristics
  3. Final plan-level verification requirements
Produces an ordered VerificationStrategy containing typed VerificationCheck items.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import uuid

from backend.agent.planning.contracts import PlanTask
from backend.agent.tasks.contracts import TaskExecutionContext
from backend.agent.verification.contracts import (
    VerificationCheck,
    VerificationStrategy,
    VerificationType,
)

logger = logging.getLogger(__name__)


class VerificationStrategyResolver:
    """
    Resolves task-specific and plan-level verification strategies.
    """

    def resolve(
        self,
        task_context: Optional[TaskExecutionContext] = None,
        task_definition: Optional[PlanTask] = None,
        is_final: bool = False,
        explicit_strategy: Optional[str] = None,
        affected_files: Optional[List[str]] = None,
        acceptance_criteria: Optional[List[str]] = None,
    ) -> VerificationStrategy:
        """
        Builds an ordered VerificationStrategy based on task parameters and metadata.
        """
        task_id = "plan-final-verification"
        if task_context:
            task_id = task_context.task_id
            if not task_definition:
                task_definition = task_context.task_definition
            if not affected_files and task_definition:
                affected_files = task_definition.affected_files
            if not acceptance_criteria and task_definition:
                acceptance_criteria = task_definition.acceptance_criteria
            if not explicit_strategy and task_definition:
                explicit_strategy = task_definition.verification_strategy
        elif task_definition:
            task_id = task_definition.task_id
            if not affected_files:
                affected_files = task_definition.affected_files
            if not acceptance_criteria:
                acceptance_criteria = task_definition.acceptance_criteria
            if not explicit_strategy:
                explicit_strategy = task_definition.verification_strategy

        strategy_str = (explicit_strategy or "").strip().lower()
        files = list(affected_files or [])
        criteria = list(acceptance_criteria or [])

        # Final plan-level verification always requires FULL verification mesh
        if is_final or strategy_str in ("full", "verify_full", "verify_all"):
            return self._build_full_strategy(task_id=task_id, files=files, criteria=criteria)

        # Strategy resolution based on explicit task strategy name
        if strategy_str in ("verify_static", "static", "verify_static_and_syntax", "syntax"):
            return self._build_static_strategy(task_id=task_id, files=files)

        if strategy_str in ("verify_dynamic", "dynamic", "verify_test_suite", "test_suite"):
            return self._build_dynamic_strategy(task_id=task_id, files=files)

        if strategy_str in ("verify_contract", "contract", "verify_contract_invariants"):
            return self._build_contract_strategy(task_id=task_id, files=files, criteria=criteria)

        # Heuristic inference if strategy string is unspecified or generic
        has_tests = any(f.startswith("tests/") or "test_" in f or "_test." in f for f in files)
        has_contract_keywords = any(
            any(kw in c.lower() for kw in ("contract", "schema", "endpoint", "api", "invariant", "status_code"))
            for c in criteria
        )

        if has_contract_keywords and has_tests:
            return self._build_full_strategy(task_id=task_id, files=files, criteria=criteria)
        elif has_contract_keywords:
            return self._build_contract_strategy(task_id=task_id, files=files, criteria=criteria)
        elif has_tests:
            return self._build_dynamic_strategy(task_id=task_id, files=files)

        # Conservative default: STATIC + DYNAMIC
        return self._build_dynamic_strategy(task_id=task_id, files=files)

    def _build_static_strategy(self, task_id: str, files: List[str]) -> VerificationStrategy:
        check = VerificationCheck(
            check_id=str(uuid.uuid4()),
            type=VerificationType.STATIC,
            name="Static AST & Import Integrity",
            required=True,
            timeout=30.0,
            metadata={"files": files},
        )
        return VerificationStrategy(
            task_id=task_id,
            required_types=[VerificationType.STATIC],
            checks=[check],
            is_final_verification=False,
        )

    def _build_dynamic_strategy(self, task_id: str, files: List[str]) -> VerificationStrategy:
        check_static = VerificationCheck(
            check_id=str(uuid.uuid4()),
            type=VerificationType.STATIC,
            name="Static AST & Import Integrity",
            required=True,
            timeout=30.0,
            metadata={"files": files},
        )
        check_dynamic = VerificationCheck(
            check_id=str(uuid.uuid4()),
            type=VerificationType.DYNAMIC,
            name="Dynamic Test Execution",
            command="pytest/npm test",
            required=True,
            timeout=60.0,
            metadata={"files": files},
        )
        return VerificationStrategy(
            task_id=task_id,
            required_types=[VerificationType.STATIC, VerificationType.DYNAMIC],
            checks=[check_static, check_dynamic],
            is_final_verification=False,
        )

    def _build_contract_strategy(
        self, task_id: str, files: List[str], criteria: List[str]
    ) -> VerificationStrategy:
        check_static = VerificationCheck(
            check_id=str(uuid.uuid4()),
            type=VerificationType.STATIC,
            name="Static AST & Import Integrity",
            required=True,
            timeout=30.0,
            metadata={"files": files},
        )
        check_contract = VerificationCheck(
            check_id=str(uuid.uuid4()),
            type=VerificationType.CONTRACT,
            name="Implementation Contract Verification",
            required=True,
            timeout=45.0,
            metadata={"files": files, "criteria": criteria},
        )
        return VerificationStrategy(
            task_id=task_id,
            required_types=[VerificationType.STATIC, VerificationType.CONTRACT],
            checks=[check_static, check_contract],
            is_final_verification=False,
        )

    def _build_full_strategy(
        self, task_id: str, files: List[str], criteria: List[str]
    ) -> VerificationStrategy:
        check_static = VerificationCheck(
            check_id=str(uuid.uuid4()),
            type=VerificationType.STATIC,
            name="Static AST & Import Integrity",
            required=True,
            timeout=30.0,
            metadata={"files": files},
        )
        check_dynamic = VerificationCheck(
            check_id=str(uuid.uuid4()),
            type=VerificationType.DYNAMIC,
            name="Dynamic Test Execution",
            command="pytest/npm test",
            required=True,
            timeout=60.0,
            metadata={"files": files},
        )
        check_contract = VerificationCheck(
            check_id=str(uuid.uuid4()),
            type=VerificationType.CONTRACT,
            name="Implementation Contract Verification",
            required=True,
            timeout=45.0,
            metadata={"files": files, "criteria": criteria},
        )
        return VerificationStrategy(
            task_id=task_id,
            required_types=[VerificationType.STATIC, VerificationType.DYNAMIC, VerificationType.CONTRACT],
            checks=[check_static, check_dynamic, check_contract],
            is_final_verification=True,
        )
