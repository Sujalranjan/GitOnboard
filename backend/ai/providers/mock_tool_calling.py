"""
Tool-Calling Mock Provider for validating Phase 2M architecture.

Simulates a multi-turn tool-calling LLM interaction:
- Call 1: Returns tool request (inspect_file)
- Call 2: Returns tool request (read_symbol)
- Call 3: Returns final natural-language answer

This provider validates the software pipeline without requiring a real LLM
that supports the JSON tool-calling protocol.
"""
from __future__ import annotations
import json
import logging
from typing import Type, TypeVar

from backend.ai.interfaces import LLMProvider
from backend.ai.schemas import LLMRequest, LLMResponse, TokenUsage, NonRetriableError

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ToolCallingMockProvider(LLMProvider):
    """
    Mock LLM provider that simulates tool-calling interaction.

    Tracks conversation state to return appropriate tool requests and final answer.
    Designed specifically for Phase 2M validation without requiring real LLM.
    """

    provider_name = "tool_calling_mock"

    def __init__(self):
        self.call_count = 0
        self.last_tool_result = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Simulate multi-turn tool-calling interaction.

        Turn 1: Return tool request for inspect_file
        Turn 2: Return tool request for read_symbol
        Turn 3+: Return final answer
        """
        self.call_count += 1

        # Extract any tool result from messages (TOOL role messages)
        tool_results = []
        for msg in request.messages:
            if msg.role.value == "tool":
                tool_results.append(msg.content)

        logger.info(
            f"[ToolCallingMock] Call #{self.call_count}, tool results: {len(tool_results)}"
        )

        # Turn 1: Request file inspection
        if self.call_count == 1:
            response_content = json.dumps(
                {
                    "thought": "I need to understand how login works. Let me start by inspecting the auth router.",
                    "tool": "inspect_file",
                    "parameters": {"file_path": "backend/routers/auth.py"},
                }
            )

            logger.info(f"[ToolCallingMock] Turn 1: Requesting inspect_file")

            return LLMResponse(
                content=response_content,
                provider=self.provider_name,
                model="mock-tool-calling-model",
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            )

        # Turn 2: Request symbol reading
        elif self.call_count == 2:
            response_content = json.dumps(
                {
                    "thought": "Good, I can see there's a login_route function. Let me read it to understand the authentication logic.",
                    "tool": "read_symbol",
                    "parameters": {
                        "file_path": "backend/routers/auth.py",
                        "symbol_name": "login_route",
                    },
                }
            )

            logger.info(f"[ToolCallingMock] Turn 2: Requesting read_symbol")

            return LLMResponse(
                content=response_content,
                provider=self.provider_name,
                model="mock-tool-calling-model",
                usage=TokenUsage(prompt_tokens=150, completion_tokens=75, total_tokens=225),
            )

        # Turn 3+: Return final answer
        else:
            answer = """
Login works through the following flow:

1. **Frontend**: User submits credentials via the login form
2. **Route Handler** (backend/routers/auth.py::login_route): Receives the login request
3. **Authentication**: The login_route function validates credentials against the database
4. **Session/Token**: After validation, a session token or JWT is generated
5. **Response**: The token is returned to the frontend for subsequent authenticated requests

The authentication system uses the backend/services/auth_service.py module which handles:
- Password validation
- User lookup
- Token generation
- Session management

This multi-layer architecture ensures security by:
- Separating route handling from business logic
- Using secure credential storage (hashed passwords)
- Generating time-limited tokens
- Validating authentication on protected endpoints
"""

            logger.info(f"[ToolCallingMock] Turn {self.call_count}: Returning final answer")

            return LLMResponse(
                content=answer,
                provider=self.provider_name,
                model="mock-tool-calling-model",
                usage=TokenUsage(prompt_tokens=200, completion_tokens=150, total_tokens=350),
            )

    async def generate_structured(self, request: LLMRequest, schema: Type[T]) -> T:
        """Not implemented for tool-calling mock."""
        raise NonRetriableError(
            f"ToolCallingMockProvider: structured generation not implemented"
        )
