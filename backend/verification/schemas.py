"""
Pydantic schemas and enums for the Multi-Vector Verification Mesh.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


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
    status: str = Field(description="'PASS' or 'FAIL'")
    passed: bool = Field(description="True if vector detected zero defects")
    defects: List[Defect] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = Field(default=0.0)


class VerificationReport(BaseModel):
    run_id: str = Field(description="Unique ID of the verification run")
    status: str = Field(description="'PASS' or 'FAIL'")
    passed: bool = Field(description="True if all vectors passed with zero defects")
    static_result: VerificationResult
    dynamic_result: VerificationResult
    contract_result: VerificationResult
    defects: List[Defect] = Field(default_factory=list)
    summary: str = Field(default="")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
