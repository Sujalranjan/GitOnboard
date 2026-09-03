from typing import Any, Set, Dict, List
from analysis.interfaces import Analyzer
from analysis.models.result import AnalysisResult
from analysis.models.finding import Finding
from analysis.models.severity import Severity
from analysis.models.layer import ArchitecturalLayer

class DeadCodeAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "dead_code_analyzer"

    def analyze(self, repository: Any) -> AnalysisResult:
        entities = getattr(repository, "entities", None)
        relationships = getattr(repository, "relationships", None)
        analyses = getattr(repository, "analyses", None)
        
        if not entities or not relationships:
            return AnalysisResult(
                analyzer_name=self.name,
                findings=[Finding(
                    title="Missing Data",
                    description="The repository model does not contain entities or relationships.",
                    severity=Severity.ERROR
                )]
            )
            
        functions = getattr(entities, "functions", None) or {}
        classes = getattr(entities, "classes", None) or {}
        modules = getattr(entities, "modules", None) or {}
        files = getattr(entities, "files", None) or {}
        
        calls = getattr(relationships, "calls", None) or {}
        depends_on = getattr(relationships, "depends_on", None) or {}
        imports = getattr(relationships, "imports", None) or {}
        
        architecture = getattr(analyses, "architecture", None) or {}
        
        findings = []
        
        # Build sets of active/called entities
        called_functions: Set[str] = set()
        for caller, callees in calls.items():
            called_functions.update(callees)
            
        used_classes: Set[str] = set()
        for src, dests in depends_on.items():
            used_classes.update(dests)
            
        imported_modules: Set[str] = set()
        for src, dests in imports.items():
            imported_modules.update(dests)
            
        # Detect unused functions
        for fn_id, fn in functions.items():
            name = getattr(fn, "name", "").lower()
            if fn_id in called_functions:
                continue
                
            # Check exemptions
            if name.startswith("__") and name.endswith("__"):
                continue # Magic methods
            if "test" in name or "callback" in name or "handler" in name or name == "main":
                continue
                
            mod_id = getattr(fn, "module_id", None)
            layer = architecture.get(mod_id) if mod_id else None
            if layer in (ArchitecturalLayer.CONTROLLER, ArchitecturalLayer.TEST):
                continue # API Routes or Test modules
                
            file_id = getattr(fn, "file_id", None)
            f_node = files.get(file_id) if file_id else None
            path = getattr(f_node, "path", "")
            if "main.py" in path or "__main__.py" in path or "app.py" in path or "run.py" in path:
                continue # Entry points
                
            findings.append(Finding(
                title=f"Unused Function: {getattr(fn, 'name', fn_id)}",
                description=f"Function '{getattr(fn, 'name', fn_id)}' is never called in the call graph and is not a recognized entry point or API route.",
                severity=Severity.WARNING,
                file_path=path
            ))
            
        # Detect unused classes
        for cls_id, cls in classes.items():
            name = getattr(cls, "name", "").lower()
            if cls_id in used_classes:
                continue
                
            if "test" in name:
                continue
                
            mod_id = getattr(cls, "module_id", None)
            layer = architecture.get(mod_id) if mod_id else None
            if layer in (ArchitecturalLayer.CONTROLLER, ArchitecturalLayer.TEST, ArchitecturalLayer.MODEL):
                # Models are often serialized/deserialized magically, exempt them
                continue
                
            file_id = getattr(cls, "file_id", None)
            f_node = files.get(file_id) if file_id else None
            path = getattr(f_node, "path", "")
            
            findings.append(Finding(
                title=f"Unused Class: {getattr(cls, 'name', cls_id)}",
                description=f"Class '{getattr(cls, 'name', cls_id)}' is never instantiated or depended upon in the repository.",
                severity=Severity.WARNING,
                file_path=path
            ))
            
        # Detect unreachable modules
        for mod_id, mod in modules.items():
            name = getattr(mod, "name", "").lower()
            if mod_id in imported_modules:
                continue
                
            # Modules are uniquely identified by file path/name. Check if file is an entry point.
            file_id = getattr(mod, "file_id", None)
            if file_id in imported_modules:
                continue
                
            f_node = files.get(file_id) if file_id else None
            path = getattr(f_node, "path", "")
            
            if "main.py" in path or "__main__.py" in path or "app.py" in path or "run.py" in path:
                continue
            if "test" in path or "test" in name:
                continue
            
            layer = architecture.get(mod_id)
            if layer in (ArchitecturalLayer.CONFIG, ArchitecturalLayer.TEST, ArchitecturalLayer.CONTROLLER):
                continue
                
            findings.append(Finding(
                title=f"Unreachable Module: {getattr(mod, 'name', mod_id)}",
                description=f"Module '{getattr(mod, 'name', mod_id)}' is never imported by any other module and is not a known entry point.",
                severity=Severity.WARNING,
                file_path=path
            ))

        return AnalysisResult(
            analyzer_name=self.name,
            findings=findings
        )
