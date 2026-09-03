from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, LargeBinary, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from backend.database import Base
import uuid

JSONType = JSON().with_variant(JSONB, "postgresql")

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    github_repo_id = Column(String, index=True, nullable=True)
    url = Column(String, index=True, nullable=False)
    default_branch = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_user_repo_url"),
        UniqueConstraint("user_id", "github_repo_id", name="uq_user_github_repo"),
    )
    
    analyses = relationship("Analysis", back_populates="repository", cascade="all, delete-orphan")

class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    commit_sha = Column(String, nullable=True)
    engine_version = Column(String, nullable=False, default="v1.0")
    status = Column(String, nullable=False, default="Queued")  # Queued, Downloading, Analyzing, Saving, Completed, Failed
    indexing_status = Column(String, nullable=False, default="PENDING")  # PENDING, SUCCESS, PARTIAL, FAILED
    indexing_details = Column(JSONType, nullable=True)  # {exact: {...}, bm25: {...}, semantic: {...}}
    fact_store_version = Column(String, nullable=True, default=lambda: str(uuid.uuid4()))  # UUID for immutability guarantee
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    indexed_at = Column(DateTime(timezone=True), nullable=True)

    repository = relationship("Repository", back_populates="analyses")
    artifacts = relationship("AnalysisArtifact", back_populates="analysis", cascade="all, delete-orphan")
    jobs = relationship("AnalysisJob", back_populates="analysis", cascade="all, delete-orphan")

class AnalysisArtifact(Base):
    __tablename__ = "analysis_artifacts"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=False)
    type = Column(String, index=True, nullable=False) # e.g., 'metrics', 'ast', 'dependency_graph'
    data = Column(JSONType, nullable=True)
    blob_data = Column(LargeBinary, nullable=True)
    
    analysis = relationship("Analysis", back_populates="artifacts")

class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=False)
    status = Column(String, nullable=False, default="Queued") # Queued, Downloading, Analyzing, Saving, Completed, Failed, Cancelled
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(String, nullable=True)
    
    analysis = relationship("Analysis", back_populates="jobs")

class TaskStatus(Base):
    __tablename__ = "task_statuses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    repo_name = Column(String, nullable=False)
    task_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending, processing, completed, failed
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
