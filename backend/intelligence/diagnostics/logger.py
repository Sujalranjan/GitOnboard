"""
Diagnostic Logger: Comprehensive action logging and error reporting system.

Logs all analyzer actions, relationship creations, and errors to enable:
- Reproducible failure diagnosis
- Action replay for debugging
- Error correlation analysis
- Timeline reconstruction
"""

import json
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class ActionType(Enum):
    ANALYZER_START = "ANALYZER_START"
    ANALYZER_PROCESS_FILE = "ANALYZER_PROCESS_FILE"
    ANALYZER_EXTRACT_ENTITY = "ANALYZER_EXTRACT_ENTITY"
    ANALYZER_EXTRACT_RELATIONSHIP = "ANALYZER_EXTRACT_RELATIONSHIP"
    ANALYZER_ERROR = "ANALYZER_ERROR"
    ANALYZER_COMPLETE = "ANALYZER_COMPLETE"
    AST_PARSE = "AST_PARSE"
    SYMBOL_RESOLUTION = "SYMBOL_RESOLUTION"
    VALIDATION_CHECK = "VALIDATION_CHECK"
    RELATIONSHIP_SKIP = "RELATIONSHIP_SKIP"
    FACT_STORE_SAVE = "FACT_STORE_SAVE"


@dataclass
class DiagnosticAction:
    """Single logged action in the analysis pipeline."""
    timestamp: str
    action_type: str
    analyzer_name: str
    file_path: str
    message: str
    details: Dict[str, Any]
    error: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiagnosticReport:
    """Comprehensive diagnostic report for a single analysis."""
    analysis_id: int
    repository_name: str
    start_time: str
    end_time: str
    total_files_processed: int
    total_entities_created: int
    total_relationships_created: int
    relationship_breakdown: Dict[str, int]
    analyzers_executed: List[str]
    errors_encountered: List[Dict[str, Any]]
    actions: List[DiagnosticAction]
    skipped_relationships: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "repository_name": self.repository_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_files_processed": self.total_files_processed,
            "total_entities_created": self.total_entities_created,
            "total_relationships_created": self.total_relationships_created,
            "relationship_breakdown": self.relationship_breakdown,
            "analyzers_executed": self.analyzers_executed,
            "errors_encountered": self.errors_encountered,
            "actions_count": len(self.actions),
            "skipped_relationships_count": len(self.skipped_relationships),
        }


