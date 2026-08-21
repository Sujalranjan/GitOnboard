"""
Engineering Agent Subsystem for GitOnBoard (Phase 1, Phase 2 & Phase 3).
"""
from backend.agent.context import (
    CompletenessStatus,
    ContextAssembler,
    ContextAssemblyRequest,
    ContextBudget,
    ContextEvidence,
    RepositoryContext,
    RepositoryUnderstandingContract,
)
from backend.agent.planning import (
    Plan,
    PlanStatus,
    PlanTask,
    PlanTaskStatus,
    PlanValidationResult,
    PlanValidator,
    PlanningOrchestrator,
)
from backend.agent.tasks import (
    DefaultTaskExecutor,
    DefaultVerificationDispatcher,
    InvalidTaskStateTransitionError,
    TaskExecutionContext,
    TaskExecutionResult,
    TaskExecutor,
    TaskOrchestrator,
    TaskOrchestratorError,
    TaskStateMachine,
    VerificationDispatcher,
)
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
from backend.agent.tools import (
    AgentToolContext,
    AgentToolRegistry,
    PolicyAction,
    PolicyDecision,
    ToolDefinition,
    ToolError,
    ToolErrorCode,
    ToolPolicy,
    ToolResult,
    create_default_tool_registry,
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
    "AgentToolRegistry",
    "ToolPolicy",
    "PolicyAction",
    "PolicyDecision",
    "ToolDefinition",
    "ToolResult",
    "ToolError",
    "ToolErrorCode",
    "AgentToolContext",
    "create_default_tool_registry",
    "ContextAssembler",
    "RepositoryContext",
    "ContextEvidence",
    "ContextBudget",
    "ContextAssemblyRequest",
    "RepositoryUnderstandingContract",
    "CompletenessStatus",
    "Plan",
    "PlanTask",
    "PlanStatus",
    "PlanTaskStatus",
    "PlanValidationResult",
    "PlanValidator",
    "PlanningOrchestrator",
    "TaskOrchestrator",
    "TaskOrchestratorError",
    "TaskStateMachine",
    "InvalidTaskStateTransitionError",
    "TaskExecutor",
    "DefaultTaskExecutor",
    "VerificationDispatcher",
    "DefaultVerificationDispatcher",
    "TaskExecutionContext",
    "TaskExecutionResult",
]



