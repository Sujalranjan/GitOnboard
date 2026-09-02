"""
Comprehensive structured logging for RIM testing and debugging.

Logs complete data flow from frontend query to LLM responses,
including all intermediate stages, RIM contributions, and tool calls.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import traceback

# Create logs directory
LOGS_DIR = Path("/home/dheeraj/repository_intelligence_platform/logs")
LOGS_DIR.mkdir(exist_ok=True)

# Create subdirectories for different log types
(LOGS_DIR / "queries").mkdir(exist_ok=True)
(LOGS_DIR / "llm_requests").mkdir(exist_ok=True)
(LOGS_DIR / "tool_calls").mkdir(exist_ok=True)
(LOGS_DIR / "metrics").mkdir(exist_ok=True)
(LOGS_DIR / "errors").mkdir(exist_ok=True)
(LOGS_DIR / "rim_trace").mkdir(exist_ok=True)


@dataclass
class QueryLog:
    """Frontend query data"""
    timestamp: str
    repository: str
    question: str
    session_id: str
    request_id: str
    user_email: Optional[str] = None


@dataclass
class LLMRequestLog:
    """LLM request data"""
    timestamp: str
    request_id: str
    session_id: str
    model: str
    provider: str
    is_rim: bool
    system_prompt_length: int
    system_prompt_hash: str
    user_message: str
    tools_available: List[str]
    context_tokens_estimate: int


@dataclass
class LLMResponseLog:
    """LLM response data"""
    timestamp: str
    request_id: str
    session_id: str
    response_text: str
    stop_reason: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    model: str


@dataclass
class ToolCallLog:
    """Individual tool call data"""
    timestamp: str
    request_id: str
    session_id: str
    turn_number: int
    tool_name: str
    tool_arguments: Dict[str, Any]
    is_rim: bool
    execution_time_ms: float
    success: bool
    error: Optional[str] = None
    result_size_bytes: Optional[int] = None
    result_summary: Optional[str] = None


@dataclass
class RIMContributionLog:
    """RIM metadata contribution at each stage"""
    timestamp: str
    request_id: str
    session_id: str
    stage: str  # "metadata_building", "query_execution", "tool_selection", "answer_refinement"
    rim_entities_found: int
    rim_relationships_found: int
    rim_confidence_score: float
    impacted_tools: List[str]
    metadata_block_size_bytes: int


@dataclass
class MetricsLog:
    """Comparison metrics"""
    timestamp: str
    request_id: str
    session_id: str
    repository: str
    question: str
    baseline_tool_calls: int
    rim_tool_calls: int
    baseline_files_retrieved: int
    rim_files_retrieved: int
    baseline_symbols_retrieved: int
    rim_symbols_retrieved: int
    rim_entities_accessed: int
    baseline_latency_ms: float
    rim_latency_ms: float
    semantic_degradation: Optional[str]
    answer_quality_score: Optional[float] = None
    failure_detected: bool = False
    failure_reason: Optional[str] = None


class StructuredLogger:
    """Structured logging for complete tracing"""

    def __init__(self, session_id: str, repository: str):
        self.session_id = session_id
        self.repository = repository
        self.request_id = None
        self.start_time = datetime.utcnow()

        # Create session-specific subdirectory
        self.session_dir = LOGS_DIR / f"{session_id}_{repository}_{self.start_time.strftime('%Y%m%d_%H%M%S')}"
        self.session_dir.mkdir(exist_ok=True)

        # Setup base logger
        self.logger = logging.getLogger(f"structured_{session_id}")
        self.logger.setLevel(logging.DEBUG)

    def log_query(self, question: str, user_email: Optional[str] = None) -> str:
        """Log incoming frontend query"""
        from uuid import uuid4
        self.request_id = str(uuid4())[:8]

        query_log = QueryLog(
            timestamp=datetime.utcnow().isoformat(),
            repository=self.repository,
            question=question,
            session_id=self.session_id,
            request_id=self.request_id,
            user_email=user_email
        )

        log_file = self.session_dir / f"01_query_{self.request_id}.json"
        with open(log_file, "w") as f:
            json.dump(asdict(query_log), f, indent=2)

        self.logger.info(f"Query logged: {self.request_id}")
        return self.request_id

    def log_llm_request(self, model: str, provider: str, is_rim: bool,
                       system_prompt: str, user_message: str,
                       tools_available: List[str], context_tokens: int):
        """Log LLM request before sending"""
        import hashlib

        prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]

        llm_req = LLMRequestLog(
            timestamp=datetime.utcnow().isoformat(),
            request_id=self.request_id,
            session_id=self.session_id,
            model=model,
            provider=provider,
            is_rim=is_rim,
            system_prompt_length=len(system_prompt),
            system_prompt_hash=prompt_hash,
            user_message=user_message,
            tools_available=tools_available,
            context_tokens_estimate=context_tokens
        )

        rim_label = "rim" if is_rim else "baseline"
        log_file = self.session_dir / f"02_llm_request_{self.request_id}_{rim_label}.json"
        with open(log_file, "w") as f:
            json.dump(asdict(llm_req), f, indent=2)

        # Also save system prompt separately for inspection
        prompt_file = self.session_dir / f"02_system_prompt_{self.request_id}_{rim_label}.txt"
        with open(prompt_file, "w") as f:
            f.write(system_prompt)

        self.logger.info(f"LLM request logged: {rim_label}")

    def log_llm_response(self, response_text: str, stop_reason: str,
                         prompt_tokens: int, completion_tokens: int,
                         latency_ms: float, model: str, is_rim: bool):
        """Log LLM response after receiving"""
        llm_resp = LLMResponseLog(
            timestamp=datetime.utcnow().isoformat(),
            request_id=self.request_id,
            session_id=self.session_id,
            response_text=response_text,
            stop_reason=stop_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            model=model
        )

        rim_label = "rim" if is_rim else "baseline"
        log_file = self.session_dir / f"03_llm_response_{self.request_id}_{rim_label}.json"
        with open(log_file, "w") as f:
            json.dump(asdict(llm_resp), f, indent=2)

        # Save response text separately
        response_file = self.session_dir / f"03_response_text_{self.request_id}_{rim_label}.txt"
        with open(response_file, "w") as f:
            f.write(response_text)

        self.logger.info(f"LLM response logged: {rim_label}, tokens={prompt_tokens + completion_tokens}, latency={latency_ms:.1f}ms")

    def log_tool_call(self, tool_name: str, arguments: Dict[str, Any],
                      is_rim: bool, turn_number: int, execution_time_ms: float,
                      success: bool, result: Optional[Dict[str, Any]] = None,
                      error: Optional[str] = None):
        """Log individual tool call"""
        result_size = 0
        result_summary = None
        if result:
            if isinstance(result, dict):
                result_size = len(json.dumps(result))
                result_summary = str(result)[:500]  # First 500 chars

        tool_call = ToolCallLog(
            timestamp=datetime.utcnow().isoformat(),
            request_id=self.request_id,
            session_id=self.session_id,
            turn_number=turn_number,
            tool_name=tool_name,
            tool_arguments=arguments,
            is_rim=is_rim,
            execution_time_ms=execution_time_ms,
            success=success,
            error=error,
            result_size_bytes=result_size,
            result_summary=result_summary
        )

        rim_label = "rim" if is_rim else "baseline"
        log_file = self.session_dir / f"04_tool_call_{self.request_id}_{rim_label}_turn{turn_number}_{tool_name}.json"
        with open(log_file, "w") as f:
            json.dump(asdict(tool_call), f, indent=2)

        # Save full result separately if available
        if result:
            result_file = self.session_dir / f"04_tool_result_{self.request_id}_{rim_label}_turn{turn_number}_{tool_name}.json"
            with open(result_file, "w") as f:
                json.dump(result, f, indent=2)

        status = "✓" if success else "✗"
        self.logger.info(f"Tool call logged {status}: {tool_name} ({rim_label}, turn {turn_number}, {execution_time_ms:.0f}ms)")

    def log_rim_contribution(self, stage: str, entities_found: int,
                            relationships_found: int, confidence: float,
                            impacted_tools: List[str], metadata_size: int):
        """Log RIM metadata contribution at each stage"""
        rim_contrib = RIMContributionLog(
            timestamp=datetime.utcnow().isoformat(),
            request_id=self.request_id,
            session_id=self.session_id,
            stage=stage,
            rim_entities_found=entities_found,
            rim_relationships_found=relationships_found,
            rim_confidence_score=confidence,
            impacted_tools=impacted_tools,
            metadata_block_size_bytes=metadata_size
        )

        log_file = self.session_dir / f"05_rim_contribution_{self.request_id}_{stage}.json"
        with open(log_file, "w") as f:
            json.dump(asdict(rim_contrib), f, indent=2)

        self.logger.info(f"RIM contribution logged: {stage}, entities={entities_found}, confidence={confidence:.2f}")

    def log_metrics(self, question: str, baseline_metrics: Dict[str, Any],
                   rim_metrics: Dict[str, Any], failure_detected: bool = False,
                   failure_reason: Optional[str] = None):
        """Log final comparison metrics"""
        metrics = MetricsLog(
            timestamp=datetime.utcnow().isoformat(),
            request_id=self.request_id,
            session_id=self.session_id,
            repository=self.repository,
            question=question,
            baseline_tool_calls=baseline_metrics.get("tool_call_count", 0),
            rim_tool_calls=rim_metrics.get("tool_call_count", 0),
            baseline_files_retrieved=baseline_metrics.get("files_retrieved", 0),
            rim_files_retrieved=rim_metrics.get("files_retrieved", 0),
            baseline_symbols_retrieved=baseline_metrics.get("symbols_retrieved", 0),
            rim_symbols_retrieved=rim_metrics.get("symbols_retrieved", 0),
            rim_entities_accessed=rim_metrics.get("rim_entities_accessed_count", 0),
            baseline_latency_ms=baseline_metrics.get("retrieval_latency_ms", 0),
            rim_latency_ms=rim_metrics.get("retrieval_latency_ms", 0),
            semantic_degradation=rim_metrics.get("semantic_degradation", None),
            failure_detected=failure_detected,
            failure_reason=failure_reason
        )

        log_file = self.session_dir / f"06_metrics_{self.request_id}.json"
        with open(log_file, "w") as f:
            json.dump(asdict(metrics), f, indent=2)

        if failure_detected:
            # Also save to errors directory
            error_file = LOGS_DIR / "errors" / f"{self.request_id}_{self.repository}.json"
            with open(error_file, "w") as f:
                json.dump(asdict(metrics), f, indent=2)
            self.logger.error(f"Failure detected: {failure_reason}")
        else:
            self.logger.info("Metrics logged successfully")

    def log_error(self, stage: str, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Log errors with full stack trace and context"""
        error_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": self.request_id,
            "session_id": self.session_id,
            "stage": stage,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "context": context or {}
        }

        error_file = self.session_dir / f"99_error_{self.request_id}_{stage}.json"
        with open(error_file, "w") as f:
            json.dump(error_log, f, indent=2)

        # Also save to errors directory
        error_dir_file = LOGS_DIR / "errors" / f"{self.request_id}_{stage}.json"
        with open(error_dir_file, "w") as f:
            json.dump(error_log, f, indent=2)

        self.logger.error(f"Error in {stage}: {type(error).__name__}: {str(error)}")

    def log_completion(self, success: bool, summary: Dict[str, Any]):
        """Log completion of the entire request"""
        completion_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": self.request_id,
            "session_id": self.session_id,
            "success": success,
            "total_duration_ms": (datetime.utcnow() - self.start_time).total_seconds() * 1000,
            "summary": summary
        }

        completion_file = self.session_dir / f"07_completion_{self.request_id}.json"
        with open(completion_file, "w") as f:
            json.dump(completion_log, f, indent=2)

        status = "✓ SUCCESS" if success else "✗ FAILURE"
        self.logger.info(f"Request completed {status}: {self.request_id}")

    def get_session_logs(self) -> Path:
        """Return path to session logs directory"""
        return self.session_dir
