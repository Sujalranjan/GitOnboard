from typing import Dict, Any, List
from analysis.interfaces import Analyzer
from analysis.models.result import AnalysisResult
from analysis.models.layer import ArchitecturalLayer, ModuleLayer
from analysis.models.finding import Finding
from analysis.models.severity import Severity

class LayerHeuristics:
    @staticmethod
    def evaluate(module, file_node, imports, functions, classes) -> ArchitecturalLayer:
        name = module.name.lower()
        path = file_node.path.lower() if file_node else ""
        
        # Test
        if "tests/" in path or "/test" in path or name.startswith("test_") or name.endswith("_test"):
            return ArchitecturalLayer.TEST
            
        # Config
        if "config" in name or "settings" in name or "setup" in name:
            return ArchitecturalLayer.CONFIG
            
        # Controller
        if any(kw in name for kw in ["controller", "route", "view", "api"]):
            return ArchitecturalLayer.CONTROLLER
        if any(imp in imports for imp in ["fastapi", "flask", "django"]):
            return ArchitecturalLayer.CONTROLLER
            
        # Repository
        if any(kw in name for kw in ["repository", "crud", "database", "db", "dal"]):
            return ArchitecturalLayer.REPOSITORY
        if any(imp in imports for imp in ["sqlalchemy", "pymongo", "asyncpg", "databases"]):
            return ArchitecturalLayer.REPOSITORY
            
        # Model
        if any(kw in name for kw in ["model", "schema", "entity", "dto", "type"]):
            return ArchitecturalLayer.MODEL
        if any(imp in imports for imp in ["pydantic", "dataclasses"]):
            return ArchitecturalLayer.MODEL
            
        # Service
        if any(kw in name for kw in ["service", "manager", "handler", "usecase", "logic"]):
            return ArchitecturalLayer.SERVICE
            
        # Utility
        if any(kw in name for kw in ["util", "helper", "common", "core", "shared", "constant"]):
            return ArchitecturalLayer.UTILITY
            
        return ArchitecturalLayer.UNKNOWN


class LayerAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "layer_analyzer"

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
            
        modules = getattr(entities, "modules", None) or {}
        files = getattr(entities, "files", None) or {}
        all_imports = getattr(entities, "imports", None) or {}
        all_functions = getattr(entities, "functions", None) or {}
        all_classes = getattr(entities, "classes", None) or {}
        
        # Precompute mappings for fast lookup
        # file_id -> list of imported module names
        file_imports: Dict[str, List[str]] = {}
        for imp in all_imports.values():
            file_id = getattr(imp, "file_id", "")
            mod_name = getattr(imp, "module_name", "").lower()
            file_imports.setdefault(file_id, []).append(mod_name)
            
        # module_id -> count of functions and classes
        module_funcs: Dict[str, int] = {}
        for fn in all_functions.values():
            mod_id = getattr(fn, "module_id", None)
            if mod_id:
                module_funcs[mod_id] = module_funcs.get(mod_id, 0) + 1
                
        module_classes: Dict[str, int] = {}
        for cls in all_classes.values():
            mod_id = getattr(cls, "module_id", None)
            if mod_id:
                module_classes[mod_id] = module_classes.get(mod_id, 0) + 1
        
        findings = []
        module_layers: Dict[str, ArchitecturalLayer] = {}
        layer_objects: List[ModuleLayer] = []
        
        for mod_id, module in modules.items():
            file_id = getattr(module, "file_id", None)
            file_node = files.get(file_id) if file_id else None
            imports = file_imports.get(file_id, []) if file_id else []
            funcs = module_funcs.get(mod_id, 0)
            classes = module_classes.get(mod_id, 0)
            
            layer = LayerHeuristics.evaluate(module, file_node, imports, funcs, classes)
            module_layers[mod_id] = layer
            
            reason = f"Classified by heuristics"
            if layer == ArchitecturalLayer.UNKNOWN:
                reason = "No rules matched this module"
                findings.append(Finding(
                    title=f"Unknown Architectural Layer for {getattr(module, 'name', mod_id)}",
                    description=f"Module {getattr(module, 'name', mod_id)} could not be classified into any architectural layer.",
                    severity=Severity.INFO,
                    file_path=getattr(file_node, "path", None) if file_node else None
                ))
                
            ml = ModuleLayer(
                module_id=mod_id,
                module_name=getattr(module, "name", mod_id),
                layer=layer,
                reason=reason
            )
            layer_objects.append(ml)
            
        # Store in RIM
        analyses = getattr(repository, "analyses", None)
        if analyses:
            analyses.architecture = {ml.module_id: ml.layer for ml in layer_objects}
            
        status = getattr(repository, "analysis_status", None)
        if status:
            status.architecture = True
            
        return AnalysisResult(
            analyzer_name=self.name,
            findings=findings,
            metadata={"layers": layer_objects}
        )
