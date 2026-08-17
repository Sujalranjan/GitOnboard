"""
Pydantic Schemas for Benchmark Tasks and Comparative Evaluation Metrics.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BenchmarkCategory(str, Enum):
    PACKAGE_HALLUCINATION = "PACKAGE_HALLUCINATION"
    SYMBOL_REFERENCE_ERROR = "SYMBOL_REFERENCE_ERROR"
    REQUIREMENT_OMISSION = "REQUIREMENT_OMISSION"
    ARCH_VIOLATION = "ARCH_VIOLATION"
    EDGE_CASE_TEST_FAILURE = "EDGE_CASE_TEST_FAILURE"


class BenchmarkTaskSchema(BaseModel):
    task_id: str = Field(description="Unique task identifier e.g. TASK-001")
    category: str = Field(description="Defect category classification")
    title: str = Field(description="Short descriptive title of the task")
    repository_target: str = Field(default="default", description="Target repository name or path")
    base_commit: str = Field(default="main", description="Target base branch or commit hash")
    prompt: str = Field(description="Natural-language prompt given to the AI coding agent")
    expected_contract: Dict[str, Any] = Field(
        default_factory=dict,
        description="Ground-truth requirements, endpoints, invariants, and test coverage",
    )
    known_pitfall_check: Dict[str, Any] = Field(
        default_factory=dict,
        description="Specific heuristic or test check designed to expose raw agent hallucinations or omissions",
    )
    seeded_failure_mode: Optional[str] = Field(
        default=None,
        description="Description of the typical zero-shot LLM defect",
    )


class TaskConditionResult(BaseModel):
    condition_name: str = Field(description="Condition A (Baseline Zero-Shot) or Condition B (GitOnBoard Verification)")
    passed: bool
    defects_count: int
    defects_list: List[str] = Field(default_factory=list)
    raw_diff: str = ""
    iterations: int = 1
    execution_time_sec: float = 0.0


class BenchmarkRunMetrics(BaseModel):
    total_tasks: int
    baseline_passed_count: int
    baseline_pass_rate_pct: float
    gitonboard_passed_count: int
    gitonboard_pass_rate_pct: float
    defect_resolution_rate_pct: float
    avg_repair_iterations: float
    avg_execution_time_sec: float
    results: List[Dict[str, Any]] = Field(default_factory=list)
