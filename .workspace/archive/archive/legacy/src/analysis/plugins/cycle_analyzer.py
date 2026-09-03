import os
from typing import Any, Dict, List, Set, Tuple
from analysis.interfaces import Analyzer
from analysis.models.result import AnalysisResult
from analysis.models.dependency import DependencyGraph
from analysis.models.cycle import Cycle
from analysis.models.finding import Finding
from analysis.models.severity import Severity

class TarjanSCC:
    def __init__(self, graph: Dict[str, List[str]]):
        self.graph = graph
        self.index = 0
        self.indices = {}
        self.lowlink = {}
        self.on_stack = set()
        self.stack = []
        self.sccs = []

    def find_sccs(self) -> List[List[str]]:
        for v in self.graph:
            if v not in self.indices:
                self.strongconnect(v)
        return self.sccs

    def strongconnect(self, v: str):
        self.indices[v] = self.index
        self.lowlink[v] = self.index
        self.index += 1
        self.stack.append(v)
        self.on_stack.add(v)

        for w in self.graph.get(v, []):
            if w not in self.indices:
                self.strongconnect(w)
                self.lowlink[v] = min(self.lowlink[v], self.lowlink[w])
            elif w in self.on_stack:
                self.lowlink[v] = min(self.lowlink[v], self.indices[w])

        if self.lowlink[v] == self.indices[v]:
            scc = []
            while True:
                w = self.stack.pop()
                self.on_stack.remove(w)
                scc.append(w)
                if w == v:
                    break
            self.sccs.append(scc)


class CycleAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "cycle_analyzer"

    def _get_package(self, path: str) -> str:
        if not path:
            return ""
        pkg = os.path.dirname(path)
        return pkg if pkg else "."

    def analyze(self, repository: Any) -> AnalysisResult:
        analyses = getattr(repository, "analyses", None)
        graph_obj = getattr(analyses, "dependency_graph", None) if analyses else None
        
        if not graph_obj or not hasattr(graph_obj, "edges"):
            return AnalysisResult(
                analyzer_name=self.name,
                findings=[Finding(
                    title="Missing Dependency Graph",
                    description="The repository model does not contain a dependency graph.",
                    severity=Severity.ERROR
                )]
            )
            
        edges = graph_obj.edges
        entities = getattr(repository, "entities", None)
        
        # Build graphs
        module_graph: Dict[str, List[str]] = {}
        package_graph: Dict[str, List[str]] = {}
        
        for e in edges:
            src = e.source
            dst = e.destination
            
            # Module graph
            if src not in module_graph:
                module_graph[src] = []
            if dst not in module_graph[src]:
                module_graph[src].append(dst)
            if dst not in module_graph:
                module_graph[dst] = []
                
            # Try to resolve to packages if possible (assuming src/dst are files or modules)
            # This is a best effort heuristic
            src_pkg = None
            dst_pkg = None
            
            if entities:
                files = getattr(entities, "files", {})
                if src in files: src_pkg = self._get_package(getattr(files[src], "path", ""))
                if dst in files: dst_pkg = self._get_package(getattr(files[dst], "path", ""))
                
            if src_pkg and dst_pkg and src_pkg != dst_pkg:
                if src_pkg not in package_graph:
                    package_graph[src_pkg] = []
                if dst_pkg not in package_graph[src_pkg]:
                    package_graph[src_pkg].append(dst_pkg)
                if dst_pkg not in package_graph:
                    package_graph[dst_pkg] = []
                    
        findings = []
        cycles = []
        
        def process_sccs(sccs, cycle_type):
            for scc in sccs:
                if len(scc) > 1:
                    size = len(scc)
                    if size > 5:
                        severity = Severity.CRITICAL
                    elif size > 2:
                        severity = Severity.ERROR
                    else:
                        severity = Severity.WARNING
                        
                    members_str = ", ".join(scc)
                    desc = f"Circular dependency detected between {size} {cycle_type}s: {members_str}."
                    
                    cycles.append(Cycle(
                        members=scc,
                        size=size,
                        severity=severity,
                        description=desc
                    ))
                    
                    findings.append(Finding(
                        title=f"{cycle_type.capitalize()} Cycle Detected",
                        description=desc,
                        severity=severity
                    ))

        # Tarjan on Module Graph
        mod_sccs = TarjanSCC(module_graph).find_sccs()
        process_sccs(mod_sccs, "module")
        
        # Tarjan on Package Graph
        pkg_sccs = TarjanSCC(package_graph).find_sccs()
        process_sccs(pkg_sccs, "package")
        
        # Store in RIM
        if analyses:
            analyses.cycles = cycles
            
        status = getattr(repository, "analysis_status", None)
        if status:
            status.cycles = True

        return AnalysisResult(
            analyzer_name=self.name,
            findings=findings,
            metadata={"cycles": cycles}
        )
