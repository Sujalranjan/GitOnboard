from .base import AIProvider, AIResponse

class MockAIProvider(AIProvider):
    def complete(self, prompt: str) -> AIResponse:
        # Just mock a response
        return AIResponse(
            answer="Based on the context, this feature does exactly what the user asked.",
            evidence_links=["urn:route:1"],
            confidence=0.99
        )
