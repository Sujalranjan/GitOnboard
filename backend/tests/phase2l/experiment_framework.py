"""
A/B Experiment Framework for Phase 2L.

Framework for comparing bulk-context approach (Experiment A) vs.
interactive-tools approach (Experiment B).

Provides:
- ExperimentConfig: Configuration for experiments
- ExperimentResult: Recorded results and metrics
- ExperimentRecorder: Detailed execution tracing
- ExperimentHarness: Orchestrates experiment execution
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import json
import uuid


class ExperimentType(str, Enum):
    """Type of A/B experiment."""

    BULK_CONTEXT = "BULK_CONTEXT"
    """Existing approach: retrieve files/symbols, expand, select top N, send all to LLM."""

    INTERACTIVE_TOOLS = "INTERACTIVE_TOOLS"
    """New approach: provide initial context, LLM calls tools to inspect/read as needed."""


class CorrectnessLevel(str, Enum):
    """Answer correctness assessment."""

    CORRECT = "CORRECT"
    """Answer is factually correct and complete."""

    PARTIAL = "PARTIAL"
    """Answer is partially correct or incomplete."""

    INCORRECT = "INCORRECT"
    """Answer is factually incorrect."""


@dataclass
class ExperimentConfig:
    """Configuration for a single A/B experiment."""

    query: str
    """User query to analyze."""

    workspace_path: str
    """Path to repository workspace."""

    experiment_type: ExperimentType
    """Type of experiment: BULK_CONTEXT or INTERACTIVE_TOOLS."""

    output_dir: Path
    """Directory to save experiment results and traces."""

    record_tool_calls: bool = True
    """Whether to record tool calls and arguments."""

    record_tokens: bool = True
    """Whether to record token usage."""

    record_files_accessed: bool = True
    """Whether to record files inspected and read."""

    seed: Optional[int] = None
    """Random seed for reproducibility."""

    def validate(self) -> None:
        """Validate configuration."""
        if not self.query:
            raise ValueError("query cannot be empty")
        if not self.workspace_path:
            raise ValueError("workspace_path cannot be empty")
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class ExperimentResult:
    """Results from a single A/B experiment."""

    # Identifiers
    query: str
    experiment_type: ExperimentType
    experiment_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Bulk context metrics
    files_selected: List[str] = field(default_factory=list)
    """Files selected for bulk context approach."""

    symbols_selected: List[str] = field(default_factory=list)
    """Symbols selected for bulk context approach."""

    evidence_count: int = 0
    """Number of evidence items in initial context."""

    initial_context_tokens: int = 0
    """Total tokens in initial bulk context."""

    initial_context_size_kb: float = 0.0
    """Size of initial context in KB."""

    # Interactive tools metrics
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    """List of tool call records."""

    files_inspected: List[str] = field(default_factory=list)
    """Files inspected (not read full content)."""

    files_read: List[str] = field(default_factory=list)
    """Files with full content read."""

    symbols_read: List[str] = field(default_factory=list)
    """Symbols for which full source was read."""

    peak_context_tokens: int = 0
    """Peak tokens used during interactive approach."""

    final_context_tokens: int = 0
    """Final tokens in context after experiment."""

    # Quality metrics
    answer: str = ""
    """LLM's final answer to the query."""

    grounded_facts: List[str] = field(default_factory=list)
    """Facts mentioned in answer that are grounded in evidence."""

    irrelevant_context_included: bool = False
    """Whether irrelevant context was included."""

    irrelevant_sources: List[str] = field(default_factory=list)
    """Sources that didn't contribute to answer."""

    correctness: CorrectnessLevel = CorrectnessLevel.PARTIAL
    """Assessment of answer correctness."""

    # Timing
    start_time: datetime = field(default_factory=datetime.now)
    """When experiment started."""

    end_time: Optional[datetime] = None
    """When experiment ended."""

    # Tool invocation trace (for replay/audit)
    tool_call_trace: List[Dict[str, Any]] = field(default_factory=list)
    """Detailed trace of all tool calls for audit/replay."""

    @property
    def duration_seconds(self) -> float:
        """Calculate experiment duration."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

    @property
    def context_size_reduction(self) -> float:
        """Calculate context size reduction (interactive vs. bulk)."""
        if self.initial_context_tokens == 0:
            return 0.0
        reduction = self.initial_context_tokens - self.final_context_tokens
        return (reduction / self.initial_context_tokens) * 100

    @property
    def tool_efficiency(self) -> float:
        """Calculate tool efficiency (relevant context / total context)."""
        if self.final_context_tokens == 0:
            return 0.0
        relevant_tokens = self.final_context_tokens - sum(
            self.initial_context_size_kb * 1024 / 4
            for _ in self.irrelevant_sources
        )
        return (relevant_tokens / self.final_context_tokens) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "experiment_id": self.experiment_id,
            "query": self.query,
            "experiment_type": self.experiment_type.value,
            "files_selected": self.files_selected,
            "symbols_selected": self.symbols_selected,
            "evidence_count": self.evidence_count,
            "initial_context_tokens": self.initial_context_tokens,
            "initial_context_size_kb": self.initial_context_size_kb,
            "tool_calls_count": len(self.tool_calls),
            "files_inspected": self.files_inspected,
            "files_read": self.files_read,
            "symbols_read": self.symbols_read,
            "peak_context_tokens": self.peak_context_tokens,
            "final_context_tokens": self.final_context_tokens,
            "answer": self.answer,
            "grounded_facts": self.grounded_facts,
            "irrelevant_context_included": self.irrelevant_context_included,
            "irrelevant_sources": self.irrelevant_sources,
            "correctness": self.correctness.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "context_size_reduction_percent": self.context_size_reduction,
            "tool_efficiency_percent": self.tool_efficiency,
        }


@dataclass
class ComparisonReport:
    """Comparison of bulk context vs. interactive tools results."""

    bulk_result: ExperimentResult
    interactive_result: ExperimentResult

    def context_size_advantage(self) -> Dict[str, Any]:
        """Compare context sizes."""
        return {
            "bulk_context_tokens": self.bulk_result.initial_context_tokens,
            "interactive_initial_tokens": self.interactive_result.initial_context_tokens,
            "interactive_final_tokens": self.interactive_result.final_context_tokens,
            "reduction_percent": self.interactive_result.context_size_reduction,
        }

    def tool_efficiency_analysis(self) -> Dict[str, Any]:
        """Analyze tool usage efficiency."""
        return {
            "total_tool_calls": len(self.interactive_result.tool_calls),
            "files_inspected": len(self.interactive_result.files_inspected),
            "files_read": len(self.interactive_result.files_read),
            "symbols_read": len(self.interactive_result.symbols_read),
            "efficiency_percent": self.interactive_result.tool_efficiency,
        }

    def quality_comparison(self) -> Dict[str, Any]:
        """Compare answer quality."""
        return {
            "bulk_correctness": self.bulk_result.correctness.value,
            "interactive_correctness": self.interactive_result.correctness.value,
            "bulk_grounded_facts": len(self.bulk_result.grounded_facts),
            "interactive_grounded_facts": len(self.interactive_result.grounded_facts),
            "bulk_irrelevant_included": self.bulk_result.irrelevant_context_included,
            "interactive_irrelevant_included": self.interactive_result.irrelevant_context_included,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "bulk_result": self.bulk_result.to_dict(),
            "interactive_result": self.interactive_result.to_dict(),
            "context_size_advantage": self.context_size_advantage(),
            "tool_efficiency_analysis": self.tool_efficiency_analysis(),
            "quality_comparison": self.quality_comparison(),
        }


class ExperimentRecorder:
    """Record detailed execution trace during experiments."""

    def __init__(self, output_dir: Path):
        """Initialize recorder."""
        self.output_dir = output_dir
        self.tool_calls: List[Dict[str, Any]] = []
        self.files_accessed: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []

    def record_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
        tokens_used: int,
        duration_ms: float,
    ) -> None:
        """Record a tool invocation."""
        self.tool_calls.append({
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "args": args,
            "result_summary": {
                k: (
                    f"<{len(v)} items>" if isinstance(v, list)
                    else f"<{len(str(v))} chars>" if isinstance(v, str)
                    else v
                )
                for k, v in result.items()
            },
            "tokens_used": tokens_used,
            "duration_ms": duration_ms,
        })

    def record_file_read(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        tokens_used: int,
    ) -> None:
        """Record file read operation."""
        self.files_accessed.append({
            "timestamp": datetime.now().isoformat(),
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "lines_read": end_line - start_line + 1,
            "tokens_used": tokens_used,
        })

    def record_event(self, event_type: str, description: str, data: Optional[Dict] = None) -> None:
        """Record a generic event."""
        self.events.append({
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "description": description,
            "data": data or {},
        })

    def save_trace(self, trace_file: Path) -> None:
        """Save complete trace to JSON file."""
        trace = {
            "tool_calls": self.tool_calls,
            "files_accessed": self.files_accessed,
            "events": self.events,
            "saved_at": datetime.now().isoformat(),
        }
        with open(trace_file, "w") as f:
            json.dump(trace, f, indent=2)

    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to dictionary."""
        return {
            "tool_calls": self.tool_calls,
            "files_accessed": self.files_accessed,
            "events": self.events,
        }


