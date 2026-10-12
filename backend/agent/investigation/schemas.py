"""
Investigation schemas and contracts for local worker and persistent evidence.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SubtaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class FindingType(str, Enum):
    SOURCE_IMPLEMENTATION = "SOURCE_IMPLEMENTATION"
    DEFINITION = "DEFINITION"
    RELATIONSHIP = "RELATIONSHIP"
    CONFIGURATION = "CONFIGURATION"
    DATABASE_SCHEMA = "DATABASE_SCHEMA"
    LIMITATION = "LIMITATION"
    ABSENCE_VERIFIED = "ABSENCE_VERIFIED"


class EvidenceCard(BaseModel):
    """
    A single granular, source-backed finding discovered during investigation.
    Preserves exact provenance, line numbers, and technical claims outside LLM message history.
    """
    id: str = Field(description="Unique identifier of this evidence card")
    task_id: str = Field(description="ID of the subtask that discovered this evidence")
    file_path: str = Field(description="File path relative to repository root")
    line_start: Optional[int] = Field(default=None, description="Starting line number")
    line_end: Optional[int] = Field(default=None, description="Ending line number")
    symbol_name: Optional[str] = Field(default=None, description="Associated symbol (function/class/method)")
    finding_type: FindingType = Field(default=FindingType.SOURCE_IMPLEMENTATION, description="Classification of the finding")
    summary: str = Field(description="Concise technical fact extracted from code")
    code_excerpt: Optional[str] = Field(default=None, description="Exact code snippet verifying the fact")
    confidence: float = Field(default=1.0, description="Confidence score [0.0 - 1.0]")
    discovered_dependencies: List[str] = Field(default_factory=list, description="New symbols or files discovered needing further investigation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra metadata")


class InvestigationSubtask(BaseModel):
    """
    A discrete, bounded repository investigation task dispatched to the Local Worker.
    """
    id: str = Field(description="Unique identifier for the subtask (e.g. 'task_1_auth_flow')")
    title: str = Field(description="Short human-readable title of what to investigate")
    description: str = Field(description="Specific target questions and code entities to inspect")
    target_entities: List[str] = Field(default_factory=list, description="Target symbol or file names to start with")
    search_strategy: str = Field(default="", description="Suggested search strategy and repository tools")
    expected_output: str = Field(default="", description="What facts must be verified before completing")
    completion_criteria: str = Field(default="", description="Strict completion criteria required to mark completed")
    status: SubtaskStatus = Field(default=SubtaskStatus.PENDING)
    dependencies: List[str] = Field(default_factory=list, description="Task IDs that must finish first")
    findings: List[EvidenceCard] = Field(default_factory=list, description="Evidence cards produced by this task")
    error: Optional[str] = Field(default=None, description="Error message if task failed")
    duration_ms: float = Field(default=0.0, description="Time spent executing task")


class WorkerTaskResult(BaseModel):
    """
    Structured response returned by the Local Worker upon finishing a subtask.
    Includes explicit file inspection transparency and usage metrics.
    """
    task_id: str
    status: SubtaskStatus
    findings: List[EvidenceCard] = Field(default_factory=list)
    # File Inspection Transparency
    files_read: List[str] = Field(default_factory=list, description="Exact files and line ranges actually read")
    files_discovered: List[str] = Field(default_factory=list, description="Files found via search or outlines but not opened")
    files_skipped: List[Dict[str, str]] = Field(default_factory=list, description="Files skipped with reason [{'path': ..., 'reason': ...}]")
    read_failures: List[Dict[str, str]] = Field(default_factory=list, description="Files attempted but failed [{'path': ..., 'error': ...}]")
    coverage_gaps: List[str] = Field(default_factory=list, description="Unresolved questions or areas not inspected")
    files_inspected: List[str] = Field(default_factory=list, description="All files interacted with (read or inspected)")
    discovered_next_steps: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    turn_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: float = 0.0

    @classmethod
    def _coerce_str_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str):
                    res.append(item)
                elif isinstance(item, dict):
                    res.append(str(item.get("description") or item.get("reason") or item.get("message") or item))
                else:
                    res.append(str(item))
            return res
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, dict):
            return [str(v)]
        return [str(v)]

    from pydantic import field_validator

    @field_validator("limitations", "coverage_gaps", "discovered_next_steps", "files_read", "files_discovered", "files_inspected", mode="before")
    @classmethod
    def validate_string_lists(cls, v: Any) -> List[str]:
        return cls._coerce_str_list(v)

