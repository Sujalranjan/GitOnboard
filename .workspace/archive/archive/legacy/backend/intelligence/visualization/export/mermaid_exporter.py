from .base import Exporter
from ..model.visual_model import VisualGraph

class MermaidExporter(Exporter):
    def export(self, graph: VisualGraph) -> str:
        lines = ["graph TD"]
        
        for node in graph.nodes:
            # Mermaid format: id["label"]
            safe_label = node.label.replace('"', "'")
            lines.append(f'    {node.id}["{safe_label}"]')
            if node.type == "feature":
                lines.append(f'    style {node.id} fill:#f9f,stroke:#333,stroke-width:2px')
                
        for edge in graph.edges:
            safe_label = edge.label.replace('"', "'") if edge.label else ""
            if edge.style == "dashed":
                if safe_label:
                    lines.append(f'    {edge.source} -. "{safe_label}" .-> {edge.target}')
                else:
                    lines.append(f'    {edge.source} -.-> {edge.target}')
            elif edge.style == "bold_red":
                if safe_label:
                    lines.append(f'    {edge.source} == "{safe_label}" ==> {edge.target}')
                else:
                    lines.append(f'    {edge.source} ===> {edge.target}')
                lines.append(f'    linkStyle {len(lines)-3} stroke:red,stroke-width:3px;')
            else:
                if safe_label:
                    lines.append(f'    {edge.source} -- "{safe_label}" --> {edge.target}')
                else:
                    lines.append(f'    {edge.source} --> {edge.target}')
                    
        return "\n".join(lines)
