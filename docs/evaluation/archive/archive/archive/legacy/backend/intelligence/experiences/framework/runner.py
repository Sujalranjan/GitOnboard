import os
from ...orchestrator.intent.analyzer import IntentAnalyzer
from ...orchestrator.retrieval.engine import RetrievalEngine
from ...orchestrator.providers.base import AIProvider
from .registry import ExperienceRegistry
from .experience import ExperienceRequest, ExperienceResponse

class ExperienceRunner:
    """
    Orchestrates the execution of a declarative AI Experience.
    """
    def __init__(self, 
                 registry: ExperienceRegistry,
                 retrieval_engine: RetrievalEngine,
                 ai_provider: AIProvider,
                 template_dir: str):
        self.registry = registry
        self.retrieval_engine = retrieval_engine
        self.ai_provider = ai_provider
        self.analyzer = IntentAnalyzer()
        self.template_dir = template_dir
        
    def execute(self, request: ExperienceRequest) -> ExperienceResponse:
        # 1. Analyze Intent
        intent = self.analyzer.analyze(request.query)
        
        # 2. Find matching experience
        if request.experience_id:
            experience = self.registry.get(request.experience_id)
        else:
            experience = self.registry.find_by_intent(intent.type.value)
            
        # 3. Build Knowledge Pack
        pack = self.retrieval_engine.build_knowledge_pack(intent)
        
        # 4. Filter Knowledge Pack based on requirements
        # (For MVP, we skip deep filtering, but the architecture allows it)
        
        # 5. Build prompt
        # We use a simple string template engine for the MVP
        template_path = os.path.join(self.template_dir, experience.prompt_template)
        with open(template_path, 'r') as f:
            template_str = f.read()
            
        # Very basic templating substitution for MVP
        prompt = template_str.replace("{{ query }}", request.query)
        prompt = prompt.replace("{{ intent }}", pack.intent)
        prompt = prompt.replace("{{ features }}", ", ".join(f.name for f in pack.features))
        
        # 6. Execute AI
        response = self.ai_provider.complete(prompt)
        
        return ExperienceResponse(
            answer=response.answer,
            evidence_links=response.evidence_links,
            confidence=response.confidence
        )
