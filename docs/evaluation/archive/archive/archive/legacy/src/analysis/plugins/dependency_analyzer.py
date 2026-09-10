from typing import Any, Dict, List
from analysis.interfaces import Analyzer
from analysis.models.result import AnalysisResult
from analysis.models.dependency import DependencyType, DependencyEdge, DependencyGraph
from analysis.models.layer import ArchitecturalLayer
from analysis.models.finding import Finding
from analysis.models.severity import Severity

class DependencyAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "dependency_analyzer"

    def analyze(self, repository: Any) -> AnalysisResult:
        relationships = getattr(repository, "relationships", None)
        entities = getattr(repository, "entities", None)
        analyses = getattr(repository, "analyses", None)
        
        if not relationships or not entities:
            return AnalysisResult(
                analyzer_name=self.name,
                findings=[Finding(
                    title="Missing Data",
                    description="The repository model does not contain relationships or entities.",
                    severity=Severity.ERROR
                )]
            )
            
        architecture = getattr(analyses, "architecture", None) or {}
        graph = DependencyGraph(edges=[])
        
        # 1. IMPORT
        # file_id -> file_id or module_id
        imports = getattr(relationships, "imports", None) or {}
        for src, dests in imports.items():
            for dest in dests:
                graph.edges.append(DependencyEdge(
                    source=src,
                    destination=dest,
                    type=DependencyType.IMPORT,
                    evidence="Explicit import relationship",
                    confidence=1.0
                ))
                
        # Also process entity-level imports
        entity_imports = getattr(entities, "imports", None) or {}
        for imp in entity_imports.values():
            src_file = getattr(imp, "file_id", "")
            mod_name = getattr(imp, "module_name", "")
            if src_file and mod_name:
                graph.edges.append(DependencyEdge(
                    source=src_file,
                    destination=mod_name,
                    type=DependencyType.IMPORT,
                    evidence=f"Imports {mod_name}",
                    confidence=1.0
                ))
                
                # Deduce EVENT, DATABASE, CONFIG from external module imports
                mod_lower = mod_name.lower()
                if any(x in mod_lower for x in ["kafka", "rabbitmq", "celery", "eventbus"]):
                    graph.edges.append(DependencyEdge(
                        source=src_file,
                        destination=mod_name,
                        type=DependencyType.EVENT,
                        evidence="Message broker/Event bus import",
                        confidence=0.8
                    ))
                elif any(x in mod_lower for x in ["sqlalchemy", "pymongo", "databases", "asyncpg"]):
                    graph.edges.append(DependencyEdge(
                        source=src_file,
                        destination=mod_name,
                        type=DependencyType.DATABASE,
                        evidence="Database driver ORM import",
                        confidence=0.9
                    ))
                elif "pydantic_settings" in mod_lower or "dotenv" in mod_lower:
                    graph.edges.append(DependencyEdge(
                        source=src_file,
                        destination=mod_name,
                        type=DependencyType.CONFIG,
                        evidence="Configuration library import",
                        confidence=0.9
                    ))

        # 2. CALL
        calls = getattr(relationships, "calls", None) or {}
        functions = getattr(entities, "functions", None) or {}
        methods = getattr(entities, "methods", None) or {}
        
        # Helper to get module for an entity
        def get_module(entity_id: str) -> str:
            if entity_id in functions:
                return getattr(functions[entity_id], "module_id", "")
            if entity_id in methods:
                return getattr(methods[entity_id], "module_id", "")
            return ""
            
        for src_fn, dest_fns in calls.items():
            src_mod = get_module(src_fn)
            for dest_fn in dest_fns:
                dest_mod = get_module(dest_fn)
                
                graph.edges.append(DependencyEdge(
                    source=src_fn,
                    destination=dest_fn,
                    type=DependencyType.CALL,
                    evidence="Explicit function call",
                    confidence=1.0
                ))
                
                # Check cross-module architectural calls
                if src_mod and dest_mod and src_mod != dest_mod:
                    dest_layer = architecture.get(dest_mod)
                    if dest_layer == ArchitecturalLayer.REPOSITORY:
                        graph.edges.append(DependencyEdge(
                            source=src_mod,
                            destination=dest_mod,
                            type=DependencyType.DATABASE,
                            evidence="Call to Repository layer",
                            confidence=0.85
                        ))
                    elif dest_layer == ArchitecturalLayer.CONFIG:
                        graph.edges.append(DependencyEdge(
                            source=src_mod,
                            destination=dest_mod,
                            type=DependencyType.CONFIG,
                            evidence="Call to Config layer",
                            confidence=0.85
                        ))

        # 3. API
        # Any module classified as CONTROLLER implies an API dependency externally
        for mod_id, layer in architecture.items():
            if layer == ArchitecturalLayer.CONTROLLER:
                graph.edges.append(DependencyEdge(
                    source=mod_id,
                    destination="EXTERNAL_CLIENT",
                    type=DependencyType.API,
                    evidence="Controller layer acts as API boundary",
                    confidence=0.7
                ))

        # 4. INHERITANCE and DECORATOR (Heuristics on depends_on)
        depends_on = getattr(relationships, "depends_on", None) or {}
        classes = getattr(entities, "classes", None) or {}
        
        for src_ent, dest_ents in depends_on.items():
            for dest_ent in dest_ents:
                if src_ent in classes and dest_ent in classes:
                    # Class depends on Class -> likely inheritance or composition
                    dest_name = getattr(classes[dest_ent], "name", "").lower()
                    if "base" in dest_name or "mixin" in dest_name:
                        graph.edges.append(DependencyEdge(
                            source=src_ent,
                            destination=dest_ent,
                            type=DependencyType.INHERITANCE,
                            evidence="Base/Mixin naming convention",
                            confidence=0.7
                        ))
                elif src_ent in functions and dest_ent in functions:
                    # Function depends on Function -> could be decorator
                    dest_name = getattr(functions[dest_ent], "name", "").lower()
                    if "decorator" in dest_name or "wrap" in dest_name:
                        graph.edges.append(DependencyEdge(
                            source=src_ent,
                            destination=dest_ent,
                            type=DependencyType.DECORATOR,
                            evidence="Decorator/Wrapper naming convention",
                            confidence=0.6
                        ))

        # Store graph in analyses
        if analyses:
            analyses.dependency_graph = graph
            
        status = getattr(repository, "analysis_status", None)
        if status:
            status.dependencies = True

        return AnalysisResult(
            analyzer_name=self.name,
            findings=[],
            metadata={"dependency_graph": graph}
        )
