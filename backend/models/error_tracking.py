"""Error and crash tracking models for observability."""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, Index
from backend.database import Base


class CrashLog(Base):
    """Track application crashes and exceptions for debugging."""

    __tablename__ = "crash_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Error details
    error_type = Column(String(256), nullable=False, index=True)  # e.g., TypeError, ValueError
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)

    # Context
    endpoint = Column(String(512), nullable=True)  # e.g., POST /api/repos/{repo}/rim-comparison/compare
    user_id = Column(String(256), nullable=True)
    repository_id = Column(String(256), nullable=True)

    # Correlation
    correlation_id = Column(String(256), nullable=True, index=True)
    request_id = Column(String(256), nullable=True)

    # Reproducibility
    request_body = Column(Text, nullable=True)  # Sanitized request data for reproduction
    environment = Column(String(64), nullable=True)  # dev, staging, prod

    # Recovery
    is_resolved = Column(Integer, default=0)  # 0 = open, 1 = resolved
    resolution_notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_crash_logs_timestamp_error_type", "timestamp", "error_type"),
        Index("ix_crash_logs_correlation_id", "correlation_id"),
        Index("ix_crash_logs_repository_id", "repository_id"),
    )


class PerformanceAlert(Base):
    """Track performance anomalies (e.g., too many Azure calls)."""

    __tablename__ = "performance_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Alert details
    alert_type = Column(String(128), nullable=False, index=True)  # e.g., "excessive_azure_calls", "slow_query"
    metric_name = Column(String(256), nullable=False)  # e.g., "blob_storage_calls"
    metric_value = Column(Integer, nullable=False)  # e.g., 150 (calls)
    threshold = Column(Integer, nullable=False)  # e.g., 50 (limit)

    # Context
    endpoint = Column(String(512), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Details
    description = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_performance_alerts_timestamp_type", "timestamp", "alert_type"),
    )
