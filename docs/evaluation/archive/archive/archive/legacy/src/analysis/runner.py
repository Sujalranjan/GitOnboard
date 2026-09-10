import time
import logging
from typing import TYPE_CHECKING, List
from .interfaces import Analyzer
from .registry import AnalyzerRegistry
from .exceptions import AnalysisExecutionError
from .models.report import AnalysisReport
from .models.result import AnalysisResult
from .models.finding import Finding

if TYPE_CHECKING:
    from rim.models import Repository

logger = logging.getLogger(__name__)

class AnalysisRunner:
    def __init__(self, registry: AnalyzerRegistry):
        self.registry = registry

    def run(self, repository: 'Repository') -> AnalysisReport:
        """Execute all registered analyzers sequentially and aggregate results."""
        results: List[AnalysisResult] = []
        overall_findings: List[Finding] = []
        
        analyzers_classes = self.registry.get_all()
        start_time = time.time()
        
        execution_summary = {
            "total_analyzers": len(analyzers_classes),
            "successful": 0,
            "failed": 0,
            "errors": {}
        }
        
        for analyzer_class in analyzers_classes:
            try:
                analyzer_instance = analyzer_class()
                analyzer_name = analyzer_instance.name
            except Exception as e:
                logger.error(f"Failed to instantiate analyzer {analyzer_class.__name__}: {e}")
                execution_summary["failed"] += 1
                execution_summary["errors"][analyzer_class.__name__] = str(e)
                continue
                
            logger.info(f"Running analyzer: {analyzer_name}")
            
            analyzer_start = time.time()
            try:
                result = analyzer_instance.analyze(repository)
                # Ensure duration is set
                if result.duration == 0.0:
                    result.duration = time.time() - analyzer_start
                results.append(result)
                overall_findings.extend(result.findings)
                execution_summary["successful"] += 1
            except Exception as e:
                logger.error(f"Analyzer {analyzer_name} failed: {e}")
                execution_summary["failed"] += 1
                execution_summary["errors"][analyzer_name] = str(e)
                # Execution policy: Catch and log, do not halt the pipeline
        
        total_duration = time.time() - start_time
        execution_summary["total_duration_seconds"] = total_duration
        
        return AnalysisReport(
            results=results,
            overall_findings=overall_findings,
            execution_summary=execution_summary
        )
