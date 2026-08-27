"""Deterministic Test Provider for offline and automated test execution."""
from __future__ import annotations
import logging
from typing import Type, TypeVar

from backend.ai.interfaces import LLMProvider
from backend.ai.schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")


class DeterministicTestProvider(LLMProvider):
    """
    Fast, deterministic LLM provider used in automated test environments
    to eliminate external Ollama/network dependencies and timeout delays.
    """
    provider_name = "test_mock"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        import json
        last_msg = (request.messages[-1].content if request.messages else "").lower()
        if "plan steps" in last_msg or "step objects" in last_msg:
            # Determine repository archetype and target files from prompt
            if "pls_cli" in last_msg or "pls-cli" in last_msg:
                steps_data = [
                    {"step_number": 1, "title": "Implement core changes in pls_cli", "description": "Modify pls_cli/please.py to support the requirement.", "target_files": ["pls_cli/please.py"], "component_type": "EXISTING"},
                    {"step_number": 2, "title": "Verify with automated tests", "description": "No existing test suite found for tests/test_pls_cli.py. Implement tests covering pls_cli/please.py modifications. Propose new module tests/test_pls_cli.py.", "target_files": ["tests/test_pls_cli.py"], "component_type": "NEW"}
                ]
            elif "uploadarea" in last_msg or "gitonboard" in last_msg or ".tsx" in last_msg or "typescript" in last_msg:
                steps_data = [
                    {"step_number": 1, "title": "Implement frontend components", "description": "Update src/components/UploadArea.tsx with payment interface.", "target_files": ["src/components/UploadArea.tsx"], "component_type": "EXISTING"},
                    {"step_number": 2, "title": "Verify with component test suite", "description": "Add tests covering UploadArea.", "target_files": ["src/components/UploadArea.test.tsx"], "component_type": "NEW"}
                ]
            else:
                steps_data = [
                    {"step_number": 1, "title": "Implement core changes", "description": "Implement the requested capability.", "target_files": ["backend/auth/service.py"], "component_type": "EXISTING"},
                    {"step_number": 2, "title": "Verify with tests", "description": "No existing test suite found for tests/test_auth.py. Propose new module tests/test_auth.py.", "target_files": ["tests/test_auth.py"], "component_type": "NEW"}
                ]
            return LLMResponse(
                content=json.dumps(steps_data),
                provider=self.provider_name,
                model="mock-test-model",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            )
        return LLMResponse(
            content=f"Deterministic test response for: {request.messages[-1].content[:60] if request.messages else ''}",
            provider=self.provider_name,
            model="mock-test-model",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        schema_name = getattr(schema, "__name__", str(schema))
        last_msg = (request.messages[-1].content if request.messages else "").lower()

        if schema_name == "LLMIntentResponse":
            if any(w in last_msg for w in ["hello", "hi", "hey", "thanks", "who are you"]):
                return schema(intent="chat", confidence=0.98, reason="Test mock chat intent")
            if any(w in last_msg for w in ["what would it take", "how would", "plan", "design", "estimate"]):
                return schema(intent="plan", confidence=0.95, reason="Test mock plan intent")
            if any(w in last_msg for w in ["tree", "find", "where", "list", "symbol"]):
                return schema(intent="explore", confidence=0.95, reason="Test mock explore intent")
            if any(w in last_msg for w in ["explain", "how does", "what does", "what are", "describe", "workflow"]):
                return schema(intent="explain", confidence=0.95, reason="Test mock explain intent")
            if any(w in last_msg for w in ["make it better", "make auth better", "clarify", "fix it", "do the thing"]):
                return schema(intent="clarify", confidence=0.50, reason="Test mock clarify intent")
            if any(w in last_msg for w in ["implement", "add", "fix", "refactor", "build", "create"]):
                return schema(intent="implement", confidence=0.95, reason="Test mock implement intent")
            return schema(intent="plan", confidence=0.90, reason="Test mock plan intent")

        if schema_name == "AnalyzedRequirement":
            from backend.planning.requirements import AcceptanceCriterion
            return schema(
                title="Mock Analyzed Requirement",
                goals=["Implement mock capability"],
                acceptance_criteria=[AcceptanceCriterion(id="AC-01", description="Verify mock behavior")],
                security_considerations=[],
                tests_required=["Test mock behavior"],
            )

        if schema_name == "ContractOutput":
            from backend.planning.contract import AffectedComponent
            if "pls_cli" in last_msg or "pls-cli" in last_msg:
                comp_file = "pls_cli/please.py"
                comp_sym = "run_command"
            elif "uploadarea" in last_msg or "gitonboard" in last_msg or ".tsx" in last_msg or "typescript" in last_msg:
                comp_file = "src/components/UploadArea.tsx"
                comp_sym = "UploadArea"
            else:
                comp_file = "backend/auth/service.py"
                comp_sym = "AuthService"

            return schema(
                affected_components=[
                    AffectedComponent(file=comp_file, symbol=comp_sym, component_type="EXISTING", evidence_ids=["EVID-001"])
                ],
                tests_required=["Test target capability flow"],
                security_considerations=[],
            )

        raise NonRetriableError(f"DeterministicTestProvider: schema '{schema_name}' triggering deterministic fallback.")
