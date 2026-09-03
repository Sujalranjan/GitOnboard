from typing import Any, Dict, List
from analysis.interfaces import Analyzer
from analysis.models.result import AnalysisResult
from analysis.models.finding import Finding
from analysis.models.severity import Severity
from analysis.models.health import RepositoryHealth, CategoryScore
from analysis.models.layer import ArchitecturalLayer

class HealthAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "health_analyzer"

    def analyze(self, repository: Any) -> AnalysisResult:
        analyses = getattr(repository, "analyses", None)
        
        metrics = getattr(analyses, "metrics", None) or {}
        cycles = getattr(analyses, "cycles", None) or []
        architecture = getattr(analyses, "architecture", None) or {}
        
        # In a real pipeline, the runner aggregates findings, but here we can check the repository for them if they were stored,
        # or we assume we are analyzing health based on the raw metrics and architectures stored in RIM.
        # Wait, the framework's runner aggregates findings across ALL analyzers at the very end.
        # How does HealthAnalyzer get findings from DeadCodeAnalyzer or LayerAnalyzer?
        # The prompt says: "Inputs: Repository metrics, Findings, Dependency graph, Layers, Cycles, Smells".
        # If the framework doesn't pass aggregated findings to analyzers, we must re-evaluate some metrics or assume they are passed via repository.analyses.findings.
        # Let's check if there are findings stored.
        all_findings = getattr(analyses, "findings", None) or []
        
        # 1. Testing (Weight 0.20)
        test_cov = 0.0
        if isinstance(metrics, dict):
            test_cov = metrics.get("test_coverage_approx_percent", 0.0)
        elif hasattr(metrics, "custom_metrics"):
            test_cov = metrics.custom_metrics.get("test_coverage_approx_percent", 0.0)
            
        test_score = test_cov
        test_expl = f"Base score derived from test coverage ({test_cov:.1f}%)."
        if test_score < 10.0:
            test_expl += " Dangerously low testing levels."

        # 2. Documentation (Weight 0.15)
        doc_cov = 0.0
        if isinstance(metrics, dict):
            doc_cov = metrics.get("documentation_coverage_percent", 0.0)
        elif hasattr(metrics, "custom_metrics"):
            doc_cov = metrics.custom_metrics.get("documentation_coverage_percent", 0.0)
            
        doc_score = doc_cov
        doc_expl = f"Base score derived from documentation coverage ({doc_cov:.1f}%)."

        # 3. Complexity (Weight 0.20)
        comp_score = 100.0
        comp_expl = "Started at 100."
        
        avg_funcs = 0.0
        if isinstance(metrics, dict):
            avg_funcs = metrics.get("average_functions_per_module", 0.0)
        elif hasattr(metrics, "custom_metrics"):
            avg_funcs = metrics.custom_metrics.get("average_functions_per_module", 0.0)
            
        if avg_funcs > 10:
            penalty = min(30.0, (avg_funcs - 10) * 2)
            comp_score -= penalty
            comp_expl += f" Deducted {penalty:.1f} due to high average functions per module ({avg_funcs:.1f})."
            
        largest_files = []
        if isinstance(metrics, dict):
            largest_files = metrics.get("largest_files", [])
        elif hasattr(metrics, "custom_metrics"):
            largest_files = metrics.custom_metrics.get("largest_files", [])
            
        huge_files = [f for f in largest_files if f.get("size", 0) > 20000] # e.g. > 20KB
        if huge_files:
            comp_score -= len(huge_files) * 5
            comp_expl += f" Deducted {len(huge_files)*5} due to extremely large files."
            
        comp_score = max(0.0, comp_score)

        # 4. Architecture (Weight 0.25)
        arch_score = 100.0
        arch_expl = "Started at 100."
        
        cycle_penalty = 0
        for c in cycles:
            sev = getattr(c, "severity", Severity.WARNING)
            if sev == Severity.CRITICAL:
                cycle_penalty += 20
            elif sev == Severity.ERROR:
                cycle_penalty += 10
            else:
                cycle_penalty += 5
                
        if cycle_penalty > 0:
            arch_score -= cycle_penalty
            arch_expl += f" Deducted {cycle_penalty} due to {len(cycles)} architectural cycles."
            
        unknown_layers = sum(1 for l in architecture.values() if l == ArchitecturalLayer.UNKNOWN)
        if unknown_layers > 0:
            unk_penalty = min(20.0, unknown_layers * 2.0)
            arch_score -= unk_penalty
            arch_expl += f" Deducted {unk_penalty:.1f} due to {unknown_layers} unclassified modules."
            
        arch_score = max(0.0, arch_score)

        # 5. Maintainability (Weight 0.20)
        maint_score = 100.0
        maint_expl = "Started at 100."
        
        if all_findings:
            finding_penalty = min(50.0, len(all_findings) * 2.0)
            maint_score -= finding_penalty
            maint_expl += f" Deducted {finding_penalty:.1f} due to {len(all_findings)} existing findings."
            
        maint_score = max(0.0, maint_score)

        # Overall Score
        overall = (test_score * 0.20) + (doc_score * 0.15) + (comp_score * 0.20) + (arch_score * 0.25) + (maint_score * 0.20)
        
        if overall >= 90:
            status = "Excellent"
        elif overall >= 75:
            status = "Good"
        elif overall >= 60:
            status = "Fair"
        else:
            status = "Needs Work"

        health = RepositoryHealth(
            health_score=round(overall, 2),
            status=status,
            issues_count=len(cycles) + len(all_findings),
            categories={
                "Testing": CategoryScore(round(test_score, 2), test_expl, 0.20),
                "Documentation": CategoryScore(round(doc_score, 2), doc_expl, 0.15),
                "Complexity": CategoryScore(round(comp_score, 2), comp_expl, 0.20),
                "Architecture": CategoryScore(round(arch_score, 2), arch_expl, 0.25),
                "Maintainability": CategoryScore(round(maint_score, 2), maint_expl, 0.20),
            }
        )

        if analyses:
            analyses.health = health
            
        rep_status = getattr(repository, "analysis_status", None)
        if rep_status:
            rep_status.health = True

        return AnalysisResult(
            analyzer_name=self.name,
            findings=[],
            metadata={"health": health}
        )
