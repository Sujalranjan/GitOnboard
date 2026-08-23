"""
AgentEventCoordinator: Centralized event emission and SSE broadcast coordinator.

Guarantees:
  - Structured event payload standard:
      {
        "agent_run_id": str,
        "task_id": Optional[str],
        "event_type": str,
        "message": str,
        "payload": dict,
        "created_at": ISO8601 string
      }
  - PostgreSQL persistence into `agent_events` table.
  - Real-time SSE publication through the existing TaskManager pub/sub infrastructure.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.models.implementation import AgentEvent, AgentEventType, AgentRun
from backend.task_manager import task_manager

logger = logging.getLogger(__name__)

# Matches existing backend.services.agent_events convention
_EVENT_CHANNEL_USER_ID = 0


def _channel_for_run(run_id: str) -> str:
    return f"agent:{run_id}"


class AgentEventCoordinator:
    """
    Central event coordinator for the Engineering Agent subsystem.
    """

    @classmethod
    def emit_event(
        cls,
        db: Session,
        agent_run: AgentRun,
        event_type: AgentEventType | str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> AgentEvent:
        """
        Persists an AgentEvent and broadcasts it over SSE channels:
          - agent:{agent_run.id}
          - agent:{agent_run.task_id} (if different)
        """
        ev_type = event_type if isinstance(event_type, AgentEventType) else AgentEventType(str(event_type))
        safe_payload = payload or {}

        event = AgentEvent(
            agent_run_id=agent_run.id,
            event_type=ev_type,
            message=message,
            payload=safe_payload,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        created_iso = (
            event.created_at.isoformat()
            if event.created_at
            else datetime.now(timezone.utc).isoformat()
        )

        event_payload_json = json.dumps(
            {
                "agent_run_id": agent_run.id,
                "task_id": agent_run.task_id,
                "event_type": ev_type.value,
                "message": message,
                "payload": safe_payload,
                "created_at": created_iso,
            }
        )

        # Broadcast on primary agent_run_id channel to run owner and default
        target_uids = [agent_run.user_id] if agent_run.user_id is not None else [0]
        if 0 not in target_uids:
            target_uids.append(0)

        for uid in target_uids:
            cls._safe_notify(uid, _channel_for_run(agent_run.id), ev_type.value, event_payload_json)
            if agent_run.task_id and agent_run.task_id != agent_run.id:
                cls._safe_notify(uid, _channel_for_run(agent_run.task_id), ev_type.value, event_payload_json)

        logger.debug(f"AgentEvent emitted: run_id={agent_run.id} type={ev_type.value} msg='{message}'")
        return event

    @staticmethod
    def _safe_notify(user_id: int, channel: str, event_name: str, payload_json: str) -> None:
        try:
            task_manager.notify(
                user_id,
                channel,
                event_name,
                payload_json,
            )
        except Exception as err:
            logger.debug(f"AgentEventCoordinator: SSE notify failed for user '{user_id}' channel '{channel}': {err}")
