"""
Task Orchestration Package for GitOnBoard Engineering Agent.
"""
from backend.agent.tasks.contracts import TaskExecutionContext, TaskExecutionResult
from backend.agent.tasks.executor import (
    DefaultTaskExecutor,
    EngineeringAgentTaskExecutor,
    TaskExecutor,
)
from backend.agent.tasks.orchestrator import TaskOrchestrator, TaskOrchestratorError
from backend.agent.tasks.state_machine import InvalidTaskStateTransitionError, TaskStateMachine
from backend.agent.tasks.verification import DefaultVerificationDispatcher, VerificationDispatcher

__all__ = [
    "TaskExecutionContext",
    "TaskExecutionResult",
    "TaskExecutor",
    "DefaultTaskExecutor",
    "EngineeringAgentTaskExecutor",
    "VerificationDispatcher",
    "DefaultVerificationDispatcher",
    "TaskStateMachine",
    "InvalidTaskStateTransitionError",
    "TaskOrchestrator",
    "TaskOrchestratorError",
]
