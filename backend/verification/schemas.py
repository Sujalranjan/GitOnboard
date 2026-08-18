"""
Pydantic schemas and enums for the Multi-Vector Verification Mesh.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutionState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    UNVERIFIED = "UNVERIFIED"
    MOCKED = "MOCKED"


class DefectSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DefectCategory(str, Enum):
    STATIC_SYMBOL_MISSING = "STATIC_SYMBOL_MISSING"
    STATIC_IMPORT_MISSING = "STATIC_IMPORT_MISSING"
    DYNAMIC_TEST_FAILURE = "DYNAMIC_TEST_FAILURE"
    DYNAMIC_BUILD_FAILURE = "DYNAMIC_BUILD_FAILURE"
    DYNAMIC_LINT_FAILURE = "DYNAMIC_LINT_FAILURE"
    CONTRACT_OMISSION = "CONTRACT_OMISSION"
    CONTRACT_INVARIANT_VIOLATION = "CONTRACT_INVARIANT_VIOLATION"
    ARCHITECTURE_ERROR = "ARCHITECTURE_ERROR"


class Defect(BaseModel):
    category: str = Field(description="Category of the defect (e.g. STATIC_IMPORT_MISSING)")
    file_path: str = Field(description="Relative path of file containing defect")
    line_number: Optional[int] = Field(default=None, description="Line number of defect if available")
    description: str = Field(description="Detailed technical description of defect")
    severity: str = Field(default=DefectSeverity.HIGH.value, description="Defect severity")
    symbol: Optional[str] = Field(default=None, description="Target symbol name if applicable")
    evidence_id: Optional[str] = Field(default=None, description="Citing evidence ID if applicable")


class VerificationResult(BaseModel):
    vector_name: str = Field(description="Name of verification vector: 'static', 'dynamic', or 'contract'")
    status: str = Field(description="'PASS', 'FAIL', 'ERROR', 'UNVERIFIED', or 'MOCKED'")
    passed: bool = Field(description="True if vector detected zero defects and had verified evidence")
    execution_state: str = Field(default=ExecutionState.UNVERIFIED.value, description="Standardized execution state")
    defects: List[Defect] = Field(default_factory=list)
    evidence_manifest: List[Dict[str, Any]] = Field(default_factory=list, description="Concrete evidence items supporting verdict")
    details: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = Field(default=0.0)


class VerificationReport(BaseModel):
    run_id: str = Field(description="Unique ID of the verification run")
    status: str = Field(description="'PASS', 'FAIL', 'ERROR', 'UNVERIFIED', or 'MOCKED'")
    passed: bool = Field(description="True if all vectors passed with zero defects and verified evidence")
    execution_state: str = Field(default=ExecutionState.UNVERIFIED.value, description="Standardized execution state")
    static_result: VerificationResult
    dynamic_result: VerificationResult
    contract_result: VerificationResult
    defects: List[Defect] = Field(default_factory=list)
    evidence_manifest: List[Dict[str, Any]] = Field(default_factory=list, description="Aggregated concrete evidence items")
    summary: str = Field(default="")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
