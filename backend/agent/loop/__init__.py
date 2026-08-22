"""
Phase 6 Engineering Agent Loop Package.

Provides the controlled tool-calling execution loop, guardrails, model adapter,
and typed contracts for executing approved engineering tasks.
"""
from __future__ import annotations

from backend.agent.loop.contracts import (
    AgentExecutionResult,
    AgentLoopConfig,
    CompletionSignal,
    CriterionEvaluation,
    StopReason,
    ToolCall,
    ToolObservation,
)
from backend.agent.loop.guardrails import LoopGuardrails
from backend.agent.loop.loop import EngineeringAgentLoop
from backend.agent.loop.model_adapter import ModelAdapter, ModelMessage, ParsedModelOutput

__all__ = [
    "EngineeringAgentLoop",
    "AgentLoopConfig",
    "StopReason",
    "ToolCall",
    "ToolObservation",
    "CriterionEvaluation",
    "CompletionSignal",
    "AgentExecutionResult",
    "ModelAdapter",
    "ModelMessage",
    "ParsedModelOutput",
    "LoopGuardrails",
]