class ExperimentHarness:
    """Orchestrate A/B experiments."""

    def __init__(self, workspace_path: str, output_dir: Path):
        """Initialize harness."""
        self.workspace_path = workspace_path
        self.output_dir = output_dir

    def run_bulk_context_experiment(
        self,
        query: str,
        retriever,
        llm_service,
    ) -> ExperimentResult:
        """
        Run bulk-context experiment.

        Simulates current approach:
        1. Retrieve relevant files/symbols
        2. Expand via RIM
        3. Select top N files + content
        4. Send all to LLM
        5. Record metrics
        """
        result = ExperimentResult(
            query=query,
            experiment_type=ExperimentType.BULK_CONTEXT,
        )

        result.start_time = datetime.now()

        try:
            # 1. Initial retrieval
            retrieval_results = retriever.retrieve(query, limit=10)
            result.evidence_count = len(retrieval_results)

            # Extract files and symbols
            files = set()
            symbols = set()
            for item in retrieval_results:
                if hasattr(item, "file"):
                    files.add(item.file)
                if hasattr(item, "symbol"):
                    symbols.add(item.symbol)

            result.files_selected = sorted(files)
            result.symbols_selected = sorted(symbols)

            # 2. Aggregate content for selected items
            # (In real experiment, would read full files)
            context_size = 0
            for file in files:
                # Estimate: ~10KB per file
                context_size += 10240
            for symbol in symbols:
                # Estimate: ~2KB per symbol
                context_size += 2048

            result.initial_context_size_kb = context_size / 1024
            result.initial_context_tokens = int(context_size / 4)  # Rough estimation

            # 3. Send to LLM
            # (In real experiment, would call actual LLM)
            result.answer = f"Bulk context analysis for: {query}"

            result.end_time = datetime.now()

        except Exception as e:
            result.end_time = datetime.now()
            result.answer = f"Error during bulk context experiment: {str(e)}"

        return result

    def run_interactive_tools_experiment(
        self,
        query: str,
        llm_service,
        tools,
        max_tool_calls: int = 20,
    ) -> ExperimentResult:
        """
        Run interactive-tools experiment.

        Simulates new approach:
        1. Provide initial RIM context (small)
        2. Allow LLM to call tools (inspect, read, etc.)
        3. Track each tool call
        4. Monitor context growth
        5. Record all metrics
        """
        result = ExperimentResult(
            query=query,
            experiment_type=ExperimentType.INTERACTIVE_TOOLS,
        )

        result.start_time = datetime.now()
        recorder = ExperimentRecorder(self.output_dir)

        try:
            # 1. Initial context from RIM (small)
            result.initial_context_tokens = 2000  # Small initial context
            result.initial_context_size_kb = 8.0

            # 2. Simulate tool-driven loop
            # (In real experiment, would call actual LLM + tool loop)
            tool_calls_made = 0
            current_tokens = result.initial_context_tokens

            for _ in range(min(max_tool_calls, 10)):  # Limit to 10 calls for simulation
                # Simulate tool call
                tool_name = "inspect_file"
                tokens_for_call = 500

                recorder.record_tool_call(
                    tool_name=tool_name,
                    args={"pattern": "*.py"},
                    result={"matches": ["file1.py", "file2.py"]},
                    tokens_used=tokens_for_call,
                    duration_ms=150,
                )

                current_tokens += tokens_for_call
                tool_calls_made += 1
                result.peak_context_tokens = max(result.peak_context_tokens, current_tokens)

            result.tool_calls = recorder.tool_calls
            result.final_context_tokens = current_tokens

            # Record trace
            trace_file = self.output_dir / f"experiment_{result.experiment_id}_trace.json"
            recorder.save_trace(trace_file)

            result.answer = f"Interactive analysis for: {query} ({tool_calls_made} tool calls)"

            result.end_time = datetime.now()

        except Exception as e:
            result.end_time = datetime.now()
            result.answer = f"Error during interactive tools experiment: {str(e)}"

        return result

    def compare_experiments(
        self,
        bulk_result: ExperimentResult,
        interactive_result: ExperimentResult,
    ) -> ComparisonReport:
        """Compare results from both experiments."""
        return ComparisonReport(
            bulk_result=bulk_result,
            interactive_result=interactive_result,
        )