class DiagnosticLogger:
    """
    Logs all analysis pipeline actions for debugging and reproducibility.

    Features:
    - Real-time action logging
    - Error capture with stack traces
    - Relationship tracking (created vs skipped)
    - Summary report generation
    - JSON persistence for post-mortem analysis
    """

    def __init__(self, analysis_id: int, repository_name: str, log_dir: Optional[Path] = None):
        self.analysis_id = analysis_id
        self.repository_name = repository_name
        self.logger = logging.getLogger(f"diagnostic.{analysis_id}")

        # Initialize log directory
        self.log_dir = log_dir or Path("/tmp/rim_diagnostics")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.start_time = datetime.utcnow().isoformat()
        self.actions: List[DiagnosticAction] = []
        self.errors: List[Dict[str, Any]] = []
        self.skipped_relationships: List[Dict[str, Any]] = []
        self.relationship_counts: Dict[str, int] = {}
        self.files_processed: set = set()
        self.entities_created: set = set()
        self.analyzers: set = set()

    def log_action(
        self,
        action_type: ActionType,
        analyzer_name: str,
        file_path: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a successful action."""
        action = DiagnosticAction(
            timestamp=datetime.utcnow().isoformat(),
            action_type=action_type.value,
            analyzer_name=analyzer_name,
            file_path=file_path,
            message=message,
            details=details or {},
        )
        self.actions.append(action)
        self.logger.info(f"[{action_type.value}] {analyzer_name} @ {file_path}: {message}")

    def log_error(
        self,
        action_type: ActionType,
        analyzer_name: str,
        file_path: str,
        message: str,
        exception: Exception,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an error with full stack trace."""
        stack_trace = traceback.format_exc()
        error_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "analyzer": analyzer_name,
            "file": file_path,
            "message": message,
            "exception": str(exception),
            "type": type(exception).__name__,
        }
        self.errors.append(error_record)

        action = DiagnosticAction(
            timestamp=datetime.utcnow().isoformat(),
            action_type=action_type.value,
            analyzer_name=analyzer_name,
            file_path=file_path,
            message=message,
            details=details or {},
            error=str(exception),
            stack_trace=stack_trace,
        )
        self.actions.append(action)
        self.logger.error(
            f"[{action_type.value}] {analyzer_name} @ {file_path}: {message}\n{stack_trace}"
        )

    def log_relationship_created(
        self,
        analyzer_name: str,
        rel_type: str,
        source_id: str,
        target_id: str,
        file_path: str,
    ) -> None:
        """Log a successfully created relationship."""
        self.relationship_counts[rel_type] = self.relationship_counts.get(rel_type, 0) + 1
        self.log_action(
            ActionType.ANALYZER_EXTRACT_RELATIONSHIP,
            analyzer_name,
            file_path,
            f"Created {rel_type} relationship",
            {
                "rel_type": rel_type,
                "source": source_id,
                "target": target_id,
            },
        )

    def log_relationship_skipped(
        self,
        analyzer_name: str,
        rel_type: str,
        source_id: str,
        target_id: str,
        reason: str,
        file_path: str,
    ) -> None:
        """Log a relationship that was skipped."""
        skip_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "analyzer": analyzer_name,
            "type": rel_type,
            "source": source_id,
            "target": target_id,
            "reason": reason,
            "file": file_path,
        }
        self.skipped_relationships.append(skip_record)
        self.log_action(
            ActionType.RELATIONSHIP_SKIP,
            analyzer_name,
            file_path,
            f"Skipped {rel_type} relationship: {reason}",
            {
                "rel_type": rel_type,
                "source": source_id,
                "target": target_id,
                "reason": reason,
            },
        )

    def log_analyzer_start(self, analyzer_name: str, file_count: int) -> None:
        """Log analyzer initialization."""
        self.analyzers.add(analyzer_name)
        self.log_action(
            ActionType.ANALYZER_START,
            analyzer_name,
            "",
            f"Starting analyzer for {file_count} files",
            {"file_count": file_count},
        )

    def log_analyzer_complete(
        self, analyzer_name: str, files_processed: int, relationships_created: int
    ) -> None:
        """Log analyzer completion."""
        self.log_action(
            ActionType.ANALYZER_COMPLETE,
            analyzer_name,
            "",
            f"Analyzer complete",
            {
                "files_processed": files_processed,
                "relationships_created": relationships_created,
            },
        )

    def log_file_processed(self, file_path: str, parser_type: str, ast_type: str) -> None:
        """Log file parsing."""
        self.files_processed.add(file_path)
        self.log_action(
            ActionType.AST_PARSE,
            "Parser",
            file_path,
            f"Parsed as {parser_type}",
            {"parser_type": parser_type, "ast_type": ast_type},
        )

    def log_symbol_resolved(
        self, analyzer_name: str, symbol_name: str, resolution_method: str, file_path: str
    ) -> None:
        """Log symbol resolution."""
        self.log_action(
            ActionType.SYMBOL_RESOLUTION,
            analyzer_name,
            file_path,
            f"Resolved symbol via {resolution_method}",
            {"symbol": symbol_name, "method": resolution_method},
        )

    def log_validation_check(
        self, check_type: str, passed: bool, details: Dict[str, Any], file_path: str = ""
    ) -> None:
        """Log validation check result."""
        self.log_action(
            ActionType.VALIDATION_CHECK,
            "Validator",
            file_path,
            f"Validation {'PASSED' if passed else 'FAILED'}: {check_type}",
            {"check_type": check_type, "passed": passed, **details},
        )

    def log_entity_created(
        self, entity_id: str, entity_type: str, entity_name: str, file_path: str
    ) -> None:
        """Log entity creation."""
        self.entities_created.add(entity_id)
        self.log_action(
            ActionType.ANALYZER_EXTRACT_ENTITY,
            "Analyzer",
            file_path,
            f"Created {entity_type}",
            {"entity_id": entity_id, "entity_type": entity_type, "entity_name": entity_name},
        )

    def generate_report(self) -> DiagnosticReport:
        """Generate comprehensive diagnostic report."""
        end_time = datetime.utcnow().isoformat()

        report = DiagnosticReport(
            analysis_id=self.analysis_id,
            repository_name=self.repository_name,
            start_time=self.start_time,
            end_time=end_time,
            total_files_processed=len(self.files_processed),
            total_entities_created=len(self.entities_created),
            total_relationships_created=sum(self.relationship_counts.values()),
            relationship_breakdown=dict(self.relationship_counts),
            analyzers_executed=sorted(list(self.analyzers)),
            errors_encountered=self.errors,
            actions=self.actions,
            skipped_relationships=self.skipped_relationships,
        )
        return report

    def save_report(self) -> Path:
        """Save diagnostic report to JSON file."""
        report = self.generate_report()
        report_dict = report.to_dict()
        report_dict["actions"] = [action.to_dict() for action in report.actions]

        report_file = self.log_dir / f"analysis_{self.analysis_id}_report.json"
        with open(report_file, "w") as f:
            json.dump(report_dict, f, indent=2)

        self.logger.info(f"Diagnostic report saved to {report_file}")
        return report_file

    def save_actions(self) -> Path:
        """Save detailed actions log for replay."""
        actions_file = self.log_dir / f"analysis_{self.analysis_id}_actions.jsonl"
        with open(actions_file, "w") as f:
            for action in self.actions:
                f.write(json.dumps(action.to_dict()) + "\n")

        self.logger.info(f"Actions log saved to {actions_file} ({len(self.actions)} actions)")
        return actions_file

    def print_summary(self) -> str:
        """Print human-readable summary."""
        report = self.generate_report()
        summary = f"""
{'=' * 80}
DIAGNOSTIC REPORT: Analysis {self.analysis_id}
{'=' * 80}
Repository: {self.repository_name}
Start Time: {report.start_time}
End Time: {report.end_time}

FILES & ENTITIES:
  Files Processed: {report.total_files_processed}
  Entities Created: {report.total_entities_created}
  Total Relationships: {report.total_relationships_created}

RELATIONSHIP BREAKDOWN:
{chr(10).join(f'  {k}: {v}' for k, v in sorted(report.relationship_breakdown.items()))}

ANALYZERS EXECUTED:
{chr(10).join(f'  - {a}' for a in report.analyzers_executed)}

ERRORS: {len(report.errors_encountered)}
{chr(10).join(f'  - {e["analyzer"]} @ {e["file"]}: {e["message"]}' for e in report.errors_encountered[:5])}

SKIPPED RELATIONSHIPS: {len(report.skipped_relationships)}
{chr(10).join(f'  - {s["type"]} ({s["reason"]})' for s in report.skipped_relationships[:5])}

LOGS SAVED TO: {self.log_dir}/analysis_{self.analysis_id}_*
{'=' * 80}
"""
        print(summary)
        return summary


# Global diagnostic logger instance
_diagnostic_logger: Optional[DiagnosticLogger] = None


def get_diagnostic_logger() -> Optional[DiagnosticLogger]:
    """Get the current diagnostic logger."""
    return _diagnostic_logger


def init_diagnostic_logger(analysis_id: int, repository_name: str) -> DiagnosticLogger:
    """Initialize diagnostic logger for an analysis."""
    global _diagnostic_logger
    _diagnostic_logger = DiagnosticLogger(analysis_id, repository_name)
    return _diagnostic_logger
