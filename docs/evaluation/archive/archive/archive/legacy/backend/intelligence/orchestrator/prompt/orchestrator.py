from ..knowledge.model import KnowledgePack

class PromptOrchestrator:
    """
    Consumes a KnowledgePack and formats it into a specific prompt 
    string for an LLM to consume.
    """
    def build_prompt(self, pack: KnowledgePack) -> str:
        lines = []
        lines.append(f"Intent: {pack.intent}")
        if pack.target_id:
            lines.append(f"Target: {pack.target_id}")
            
        lines.append("\n=== Features ===")
        for f in pack.features:
            lines.append(f"- {f.name}: {f.description}")
            
        lines.append("\n=== Capabilities ===")
        for c in pack.capabilities:
            lines.append(f"- {c.name}: {c.purpose}")
            
        lines.append("\n=== Representative Sources ===")
        for src in pack.representative_sources:
            lines.append(f"- {src.name} ({src.type.value}) at {src.location.repository_path}")
            
        lines.append("\nPlease answer the user's query using only the information provided above.")
        return "\n".join(lines)
