"""
RequirementAnalyzer: Extracts structured acceptance criteria from a natural language requirement.

Security: Repository content is NEVER passed to this module.
The LLM receives only the raw requirement string.
"""
from __future__ import annotations
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from backend.ai.service import LLMService
from backend.ai.schemas import LLMRequest, Message, MessageRole

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a requirements engineering assistant for a software platform.
Your task is to analyze a user's feature requirement and extract structured information.

IMPORTANT RULES:
- You only receive the raw user requirement. No repository files or code.
- Output ONLY a valid JSON object. No prose, no explanation, no markdown.
- Acceptance criteria must be deterministic and verifiable (not vague wishes).
- Number criteria as AC-01, AC-02, etc.
"""

USER_PROMPT_TEMPLATE = """Analyze this feature requirement and produce structured output:

REQUIREMENT:
{requirement}

Output JSON with this exact structure:
{{
  "title": "short title (max 10 words)",
  "goals": ["goal 1", "goal 2"],
  "acceptance_criteria": [
    {{"id": "AC-01", "description": "Specific, verifiable criterion"}},
    {{"id": "AC-02", "description": "Another criterion"}}
  ],
  "security_considerations": ["consideration 1"],
  "tests_required": ["Test that ...", "Test that ..."]
}}
"""


class AcceptanceCriterion(BaseModel):
    id: str = Field(description="e.g. AC-01")
    description: str


class AnalyzedRequirement(BaseModel):
    title: str
    goals: List[str] = Field(default_factory=list)
    acceptance_criteria: List[AcceptanceCriterion] = Field(default_factory=list)
    security_considerations: List[str] = Field(default_factory=list)
    tests_required: List[str] = Field(default_factory=list)


class RequirementAnalyzer:
    """
    Parses a natural language requirement into structured acceptance criteria.

    Note: This module intentionally does NOT receive repository context —
    it processes only the raw user requirement to prevent prompt injection.
    """

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    async def analyze(self, requirement: str) -> AnalyzedRequirement:
        """
        Analyze a raw requirement string and return structured acceptance criteria.

        Args:
            requirement: Raw natural language requirement from the user.

        Returns:
            AnalyzedRequirement with deterministic acceptance criteria.
        """
        logger.info(f"RequirementAnalyzer: Analyzing requirement ({len(requirement)} chars)")

        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
                Message(
                    role=MessageRole.USER,
                    content=USER_PROMPT_TEMPLATE.format(requirement=requirement),
                ),
            ],
            temperature=0.1,  # Low temperature for deterministic structured output
            max_tokens=2048,
        )

        result = await self.llm.generate_structured(request, AnalyzedRequirement)
        logger.info(
            f"RequirementAnalyzer: Extracted {len(result.acceptance_criteria)} criteria, "
            f"{len(result.tests_required)} required tests."
        )
        return result
