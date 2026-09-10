from typing import Dict, Any, List
from analysis.interfaces import Analyzer
from analysis.models.result import AnalysisResult
from analysis.models.metrics import RepositoryMetrics
from analysis.models.finding import Finding
from analysis.models.severity import Severity

class MetricsAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "metrics_analyzer"

    def analyze(self, repository: Any) -> AnalysisResult:
        entities = getattr(repository, "entities", None)
        if not entities:
            return AnalysisResult(
                analyzer_name=self.name,
                findings=[Finding(
                    title="Missing Entities",
                    description="The repository model does not contain entities.",
                    severity=Severity.ERROR
                )]
            )
            
        total_files = len(getattr(entities, "files", {}))
        total_directories = len(getattr(entities, "directories", {}))
        total_modules = len(getattr(entities, "modules", {}))
        total_classes = len(getattr(entities, "classes", {}))
        total_functions = len(getattr(entities, "functions", {}))
        total_methods = len(getattr(entities, "methods", {}))
        total_imports = len(getattr(entities, "imports", {}))
        
        # Largest files
        files_dict = getattr(entities, "files", {})
        sorted_files = sorted(files_dict.values(), key=lambda f: getattr(f, "size", 0), reverse=True)
        largest_files = [{"name": getattr(f, "name", ""), "path": getattr(f, "path", ""), "size": getattr(f, "size", 0)} for f in sorted_files[:5]]
        
        # Largest modules (by number of functions + classes + methods)
        modules_dict = getattr(entities, "modules", {})
        module_sizes: Dict[str, int] = {m_id: 0 for m_id in modules_dict}
        
        for fn in getattr(entities, "functions", {}).values():
            mod_id = getattr(fn, "module_id", None)
            if mod_id in module_sizes:
                module_sizes[mod_id] += 1
        for cls in getattr(entities, "classes", {}).values():
            mod_id = getattr(cls, "module_id", None)
            if mod_id in module_sizes:
                module_sizes[mod_id] += 1
        for mth in getattr(entities, "methods", {}).values():
            mod_id = getattr(mth, "module_id", None)
            if mod_id in module_sizes:
                module_sizes[mod_id] += 1
                
        sorted_modules = sorted(module_sizes.items(), key=lambda item: item[1], reverse=True)
        largest_modules = []
        for m_id, size in sorted_modules[:5]:
            module_name = getattr(modules_dict[m_id], "name", m_id)
            largest_modules.append({"name": module_name, "entities_count": size})
            
        # Doc coverage
        doc_capable = total_functions + total_classes + total_methods
        doc_count = 0
        for fn in getattr(entities, "functions", {}).values():
            if getattr(fn, "docstring", ""): doc_count += 1
        for cls in getattr(entities, "classes", {}).values():
            if getattr(cls, "docstring", ""): doc_count += 1
        for mth in getattr(entities, "methods", {}).values():
            if getattr(mth, "docstring", ""): doc_count += 1
            
        doc_coverage = (doc_count / doc_capable * 100) if doc_capable > 0 else 0.0
        
        # Average functions per module
        avg_funcs_per_module = (total_functions / total_modules) if total_modules > 0 else 0.0
        
        # Test coverage (approx by finding test files vs total python files)
        python_files = [f for f in files_dict.values() if getattr(f, "is_python", False)]
        test_files = [f for f in python_files if "test_" in getattr(f, "name", "").lower() or "_test" in getattr(f, "name", "").lower()]
        test_coverage = (len(test_files) / len(python_files) * 100) if len(python_files) > 0 else 0.0
        
        # API Routes (approx)
        api_routes = 0
        for fn in getattr(entities, "functions", {}).values():
            name = getattr(fn, "name", "").lower()
            if "route" in name or "endpoint" in name:
                api_routes += 1
                
        # Lines of code (approximate)
        lines_of_code = 0
        analyses = getattr(repository, "analyses", None)
        if analyses and getattr(analyses, "metrics", None):
            metrics_dict = analyses.metrics
            lines_of_code = metrics_dict.get("lines_of_code", 0)
            if "api_routes" in metrics_dict:
                api_routes = metrics_dict["api_routes"]
                
        if lines_of_code == 0:
            total_size = sum(getattr(f, "size", 0) for f in files_dict.values())
            lines_of_code = total_size // 30
            
        metrics = RepositoryMetrics(
            total_files=total_files,
            total_lines=lines_of_code,
            complexity=0.0,
            custom_metrics={
                "total_directories": total_directories,
                "total_modules": total_modules,
                "total_classes": total_classes,
                "total_functions": total_functions,
                "total_methods": total_methods,
                "total_imports": total_imports,
                "total_api_routes": api_routes,
                "comment_lines": 0,
                "documentation_coverage_percent": round(doc_coverage, 2),
                "test_coverage_approx_percent": round(test_coverage, 2),
                "average_cyclomatic_complexity": 0.0,
                "average_functions_per_module": round(avg_funcs_per_module, 2),
                "largest_files": largest_files,
                "largest_modules": largest_modules
            }
        )
        
        findings = []
        if doc_coverage < 50:
            findings.append(Finding(
                title="Low Documentation Coverage",
                description=f"Only {doc_coverage:.1f}% of code entities have docstrings.",
                severity=Severity.WARNING
            ))
            
        return AnalysisResult(
            analyzer_name=self.name,
            findings=findings,
            metrics=metrics
        )
