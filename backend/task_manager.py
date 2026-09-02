"""
In-process pub/sub TaskManager.

Background threads call notify() after updating the DB.
SSE endpoints subscribe to receive instant push notifications
without any polling.

Architecture:
  Background thread
    │ updates DB (persistence)
    │ calls task_manager.notify(...)
    ▼
  TaskManager
    │ updates in-memory status dict
    │ pushes to all subscriber asyncio.Queues
    ▼
  SSE endpoint
    │ reads from its Queue
    │ streams event to browser
    ▼
  Browser (EventSource)
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, Set

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self):
        # {f"{user_id}:{repo_name}": {"task_name": "status", ...}}
        self._statuses: Dict[str, Dict[str, str]] = {}
        # {f"{user_id}:{repo_name}": {asyncio.Queue, ...}}
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        # The main event loop — set once at startup
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def _key(self, user_id: int, repo_name: str) -> str:
        return f"{user_id}:{repo_name}"

    def notify(self, user_id: int, repo_name: str, task_name: str, status: str):
        """
        Called from background threads (after updating DB).
        Updates in-memory state and pushes to all SSE subscribers.
        Thread-safe via call_soon_threadsafe.
        """
        key = self._key(user_id, repo_name)

        if key not in self._statuses:
            self._statuses[key] = {}
        self._statuses[key][task_name] = status

        subscriber_count = len(self._subscribers.get(key, set()))
        logger.info(f"[TaskManager] Notification: user_id={user_id}, repo={repo_name}, task={task_name}, status={status}, subscribers={subscriber_count}")

        if self._loop and not self._loop.is_closed():
            try:
                parsed = json.loads(status)
                if isinstance(parsed, dict) and ("event_type" in parsed or "agent_run_id" in parsed or "payload" in parsed):
                    payload = status
                else:
                    payload = json.dumps({task_name: status})
            except Exception:
                payload = json.dumps({task_name: status})

            for queue in list(self._subscribers[key]):
                logger.info(f"[TaskManager] Pushing to queue: {payload}")
                self._loop.call_soon_threadsafe(queue.put_nowait, payload)
        else:
            logger.warning(f"[TaskManager] Event loop not available, notification discarded")

    def get_all(self, user_id: int, repo_name: str) -> Dict[str, str]:
        """Return snapshot of all task statuses for a repo."""
        return dict(self._statuses.get(self._key(user_id, repo_name), {}))

    def subscribe(self, user_id: int, repo_name: str) -> asyncio.Queue:
        """Register a new SSE subscriber. Returns a Queue to read events from."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[self._key(user_id, repo_name)].add(queue)
        return queue

    def unsubscribe(self, user_id: int, repo_name: str, queue: asyncio.Queue):
        """Remove a subscriber when the SSE connection closes."""
        self._subscribers[self._key(user_id, repo_name)].discard(queue)


# Singleton — imported by repo.py and main.py
task_manager = TaskManager()
