import contextvars
import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

LOGS_DIR = Path("logs")

# Correlation ID Context Variables
correlation_id_ctx = contextvars.ContextVar[str]("correlation_id", default="")
repo_id_ctx = contextvars.ContextVar[str]("repo_id", default="")
task_id_ctx = contextvars.ContextVar[str]("task_id", default="")
worktree_id_ctx = contextvars.ContextVar[str]("worktree_id", default="")
blob_id_ctx = contextvars.ContextVar[str]("blob_id", default="")


def set_correlation_context(
    correlation_id: Optional[str] = None,
    repo_id: Optional[str] = None,
    task_id: Optional[str] = None,
    worktree_id: Optional[str] = None,
    blob_id: Optional[str] = None,
) -> None:
    """Sets correlation identifiers in the current async context."""
    if correlation_id is not None:
        correlation_id_ctx.set(correlation_id)
    if repo_id is not None:
        repo_id_ctx.set(repo_id)
    if task_id is not None:
        task_id_ctx.set(task_id)
    if worktree_id is not None:
        worktree_id_ctx.set(worktree_id)
    if blob_id is not None:
        blob_id_ctx.set(blob_id)


def get_correlation_context() -> Dict[str, str]:
    """Retrieves active correlation identifiers from context."""
    return {
        "correlation_id": correlation_id_ctx.get(),
        "repo_id": repo_id_ctx.get(),
        "task_id": task_id_ctx.get(),
        "worktree_id": worktree_id_ctx.get(),
        "blob_id": blob_id_ctx.get(),
    }


def sanitize_log_data(data: Any) -> Any:
    """
    Recursively redacts secrets, bearer tokens, JWTs, and sensitive payload keys.
    """
    sensitive_keys = {
        "access_token", "github_access_token", "token", "password", "jwt",
        "secret", "jwt_secret", "azure_storage_account_key", "authorization",
        "cookie", "set-cookie", "client_secret"
    }

    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if str(k).lower() in sensitive_keys:
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_log_data(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_log_data(item) for item in data]
    elif isinstance(data, str):
        if data.lower().startswith("bearer ") or len(data) > 300 and ("eyj" in data.lower() or "gho_" in data):
            return "[REDACTED_TOKEN]"
        return data
    return data


def emit_execution_log(
    event_type: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
    repo_id: Optional[str] = None,
    task_id: Optional[str] = None,
    worktree_id: Optional[str] = None,
    blob_id: Optional[str] = None,
) -> None:
    """
    Emits a structured JSONL execution record to logs/execution.jsonl.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    ctx = get_correlation_context()
    record = {
        "timestamp": ts,
        "event_type": event_type,
        "status": status,
        "correlation_id": correlation_id or ctx["correlation_id"] or "N/A",
        "repo_id": repo_id or ctx["repo_id"] or "N/A",
        "task_id": task_id or ctx["task_id"] or "N/A",
        "worktree_id": worktree_id or ctx["worktree_id"] or "N/A",
        "blob_id": blob_id or ctx["blob_id"] or "N/A",
        "details": sanitize_log_data(details or {}),
    }

    try:
        with open(LOGS_DIR / "execution.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Could not write to execution.jsonl: {e}")


def setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Clean existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    detailed_formatter = logging.Formatter(
        "%(asctime)s - [%(levelname)s] - %(name)s (%(filename)s:%(lineno)d) - %(message)s"
    )
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )

    # 1. Console Handler: Clean, milestone INFO logs only (no warning/error stack traces on console)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    class NonErrorFilter(logging.Filter):
        def filter(self, record):
            # Suppress WARNING and above from console to keep terminal clean
            return record.levelno < logging.WARNING

    console_handler.addFilter(NonErrorFilter())
    root_logger.addHandler(console_handler)

    # 2. General App Log File (logs/app.log): All debug & info events, rotated (10MB, 5 backups)
    app_file_handler = RotatingFileHandler(
        LOGS_DIR / "app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_file_handler.setLevel(logging.DEBUG)
    app_file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(app_file_handler)

    # 3. Errors & Warnings Log File (logs/errors.log): ONLY Warnings, Errors, Exceptions with full tracebacks
    error_file_handler = RotatingFileHandler(
        LOGS_DIR / "errors.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.WARNING)
    error_file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_file_handler)

    # Silence verbose 3rd-party loggers
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("azure.core").setLevel(logging.WARNING)
    logging.getLogger("azure.storage").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def log_commit_analysis(repo_name: str, commit_info: dict, analysis_id: int, status: str, file_count: int = 0, duration_seconds: float = 0.0):
    """
    Appends structured commit and analysis metadata to logs/commits.log and logs/commits.jsonl.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = {
        "timestamp": ts,
        "analysis_id": analysis_id,
        "repo_name": repo_name,
        "status": status,
        "commit_hash": commit_info.get("hash") if commit_info else None,
        "branch": commit_info.get("branch") if commit_info else None,
        "commit_message": commit_info.get("message") if commit_info else None,
        "author": commit_info.get("author") if commit_info else None,
        "commit_timestamp": commit_info.get("timestamp") if commit_info else None,
        "file_count": file_count,
        "duration_seconds": round(duration_seconds, 2),
    }

    # Structured JSONL log
    try:
        with open(LOGS_DIR / "commits.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Could not write to commits.jsonl: {e}")

    # Human-readable log
    try:
        with open(LOGS_DIR / "commits.log", "a", encoding="utf-8") as f:
            f.write(
                f"[{ts}] Analysis #{analysis_id} | {repo_name} | Status: {status} | "
                f"Commit: {record['commit_hash'] or 'N/A'} ({record['branch'] or 'N/A'}) | "
                f"Msg: {record['commit_message'] or 'N/A'} | Files: {file_count} ({duration_seconds:.2f}s)\n"
            )
    except Exception as e:
        logging.getLogger(__name__).warning(f"Could not write to commits.log: {e}")

