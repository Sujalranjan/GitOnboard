"""
Priority 2 Diagnostic: Verify LLM Provider Capability

Tests the actual LLM provider being used and its JSON tool-calling support.
"""
import os
import pytest
import asyncio


class TestLLMProviderCapability:
    """Diagnose LLM provider and tool-calling support."""

    def test_deployment_type(self):
        """Check what DEPLOYMENT_TYPE is active."""
        deployment_type = os.environ.get("DEPLOYMENT_TYPE", "LOCAL")
        print(f"\nDEPLOYMENT_TYPE: {deployment_type}")

        if deployment_type == "TEST":
            pytest.skip("Test environment uses mocked LLM (DeterministicTestProvider)")

    def test_which_provider_loaded(self):
        """Check which LLM provider is actually loaded."""
        from backend.ai.service import get_llm_service

        service = get_llm_service()
        print(f"\nLLMService providers: {[p.provider_name for p in service.providers]}")

        for provider in service.providers:
            print(f"  - {provider.provider_name}")
            if hasattr(provider, "__class__"):
                print(f"    class: {provider.__class__.__name__}")

    @pytest.mark.asyncio
    async def test_llm_response_format(self):
        """Test what format the LLM returns."""
        from backend.ai.schemas import LLMRequest, Message, MessageRole
        from backend.ai.service import get_llm_service
        import json

        service = get_llm_service()

        request = LLMRequest(
            messages=[
                Message(
                    role=MessageRole.USER,
                    content="Respond with valid JSON: {\"tool\": \"test\", \"parameters\": {}}",
                )
            ],
            temperature=0.1,
            max_tokens=256,
        )

        response = await service.generate(request)
        print(f"\nLLM Response Type: {type(response)}")
        print(f"Response Content: {response.content[:200]}")

        # Try to parse as JSON
        try:
            parsed = json.loads(response.content)
            print(f"✅ Response is valid JSON")
            print(f"   Keys: {list(parsed.keys())}")
        except json.JSONDecodeError as e:
            print(f"❌ Response is NOT valid JSON")
            print(f"   Error: {e}")
            print(f"   Looks like: {response.content[:100]}")


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
