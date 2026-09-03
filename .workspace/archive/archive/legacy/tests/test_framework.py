import pytest
from analysis.interfaces import Analyzer
from analysis.registry import AnalyzerRegistry
from analysis.runner import AnalysisRunner
from analysis.exceptions import PluginRegistrationError
from analysis.models import AnalysisResult, Finding, Severity

class DummyAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "dummy_analyzer"

    def analyze(self, repository) -> AnalysisResult:
        return AnalysisResult(
            analyzer_name=self.name,
            findings=[
                Finding(title="Dummy Finding", description="Dummy description", severity=Severity.INFO)
            ]
        )

class FailingAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "failing_analyzer"

    def analyze(self, repository) -> AnalysisResult:
        raise ValueError("Analyzer intentionally failed")

def test_registry_registration():
    registry = AnalyzerRegistry()
    registry.register(DummyAnalyzer)
    assert len(registry.get_all()) == 1
    assert registry.get_all()[0] == DummyAnalyzer

def test_registry_duplicate_registration():
    registry = AnalyzerRegistry()
    registry.register(DummyAnalyzer)
    with pytest.raises(PluginRegistrationError):
        registry.register(DummyAnalyzer)

def test_registry_unregistration():
    registry = AnalyzerRegistry()
    registry.register(DummyAnalyzer)
    registry.unregister("dummy_analyzer")
    assert len(registry.get_all()) == 0

def test_registry_unregister_not_found():
    registry = AnalyzerRegistry()
    with pytest.raises(PluginRegistrationError):
        registry.unregister("non_existent")

def test_runner_sequential_execution_and_aggregation():
    registry = AnalyzerRegistry()
    registry.register(DummyAnalyzer)
    
    runner = AnalysisRunner(registry)
    # Using None as mock repository
    report = runner.run(None)
    
    assert len(report.results) == 1
    assert report.results[0].analyzer_name == "dummy_analyzer"
    assert len(report.overall_findings) == 1
    assert report.overall_findings[0].title == "Dummy Finding"
    assert report.execution_summary["successful"] == 1
    assert report.execution_summary["failed"] == 0

def test_runner_fault_tolerance():
    registry = AnalyzerRegistry()
    registry.register(FailingAnalyzer)
    registry.register(DummyAnalyzer)
    
    runner = AnalysisRunner(registry)
    report = runner.run(None)
    
    # Execution should continue despite FailingAnalyzer failing
    assert len(report.results) == 1
    assert report.results[0].analyzer_name == "dummy_analyzer"
    assert report.execution_summary["successful"] == 1
    assert report.execution_summary["failed"] == 1
    assert "failing_analyzer" in report.execution_summary["errors"]
