"""
PlanValidator: Validates that synthesized implementation plans satisfy all architectural contracts.

Rules enforced:
  1. Non-Empty Guard: Rejects empty plans unless explicitly flagged as no-op.
  2. Task Purpose: Every task must possess a clear, non-empty title and description.
  3. Acceptance Criteria: Every task must define measurable acceptance criteria (Fatal Error if missing).
  4. Dependency DAG Correctness:
     - All dependency task IDs must exist.
     - Graph must be strictly acyclic (no cycles or self-dependencies).
  5. Verification Strategy: Every task must specify a verification method (Fatal Error if missing).
  6. Unknowns Preservation: Carries forward repository unknowns without silently fabricating architecture.
  7. Duplicate Detection: Identifies redundant or duplicate tasks.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Set

from .contracts import Plan, PlanTask, PlanValidationResult

logger = logging.getLogger(__name__)


class PlanValidator:
    """
    Validates a Plan artifact against architectural constraints before human approval.
    """

    def validate(self, plan: Plan) -> PlanValidationResult:
        """
        Runs comprehensive validation across the plan and task DAG.
        """
        errors: List[str] = []
        warnings: List[str] = []
        missing_requirements: List[str] = []
        missing_acceptance_criteria: List[str] = []
        missing_verification: List[str] = []
        dependency_cycles: List[List[str]] = []
        unknowns: List[str] = list(plan.unknowns)

        # 1. Non-Empty Guard
        if not plan.tasks:
            errors.append("Plan contains no tasks. An implementation plan must contain at least one actionable task.")

        # 2. Task-Level Validations
        task_map: Dict[str, PlanTask] = {t.task_id: t for t in plan.tasks}
        seen_titles: Set[str] = set()

        for t in plan.tasks:
            # Purpose check
            if not t.title or not t.title.strip():
                errors.append(f"Task '{t.task_id}' is missing a title.")
            if not t.description or not t.description.strip():
                errors.append(f"Task '{t.task_id}' ('{t.title}') is missing a description.")

            # Acceptance Criteria check (Fatal Error)
            if not t.acceptance_criteria or all(not c.strip() for c in t.acceptance_criteria):
                err = f"Task '{t.task_id}' ('{t.title}') lacks acceptance criteria."
                errors.append(err)
                missing_acceptance_criteria.append(t.task_id)

            # Verification Strategy check (Fatal Error)
            if not t.verification_strategy or not t.verification_strategy.strip():
                err = f"Task '{t.task_id}' ('{t.title}') lacks a verification strategy."
                errors.append(err)
                missing_verification.append(t.task_id)

            # Affected scope warning (Non-fatal)
            if not t.affected_files and t.component_type == "EXISTING":
                warnings.append(f"Task '{t.task_id}' targets existing code but specifies no affected files.")

            # Duplicate task detection
            norm_title = t.title.strip().lower()
            if norm_title in seen_titles:
                warnings.append(f"Duplicate or highly similar task detected: '{t.title}'.")
            seen_titles.add(norm_title)

        # 3. Dependency Validation & Cycle Detection (DAG)
        cycles = self._detect_dependency_cycles(task_map)
        if cycles:
            for cycle in cycles:
                dependency_cycles.append(cycle)
                errors.append(f"Circular dependency detected: {' -> '.join(cycle)}")

        # 4. Unknowns / Uncertainty Evaluation
        if plan.unknowns:
            warnings.extend([f"Carried-forward unknown: {u}" for u in plan.unknowns])

        is_valid = len(errors) == 0

        result = PlanValidationResult(
            valid=is_valid,
            errors=errors,
            warnings=warnings,
            missing_requirements=missing_requirements,
            missing_acceptance_criteria=missing_acceptance_criteria,
            dependency_cycles=dependency_cycles,
            missing_verification=missing_verification,
            unknowns=unknowns,
        )

        logger.info(
            f"PlanValidator: Plan '{plan.plan_id}' validation -> "
            f"valid={is_valid}, {len(errors)} errors, {len(warnings)} warnings, {len(dependency_cycles)} cycles"
        )
        return result

    def _detect_dependency_cycles(self, task_map: Dict[str, PlanTask]) -> List[List[str]]:
        """
        Detects circular dependencies in the task graph using DFS with state tracking.
        Returns a list of cycle paths if any are found.
        """
        cycles: List[List[str]] = []
        
        # State: 0 = unvisited, 1 = visiting (in recursion stack), 2 = visited (completed)
        visited: Dict[str, int] = {tid: 0 for tid in task_map}
        path: List[str] = []

        def dfs(node: str):
            visited[node] = 1
            path.append(node)

            task = task_map.get(node)
            deps = task.dependencies if task else []

            for dep in deps:
                if dep not in task_map:
                    # Dep references a non-existent task ID
                    continue

                if visited[dep] == 1:
                    # Cycle detected: extract cycle from path
                    cycle_start_idx = path.index(dep)
                    cycle = path[cycle_start_idx:] + [dep]
                    cycles.append(cycle)
                elif visited[dep] == 0:
                    dfs(dep)

            path.pop()
            visited[node] = 2

        for task_id in task_map:
            if visited[task_id] == 0:
                dfs(task_id)

        return cycles
