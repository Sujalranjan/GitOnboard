"""
Data models and enumerations for the documentation-aware repository summary pipeline.
"""
from __future__ import annotations
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocType(str, Enum):
    PRIMARY_README = "PRIMARY_README"
    ARCHITECTURE = "ARCHITECTURE"
    CONTRIBUTING = "CONTRIBUTING"
    PRODUCT_SYSTEM_DOCS = "PRODUCT_SYSTEM_DOCS"
    API_DOCS = "API_DOCS"
    GUIDES_TUTORIALS = "GUIDES_TUTORIALS"
    DIAGRAMS = "DIAGRAMS"
    AGENT_INSTRUCTIONS = "AGENT_INSTRUCTIONS"
    GENERIC_DOCS = "GENERIC_DOCS"


class DocPriority(IntEnum):
    HIGHEST = 100        # README, Architecture, System Design
    HIGH = 75            # Contributing, Core Product Docs
    MEDIUM = 50          # API Docs, Guides, Tutorials, Diagrams
    AGENT_CONTEXT = 20   # Agent/Tool Instructions (AGENTS.md, CLAUDE.md, skill.md)
    LOW = 10             # Generic / Misc Docs
    EXCLUDE = 0          # Ignored, vendored, build output


class DiscoveredDoc(BaseModel):
    path: str
    filename: str
    doc_type: DocType
    priority: DocPriority
    raw_size: int
    line_count: int
    headings: List[str] = Field(default_factory=list)
    content: str = ""
    is_truncated: bool = False
    token_estimate: int = 0


class BudgetedDocContext(BaseModel):
    primary_docs: List[DiscoveredDoc] = Field(default_factory=list)
    supporting_docs: List[DiscoveredDoc] = Field(default_factory=list)
    diagram_docs: List[DiscoveredDoc] = Field(default_factory=list)
    agent_docs: List[DiscoveredDoc] = Field(default_factory=list)
    omitted_docs: List[str] = Field(default_factory=list)
    total_chars: int = 0
    total_tokens_est: int = 0


class SummaryGenerationResult(BaseModel):
    summary_markdown: str
    doc_context_stats: Dict[str, Any] = Field(default_factory=dict)
    discrepancies_detected: List[str] = Field(default_factory=list)
    tool_calls_made: List[Dict[str, Any]] = Field(default_factory=list)

# ------------------------------------------------------------------------------
# V2 Evidence-Based Architecture Schemas
# ------------------------------------------------------------------------------

class EvidenceSourceType(str, Enum):
    MANIFEST_DEPENDENCY = "manifest_dep"
    CODE_IMPORT = "code_import"
    IMPORT_STATEMENT = "code_import"
    AST_DEFINITION = "ast_definition"
    AST_INSTANTIATION = "ast_instantiation"
    AST_CALL = "ast_call"
    ROUTE_DECLARATION = "route_decl"
    CONFIG_ENTRY = "config_entry"
    RUNTIME_INTEGRATION = "runtime_integration"
    DOCUMENTATION_SECTION = "doc_section"
    DB_MODEL_SCHEMA = "db_schema"


class SourceClassification(str, Enum):
    APPLICATION = "application"
    EXAMPLE = "example"
    TEST = "test"
    GENERATED = "generated"
    VENDORED = "vendored"
    CONFIGURATION = "configuration"
    DOCUMENTATION = "documentation"


class TechnologyLifecycle(BaseModel):
    is_declared: bool = False
    is_imported: bool = False
    is_instantiated: bool = False
    is_application_used: bool = False
    is_configured: bool = False
    is_runtime_integrated: bool = False
    is_documented: bool = False


class ClaimCategory(str, Enum):
    FRAMEWORK = "framework"
    DATABASE = "database"
    DEPLOYMENT = "deployment"
    DEPENDENCY = "dependency"
    TECHNOLOGY_DEPENDENCY = "dependency"
    ARCHITECTURE = "architecture"
    DEPLOYABLE_UNIT = "architecture"
    FEATURE = "feature"


class VerificationStatus(str, Enum):
    STRONGLY_SUPPORTED = "strongly_supported"
    SUPPORTED = "supported"
    CONFIGURED_ONLY = "configured_only"
    DECLARED_UNUSED = "declared_unused"
    DOCUMENTED_UNVERIFIED = "documented_unverified"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class EvidenceItem(BaseModel):
    evidence_id: str
    source_type: EvidenceSourceType
    source_classification: SourceClassification
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    snippet: str
    symbol_name: Optional[str] = None
    context_metadata: Dict[str, Any] = Field(default_factory=dict)


class RepositoryClaim(BaseModel):
    claim_id: str
    subject: str
    category: ClaimCategory = ClaimCategory.TECHNOLOGY_DEPENDENCY
    claim_type: Optional[str] = None
    statement: Optional[str] = None
    lifecycle: TechnologyLifecycle = Field(default_factory=TechnologyLifecycle)
    status: VerificationStatus
    evidence_ids: List[str] = Field(default_factory=list)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    verification_reasoning: str = ""


class DeployableUnitType(str, Enum):
    BACKEND_API = "backend_api"
    WEB_APP = "web_app"
    WEB_APPLICATION = "web_app"
    CLI_TOOL = "cli_tool"
    BACKGROUND_WORKER = "background_worker"
    SHARED_LIBRARY = "shared_library"
    DATA_PIPELINE = "data_pipeline"


class DeployableUnit(BaseModel):
    unit_id: str
    name: str
    unit_type: str
    root_path: str
    entrypoints: List[str] = Field(default_factory=list)
    manifest_evidence_id: Optional[str] = None
    config_evidence_id: Optional[str] = None
    contained_modules: List[str] = Field(default_factory=list)


class RejectedClaim(BaseModel):
    statement: str
    reason: str
    attempted_evidence_ids: List[str] = Field(default_factory=list)


class OverviewSummary(BaseModel):
    text: str
    evidence_ids: List[str] = Field(default_factory=list)


class DeployableUnitSummaryItem(BaseModel):
    name: str
    unit_type: str
    root_path: str
    summary: str = ""
    evidence_ids: List[str] = Field(default_factory=list)


class TechnologySummaryItem(BaseModel):
    name: str
    category: str = "Framework"
    status: str = "strongly_supported"
    evidence_ids: List[str] = Field(default_factory=list)


class DiscrepancyItem(BaseModel):
    documented_claim: str
    repository_reality: str
    evidence_ids: List[str] = Field(default_factory=list)


class UnverifiedDocClaimItem(BaseModel):
    claim: str = ""
    statement: str = ""
    doc_evidence_id: Optional[str] = None
    reason: str = "Unverified in codebase."
    evidence_ids: List[str] = Field(default_factory=list)


class StructuredSummary(BaseModel):
    overview: OverviewSummary
    deployable_units: List[DeployableUnitSummaryItem] = Field(default_factory=list)
    technologies: List[TechnologySummaryItem] = Field(default_factory=list)
    data_and_storage: Dict[str, Any] = Field(default_factory=dict)
    operations_and_deployment: Dict[str, Any] = Field(default_factory=dict)
    discrepancies: List[DiscrepancyItem] = Field(default_factory=list)
    unverified_doc_claims: List[UnverifiedDocClaimItem] = Field(default_factory=list)
