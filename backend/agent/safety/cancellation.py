"""
CancellationController: Thread-safe, unified cancellation controller for Phase 9.

Enforces:
  1. Safe interruption across EngineeringAgentLoop, TerminalExecutor, VerificationDispatcher, and RepairController.
  2. Guardrail 2: CANCELLED represents explicit human/operator cancellation. BLOCKED represents safety/policy/repair limits.
  3. Interrupted tasks never transition to a false PASSED state.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Optional
from sqlalchemy.orm import Session

from backend.agent.event_coordinator import AgentEventCoordinator
from backend.models.implementation import AgentEventType, AgentRun, AgentState

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OperationCancelledError(Exception):
    """Raised when an operation is cancelled via CancellationToken."""
    def __init__(self, reason: str = "Operation was cancelled"):
        self.reason = reason
        super().__init__(reason)


class CancellationToken:
    """
    Thread-safe cancellation token checked periodically by long-running agent subsystems.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._cancelled = threading.Event()
        self._reason: Optional[str] = None
        self._cancelled_at: Optional[datetime] = None

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    @property
    def cancelled_at(self) -> Optional[datetime]:
        return self._cancelled_at

    def cancel(self, reason: str = "User requested cancellation") -> None:
        self._reason = reason
        self._cancelled_at = _now()
        self._cancelled.set()
        logger.info(f"CancellationToken: Run '{self.run_id}' cancelled: {reason}")

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise OperationCancelledError(self._reason or "Operation was cancelled")


class CancellationController:
    """
    Registry of active CancellationTokens for running agent sessions.
    """

    _tokens: Dict[str, CancellationToken] = {}
    _lock = threading.Lock()

    def __init__(self, event_coordinator: Optional[AgentEventCoordinator] = None):
        self.event_coordinator = event_coordinator or AgentEventCoordinator()

    @classmethod
    def get_or_create_token(cls, run_id: str) -> CancellationToken:
        """Retrieves or registers a CancellationToken for the run."""
        with cls._lock:
            if run_id not in cls._tokens:
                cls._tokens[run_id] = CancellationToken(run_id)
            return cls._tokens[run_id]

    @classmethod
    def get_token(cls, run_id: str) -> Optional[CancellationToken]:
        """Retrieves the active token if one exists."""
        with cls._lock:
            return cls._tokens.get(run_id)

    @classmethod
    def unregister_token(cls, run_id: str) -> None:
        """Cleans up the token when a run concludes."""
        with cls._lock:
            cls._tokens.pop(run_id, None)

    def cancel_run(
        self,
        db: Session,
        run_id: str,
        reason: str = "User requested cancellation",
        run_model: Optional[AgentRun] = None,
    ) -> bool:
        """
        Requests cancellation across all executing subsystems for the run.
        Emits CANCELLATION_REQUESTED and CANCELLED events and updates database state.
        """
        token = self.get_or_create_token(run_id)
        token.cancel(reason=reason)

        run = run_model or db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run:
            self.event_coordinator.emit_event(
                db=db,
                agent_run=run,
                event_type=AgentEventType.CANCELLATION_REQUESTED,
                message=f"Cancellation requested for run '{run_id}': {reason}",
                payload={"run_id": run_id, "reason": reason},
            )

        if run and run.current_state != AgentState.CANCELLED:
            run.current_state = AgentState.CANCELLED
            run.cancellation_reason = reason
            run.completed_at = _now()
            db.add(run)
            db.commit()

            self.event_coordinator.emit_event(
                db=db,
                agent_run=run,
                event_type=AgentEventType.CANCELLED,
                message=f"Run '{run_id}' transitioned to CANCELLED: {reason}",
                payload={"run_id": run_id, "reason": reason},
            )

        logger.info(f"CancellationController: Cancelled run '{run_id}' successfully")
        return True
