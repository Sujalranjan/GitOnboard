"""
Engineering Agent Subsystem for GitOnBoard (Phase 1).
"""
from backend.agent.engineering_agent import (
    EngineeringAgent,
    EngineeringAgentError,
    RunNotFoundError,
)
from backend.agent.event_coordinator import AgentEventCoordinator
from backend.agent.state_machine import (
    AgentStateMachine,
    InvalidStateTransitionError,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
)
from backend.models.implementation import (
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentState,
    AgentStateTransition,
    map_agent_state_to_legacy_status,
)

__all__ = [
    "EngineeringAgent",
    "EngineeringAgentError",
    "RunNotFoundError",
    "AgentStateMachine",
    "InvalidStateTransitionError",
    "AgentEventCoordinator",
    "AgentState",
    "AgentRunStatus",
    "AgentEventType",
    "AgentRun",
    "AgentStateTransition",
    "VALID_TRANSITIONS",
    "TERMINAL_STATES",
    "map_agent_state_to_legacy_status",
]
