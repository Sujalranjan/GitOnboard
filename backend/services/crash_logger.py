"""Service for logging crashes and exceptions to the database."""

import logging
import traceback
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class CrashLogger:
    """Centralized crash logging for observability and debugging."""

    def __init__(self, db=None):
        self.db = db

    def log_exception(
        self,
        exception: Exception,
        endpoint: Optional[str] = None,
        user_id: Optional[str] = None,
        repository_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        request_body: Optional[Dict[str, Any]] = None,
        environment: str = "dev",
    ) -> None:
        """
        Log an exception to both stdout and database.

        Args:
            exception: The exception that occurred
            endpoint: API endpoint that was hit (e.g., POST /api/repos/{repo}/rim-comparison)
            user_id: User who triggered the error
            repository_id: Repository being accessed
            correlation_id: Request correlation ID for tracing
            request_body: Sanitized request data (for reproduction)
            environment: Deployment environment (dev/staging/prod)
        """
        error_type = type(exception).__name__
        error_message = str(exception)
        stack_trace = traceback.format_exc()

        # Log to stdout first (always available)
        logger.error(
            f"[CRASH] {error_type}: {error_message} | "
            f"endpoint={endpoint} | "
            f"correlation_id={correlation_id}",
            exc_info=exception,
        )

        # Log to database if available
        if self.db:
            try:
                from backend.models.error_tracking import CrashLog

                crash_record = CrashLog(
                    timestamp=datetime.utcnow(),
                    error_type=error_type,
                    error_message=error_message,
                    stack_trace=stack_trace,
                    endpoint=endpoint,
                    user_id=user_id,
                    repository_id=repository_id,
                    correlation_id=correlation_id,
                    request_body=str(request_body)[:2000] if request_body else None,  # Cap at 2KB
                    environment=environment,
                    is_resolved=0,
                )
                self.db.add(crash_record)
                self.db.commit()
                logger.info(f"[CRASH_LOGGED] Crash record created with ID {crash_record.id}")
            except Exception as db_err:
                logger.error(f"[CRASH_LOGGER_FAILED] Could not log to database: {db_err}")

    def log_performance_alert(
        self,
        alert_type: str,
        metric_name: str,
        metric_value: int,
        threshold: int,
        endpoint: Optional[str] = None,
        duration_ms: Optional[int] = None,
        description: Optional[str] = None,
    ) -> None:
        """
        Log a performance anomaly (e.g., excessive Azure calls).

        Args:
            alert_type: e.g., "excessive_azure_calls", "slow_query"
            metric_name: e.g., "blob_storage_calls", "query_duration_ms"
            metric_value: Actual value observed
            threshold: Upper limit that was exceeded
            endpoint: API endpoint
            duration_ms: Request duration
            description: Human-readable details
        """
        logger.warning(
            f"[PERFORMANCE_ALERT] {alert_type}: {metric_name}={metric_value} "
            f"(threshold={threshold}) | endpoint={endpoint}"
        )

        if self.db:
            try:
                from backend.models.error_tracking import PerformanceAlert

                alert_record = PerformanceAlert(
                    timestamp=datetime.utcnow(),
                    alert_type=alert_type,
                    metric_name=metric_name,
                    metric_value=metric_value,
                    threshold=threshold,
                    endpoint=endpoint,
                    duration_ms=duration_ms,
                    description=description,
                )
                self.db.add(alert_record)
                self.db.commit()
                logger.info(f"[ALERT_LOGGED] Performance alert created with ID {alert_record.id}")
            except Exception as db_err:
                logger.error(f"[ALERT_LOGGER_FAILED] Could not log to database: {db_err}")


# Global singleton for easy access
_crash_logger: Optional[CrashLogger] = None


def initialize_crash_logger(db) -> CrashLogger:
    """Initialize the global crash logger with a database session."""
    global _crash_logger
    _crash_logger = CrashLogger(db)
    return _crash_logger


def get_crash_logger() -> CrashLogger:
    """Get the global crash logger instance."""
    global _crash_logger
    if _crash_logger is None:
        _crash_logger = CrashLogger(db=None)
    return _crash_logger
