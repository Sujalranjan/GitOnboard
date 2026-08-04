from backend.intelligence.repository_model import RepositoryModel
from .graph_view import GraphView

class CallGraphView(GraphView):
    def __init__(self, model: RepositoryModel):
        super().__init__()
        
        # We need to build the graph and find connected components to filter out noise
        # that causes Dagre to layout thousands of nodes in a flat horizontal line.
        temp_nodes = set()
        temp_edges = {}
        temp_reverse = {}
        
        for caller, callees in model.relationships.calls.items():
            temp_nodes.add(caller)
            for callee in callees:
                temp_nodes.add(callee)
                temp_edges.setdefault(caller, []).append(callee)
                temp_reverse.setdefault(callee, []).append(caller)
                
        # Filter nodes: only keep nodes that are part of a component with size >= 3
        # or have degree >= 2 (to prevent a massive line of pairs)
        visited = set()
        components = []
        
        for node in temp_nodes:
            if node not in visited:
                comp = set()
                stack = [node]
                while stack:
                    curr = stack.pop()
                    if curr not in visited:
                        visited.add(curr)
                        comp.add(curr)
                        neighbors = temp_edges.get(curr, []) + temp_reverse.get(curr, [])
                        for n in neighbors:
                            if n not in visited:
                                stack.append(n)
                components.append(comp)
                
        valid_nodes = set()
        for comp in components:
            if len(comp) >= 3:
                valid_nodes.update(comp)
                
        # Now populate the view only with valid nodes
        for caller, callees in model.relationships.calls.items():
            if caller not in valid_nodes: continue
            self._nodes.add(caller)
            for callee in callees:
                if callee not in valid_nodes: continue
                self._nodes.add(callee)
                self._edges.setdefault(caller, []).append(callee)
                self._reverse_edges.setdefault(callee, []).append(caller)
