"""
Experiment Runner for Phase 2L A/B experiments.

Orchestrates running complete A/B experiment workflows:
1. Load configuration
2. Run Experiment A (bulk context)
3. Run Experiment B (interactive tools)
4. Compare results
5. Generate report
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .experiment_framework import (
    ExperimentConfig,
    ExperimentType,
    ExperimentResult,
    ExperimentHarness,
    ComparisonReport,
)

logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Orchestrate complete A/B experiment workflows."""

    def __init__(self, output_base_dir: Path):
        """
        Initialize experiment runner.

        Args:
            output_base_dir: Base directory for all experiment outputs
        """
        self.output_base_dir = output_base_dir
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

    def run_complete_experiment(
        self,
        config: ExperimentConfig,
        retriever: Optional[Any] = None,
        llm_service: Optional[Any] = None,
        tools: Optional[List[str]] = None,
    ) -> ComparisonReport:
        """
        Run complete A/B experiment workflow.

        Steps:
        1. Validate configuration
        2. Create output directory
        3. Run Experiment A (bulk context)
        4. Run Experiment B (interactive tools)
        5. Generate comparison report

        Args:
            config: ExperimentConfig with query and settings
            retriever: Retrieval service for bulk context experiment
            llm_service: LLM service for both experiments
            tools: List of available tools for interactive experiment

        Returns:
            ComparisonReport with both results
        """
        # Validate config
        config.validate()

        # Create experiment-specific output directory
        experiment_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        experiment_dir = self.output_base_dir / experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting complete A/B experiment: {experiment_id}")
        logger.info(f"Query: {config.query}")
        logger.info(f"Workspace: {config.workspace_path}")

        # Initialize harness
        harness = ExperimentHarness(config.workspace_path, experiment_dir)

        # Run Experiment A (bulk context)
        logger.info("Running Experiment A (bulk context approach)...")
        bulk_result = harness.run_bulk_context_experiment(
            query=config.query,
            retriever=retriever,
            llm_service=llm_service,
        )
        logger.info(f"Experiment A complete: {bulk_result.duration_seconds:.2f}s")

        # Run Experiment B (interactive tools)
        logger.info("Running Experiment B (interactive tools approach)...")
        interactive_result = harness.run_interactive_tools_experiment(
            query=config.query,
            llm_service=llm_service,
            tools=tools or [],
        )
        logger.info(f"Experiment B complete: {interactive_result.duration_seconds:.2f}s")

        # Compare results
        report = harness.compare_experiments(bulk_result, interactive_result)

        # Save results
        self._save_results(report, experiment_dir)

        logger.info(f"Experiment complete. Results saved to: {experiment_dir}")

        return report

    def run_bulk_context_only(
        self,
        config: ExperimentConfig,
        retriever: Optional[Any] = None,
        llm_service: Optional[Any] = None,
    ) -> ExperimentResult:
        """
        Run only Experiment A (bulk context).

        Useful for isolated testing or baseline establishment.

        Args:
            config: ExperimentConfig with query and settings
            retriever: Retrieval service
            llm_service: LLM service

        Returns:
            ExperimentResult with bulk context metrics
        """
        config.validate()

        experiment_dir = self.output_base_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
        experiment_dir.mkdir(parents=True, exist_ok=True)

        harness = ExperimentHarness(config.workspace_path, experiment_dir)

        result = harness.run_bulk_context_experiment(
            query=config.query,
            retriever=retriever,
            llm_service=llm_service,
        )

        # Save result
        result_file = experiment_dir / "bulk_context_result.json"
        with open(result_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(f"Bulk context experiment saved to: {result_file}")

        return result

    def run_interactive_tools_only(
        self,
        config: ExperimentConfig,
        llm_service: Optional[Any] = None,
        tools: Optional[List[str]] = None,
    ) -> ExperimentResult:
        """
        Run only Experiment B (interactive tools).

        Useful for isolated testing or tool optimization.

        Args:
            config: ExperimentConfig with query and settings
            llm_service: LLM service
            tools: List of available tools

        Returns:
            ExperimentResult with interactive tools metrics
        """
        config.validate()

        experiment_dir = self.output_base_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
        experiment_dir.mkdir(parents=True, exist_ok=True)

        harness = ExperimentHarness(config.workspace_path, experiment_dir)

        result = harness.run_interactive_tools_experiment(
            query=config.query,
            llm_service=llm_service,
            tools=tools or [],
        )

        # Save result
        result_file = experiment_dir / "interactive_tools_result.json"
        with open(result_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(f"Interactive tools experiment saved to: {result_file}")

        return result

    def run_multiple_queries(
        self,
        queries: List[str],
        workspace_path: str,
        retriever: Optional[Any] = None,
        llm_service: Optional[Any] = None,
        tools: Optional[List[str]] = None,
    ) -> List[ComparisonReport]:
        """
        Run complete A/B experiment for multiple queries.

        Useful for comprehensive evaluation across different query types.

        Args:
            queries: List of queries to test
            workspace_path: Repository workspace path
            retriever: Retrieval service
            llm_service: LLM service
            tools: Available tools

        Returns:
            List of ComparisonReports, one per query
        """
        reports = []

        for i, query in enumerate(queries, 1):
            logger.info(f"Running experiment {i}/{len(queries)}: {query}")

            config = ExperimentConfig(
                query=query,
                workspace_path=workspace_path,
                experiment_type=ExperimentType.BULK_CONTEXT,
                output_dir=self.output_base_dir,
            )

            report = self.run_complete_experiment(
                config,
                retriever=retriever,
                llm_service=llm_service,
                tools=tools,
            )

            reports.append(report)

        # Save aggregated results
        aggregated_report = self._aggregate_reports(reports)
        aggregated_file = self.output_base_dir / "aggregated_results.json"
        with open(aggregated_file, "w") as f:
            json.dump(aggregated_report, f, indent=2)

        logger.info(f"All experiments complete. Aggregated results saved to: {aggregated_file}")

        return reports

    def _save_results(self, report: ComparisonReport, experiment_dir: Path) -> None:
        """Save experiment results to files."""
        # Save comparison report
        report_file = experiment_dir / "comparison_report.json"
        with open(report_file, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        # Save bulk result details
        bulk_file = experiment_dir / "bulk_context_details.json"
        with open(bulk_file, "w") as f:
            json.dump(report.bulk_result.to_dict(), f, indent=2)

        # Save interactive result details
        interactive_file = experiment_dir / "interactive_tools_details.json"
        with open(interactive_file, "w") as f:
            json.dump(report.interactive_result.to_dict(), f, indent=2)

        # Save summary report
        summary = self._generate_summary(report)
        summary_file = experiment_dir / "summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Results saved to: {experiment_dir}")
        logger.info(f"  - comparison_report.json: Full A/B comparison")
        logger.info(f"  - bulk_context_details.json: Bulk context metrics")
        logger.info(f"  - interactive_tools_details.json: Interactive tools metrics")
        logger.info(f"  - summary.json: High-level summary")

    def _generate_summary(self, report: ComparisonReport) -> Dict[str, Any]:
        """Generate high-level summary of results."""
        bulk = report.bulk_result
        interactive = report.interactive_result

        return {
            "query": bulk.query,
            "timestamp": datetime.now().isoformat(),
            "bulk_context": {
                "initial_tokens": bulk.initial_context_tokens,
                "context_size_kb": bulk.initial_context_size_kb,
                "files_selected": len(bulk.files_selected),
                "symbols_selected": len(bulk.symbols_selected),
                "correctness": bulk.correctness.value,
                "duration_seconds": bulk.duration_seconds,
            },
            "interactive_tools": {
                "initial_tokens": interactive.initial_context_tokens,
                "final_tokens": interactive.final_context_tokens,
                "peak_tokens": interactive.peak_context_tokens,
                "tool_calls": len(interactive.tool_calls),
                "files_inspected": len(interactive.files_inspected),
                "files_read": len(interactive.files_read),
                "correctness": interactive.correctness.value,
                "duration_seconds": interactive.duration_seconds,
            },
            "comparison": {
                "context_reduction_percent": interactive.context_size_reduction,
                "tool_efficiency_percent": interactive.tool_efficiency,
                "bulk_better_quality": (
                    bulk.correctness.value == "CORRECT" and
                    interactive.correctness.value != "CORRECT"
                ),
                "interactive_more_efficient": (
                    interactive.final_context_tokens < bulk.initial_context_tokens
                ),
            },
        }

    def _aggregate_reports(self, reports: List[ComparisonReport]) -> Dict[str, Any]:
        """Aggregate results from multiple experiment runs."""
        if not reports:
            return {}

        bulk_durations = [r.bulk_result.duration_seconds for r in reports]
        interactive_durations = [r.interactive_result.duration_seconds for r in reports]

        bulk_tokens = [r.bulk_result.initial_context_tokens for r in reports]
        interactive_final_tokens = [r.interactive_result.final_context_tokens for r in reports]

        return {
            "num_experiments": len(reports),
            "bulk_context_stats": {
                "avg_duration_seconds": sum(bulk_durations) / len(bulk_durations),
                "avg_tokens": sum(bulk_tokens) / len(bulk_tokens),
                "min_tokens": min(bulk_tokens),
                "max_tokens": max(bulk_tokens),
            },
            "interactive_tools_stats": {
                "avg_duration_seconds": sum(interactive_durations) / len(interactive_durations),
                "avg_final_tokens": sum(interactive_final_tokens) / len(interactive_final_tokens),
                "min_final_tokens": min(interactive_final_tokens),
                "max_final_tokens": max(interactive_final_tokens),
            },
            "context_reduction": {
                "avg_percent": sum(
                    r.interactive_result.context_size_reduction
                    for r in reports
                ) / len(reports),
            },
            "timestamps": {
                "first_started": min(r.bulk_result.start_time for r in reports).isoformat(),
                "last_ended": max(
                    r.interactive_result.end_time or datetime.now()
                    for r in reports
                ).isoformat(),
            },
        }
