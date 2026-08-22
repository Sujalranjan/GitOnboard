"""
AgentStateMachine: Enforces strict, valid lifecycle transitions for an EngineeringAgent session.

State Machine Specification (Phase 1):
  States:
    - IDLE               : Initial state prior to requirement analysis.
    - UNDERSTANDING      : Active repository inspection and requirement comprehension.
    - PLANNING           : Step-by-step plan synthesis and acceptance criteria linking.
    - AWAITING_APPROVAL  : Plan generated, awaiting user approval or automated dispatch.
    - EXECUTING          : Action/worktree execution in progress.
    - VERIFYING          : Multi-vector verification and assertions running.
    - COMPLETED          : Terminal state representing successful completion.
    - FAILED             : Terminal state representing an unrecoverable failure or defect.
    - CANCELLED          : Terminal state representing intentional cancellation by user or system.

Transitions:
  - Valid transitions strictly follow the directed lifecycle matrix.
  - Terminal states (COMPLETED, FAILED, CANCELLED) allow zero outbound transitions.
  - CANCELLED is reachable from any active (non-terminal) state upon cancellation request.
  - FAILED is reachable from any active state upon critical failure.
"""
from __future__ import annotations

import logging
from typing import Dict, Set

from backend.models.implementation import AgentState

logger = logging.getLogger(__name__)


class InvalidStateTransitionError(Exception):
    """Raised when an illegal or unsupported state transition is attempted."""

    def __init__(self, from_state: AgentState | str, to_state: AgentState | str, message: str = ""):
        self.from_state = from_state if isinstance(from_state, AgentState) else str(from_state)
        self.to_state = to_state if isinstance(to_state, AgentState) else str(to_state)
        msg = message or f"Illegal state transition from '{self.from_state}' to '{self.to_state}'"
        super().__init__(msg)


# Allowed transitions for active Phase 1 states
VALID_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
    AgentState.IDLE: {
        AgentState.UNDERSTANDING,
        AgentState.FAILED,
        AgentState.CANCELLED,
    },
    AgentState.UNDERSTANDING: {
        AgentState.PLANNING,
        AgentState.EXECUTING,  # Fast-path for direct controlled action
        AgentState.FAILED,
        AgentState.CANCELLED,
    },
    AgentState.PLANNING: {
        AgentState.AWAITING_APPROVAL,
        AgentState.EXECUTING,
        AgentState.FAILED,
        AgentState.CANCELLED,
    },
    AgentState.AWAITING_APPROVAL: {
        AgentState.EXECUTING,
        AgentState.PLANNING,  # Re-planning upon feedback
        AgentState.FAILED,
        AgentState.CANCELLED,
    },
    AgentState.EXECUTING: {
        AgentState.AWAITING_APPROVAL,  # Action-level approval pause
        AgentState.VERIFYING,
        AgentState.COMPLETED,  # Direct completion if action verification is built-in
        AgentState.FAILED,
        AgentState.CANCELLED,
    },
    AgentState.VERIFYING: {
        AgentState.COMPLETED,
        AgentState.FAILED,
        AgentState.CANCELLED,
    },
    AgentState.COMPLETED: set(),  # Terminal state: 0 outbound transitions
    AgentState.FAILED: set(),     # Terminal state: 0 outbound transitions
    AgentState.CANCELLED: set(),  # Terminal state: 0 outbound transitions
}

TERMINAL_STATES: Set[AgentState] = {
    AgentState.COMPLETED,
    AgentState.FAILED,
    AgentState.CANCELLED,
}


class AgentStateMachine:
    """
    State machine validator for EngineeringAgent lifecycle.
    Guarantees state transition invariants and rejects arbitrary state mutation.
    """

    @staticmethod
    def is_terminal(state: AgentState | str) -> bool:
        """Returns True if state is an immutable terminal state."""
        s = state if isinstance(state, AgentState) else AgentState(str(state))
        return s in TERMINAL_STATES

    @staticmethod
    def can_transition(from_state: AgentState | str, to_state: AgentState | str) -> bool:
        """Checks whether transition from from_state to to_state is permissible."""
        try:
            src = from_state if isinstance(from_state, AgentState) else AgentState(str(from_state))
            dst = to_state if isinstance(to_state, AgentState) else AgentState(str(to_state))
        except ValueError:
            return False

        allowed = VALID_TRANSITIONS.get(src, set())
        return dst in allowed

    @classmethod
    def validate_transition(
        cls,
        from_state: AgentState | str,
        to_state: AgentState | str,
    ) -> AgentState:
        """
        Validates transition and returns the new validated AgentState.
        Raises InvalidStateTransitionError on invalid transition.
        """
        try:
            src = from_state if isinstance(from_state, AgentState) else AgentState(str(from_state))
            dst = to_state if isinstance(to_state, AgentState) else AgentState(str(to_state))
        except ValueError as err:
            raise InvalidStateTransitionError(from_state, to_state, f"Unknown AgentState: {err}") from err

        # Invariant 1: Terminal state lock
        if cls.is_terminal(src):
            raise InvalidStateTransitionError(
                src, dst, f"Cannot transition from terminal state '{src.value}' to '{dst.value}'"
            )

        # Invariant 2: Directed transition table check
        allowed = VALID_TRANSITIONS.get(src, set())
        if dst not in allowed:
            allowed_names = [s.value for s in allowed]
            raise InvalidStateTransitionError(
                src,
                dst,
                f"Transition from '{src.value}' to '{dst.value}' is not allowed. Valid targets from '{src.value}': {allowed_names}",
            )

        return dst
