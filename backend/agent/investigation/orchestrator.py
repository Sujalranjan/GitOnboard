"""
Investigation Orchestrator: Connects Main LLM Planner + Local Worker + Persistent State.

Features:
- Adaptive plan expansion (Phase 4): checks worker discovered_next_steps and adds tasks.
- Token and turn budgeting (Phase 4).
- Completion and claim verification integration (Phase 5).
- SSE streaming callback support (Phase 6).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.agent.investigation.planner import MainInvestigationPlanner
from backend.agent.investigation.schemas import (
    InvestigationSubtask,
    SubtaskStatus,
    WorkerTaskResult,
)
from backend.agent.investigation.state_store import InvestigationStateStore
from backend.agent.investigation.worker import LocalInvestigationWorker
from backend.agent.loop.contracts import StopReason
from backend.config import settings
from backend.services.qa_loop import QALoopResult
from backend.services.qa_validation import validate_final_answer_against_evidence

logger = logging.getLogger(__name__)


class InvestigationOrchestrator:
    """
    Coordinates multi-phase investigation using Main LLM and Local Worker.
    """

    def __init__(
        self,
        planner: MainInvestigationPlanner,
        worker: LocalInvestigationWorker,
        db: Optional[Session] = None,
        analysis_id: Optional[int] = None,
        max_total_tasks: Optional[int] = None,
        concurrency: Optional[int] = None,
        subtask_timeout: Optional[float] = None,
        on_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.planner = planner
        self.worker = worker
        self.db = db
        self.analysis_id = analysis_id
        self.max_total_tasks = max_total_tasks if max_total_tasks is not None else settings.investigation_max_total_tasks
        self.concurrency = concurrency if concurrency is not None else settings.investigation_concurrency
        self.subtask_timeout = subtask_timeout if subtask_timeout is not None else settings.investigation_subtask_timeout
        self.on_event = on_event_callback

    async def run(self, question: str, repo_summary: str = "") -> QALoopResult:
        """
        Execute end-to-end investigation workflow.
        """
        start_time = time.perf_counter()
        inv_id = f"inv_{uuid.uuid4().hex[:8]}"
        store = InvestigationStateStore(inv_id, db=self.db, analysis_id=self.analysis_id)

        # 1. Main LLM: Decompose question into initial investigation subtasks
        await self._emit_event({
            "type": "investigation-start",
            "investigation_id": inv_id,
            "query": question,
            "main_model": getattr(self.planner, "model", "default"),
            "worker_model": getattr(self.worker, "model", "qwen3:4b-instruct"),
            "message": "Starting multi-agent repository investigation...",
        })

        planner_llm = getattr(self.planner, "llm_service", None)
        planner_provider = getattr(planner_llm, "provider", "ollama") if planner_llm else "ollama"

        await self._emit_event({
            "type": "agent-spawn",
            "agent_id": "planner-main",
            "role": "Planner & Synthesizer",
            "model": getattr(self.planner, "model", "default"),
            "provider": planner_provider,
            "is_local": True,
            "status": "running",
            "current_task": "Decompose inquiry into verification plan",
        })

        initial_tasks = await self.planner.create_plan(question, repo_summary)
        for t in initial_tasks:
            store.tasks[t.id] = t

        await self._emit_event({
            "type": "plan-created",
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "target_entities": t.target_entities,
                    "search_strategy": t.search_strategy,
                    "expected_output": t.expected_output,
                    "completion_criteria": t.completion_criteria,
                    "status": t.status.value,
                    "dependencies": t.dependencies,
                }
                for t in initial_tasks
            ],
            "message": f"Generated investigation checklist with {len(initial_tasks)} tasks." + (" (Using dynamic fallback plan)" if getattr(self.planner, "last_plan_fallback_used", False) else ""),
        })

        await self._emit_event({
            "type": "agent-update",
            "agent_id": "planner-main",
            "status": "waiting",
            "current_task": "Awaiting worker evidence collection",
        })

        # 2. Sequential Execution Loop: Dispatch ready tasks to Local Worker one-by-one
        tasks_executed = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        all_turns = []

        while tasks_executed < self.max_total_tasks:
            ready_tasks = store.get_ready_tasks()
            if not ready_tasks:
                break

            current_task = ready_tasks[0]
            current_task.status = SubtaskStatus.RUNNING
            worker_id = f"worker-{current_task.id}"

            await self._emit_event({
                "type": "agent-spawn",
                "agent_id": worker_id,
                "role": "Local Repository Explorer",
                "model": getattr(self.worker, "model", "qwen3:4b-instruct"),
                "provider": getattr(self.worker, "provider", "ollama"),
                "is_local": True,
                "status": "running",
                "current_task": current_task.title,
                "task_id": current_task.id,
                "acceptance_criteria": current_task.completion_criteria or current_task.expected_output,
            })

            await self._emit_event({
                "type": "task-update",
                "task_id": current_task.id,
                "status": "RUNNING",
                "assigned_agent": worker_id,
                "message": f"Worker active on: {current_task.title}",
            })

            # Retrieve verified findings from previously completed tasks to prevent redundant investigation
            prior_findings = store.get_all_findings()

            # Execute subtask with complete context and hard timeout guarantee
            # Explicitly reset per-agent state before execution to ensure complete isolation
            if hasattr(self.worker, "reset_active_state"):
                self.worker.reset_active_state()

            worker_result = None
            turns = []
            try:
                worker_res = await asyncio.wait_for(
                    self.worker.execute_subtask(
                        subtask=current_task,
                        user_question=question,
                        repo_context=repo_summary,
                        prior_findings=prior_findings,
                    ),
                    timeout=self.subtask_timeout,
                )
                if isinstance(worker_res, tuple) and len(worker_res) == 2:
                    worker_result, turns = worker_res
                else:
                    worker_result = worker_res
                    turns = []
            except asyncio.TimeoutError:
                logger.error(f"[InvestigationOrchestrator] Subtask '{current_task.id}' timed out after {self.subtask_timeout}s.")
                # Harvest partial progress from worker if available
                p_read = list(getattr(self.worker, "_active_files_read", []))
                p_inspected = list(getattr(self.worker, "_active_files_inspected", []))
                p_findings = list(getattr(self.worker, "_active_findings", []))
                p_turns = list(getattr(self.worker, "_active_turns", []))
                turns = p_turns

                worker_result = WorkerTaskResult(
                    task_id=current_task.id,
                    status=SubtaskStatus.COMPLETED if p_findings else SubtaskStatus.FAILED,
                    findings=p_findings,
                    files_read=p_read,
                    files_inspected=p_inspected,
                    error=None if p_findings else f"Worker execution timed out after {int(self.subtask_timeout)} seconds without completing.",
                    coverage_gaps=["Task execution reached absolute timeout."],
                    limitations=["Subtask timed out before completing downstream traces, but recorded inspected files."],
                )
            except Exception as e:
                logger.exception(f"[InvestigationOrchestrator] Subtask '{current_task.id}' raised unexpected error: {e}")
                worker_result = WorkerTaskResult(
                    task_id=current_task.id,
                    status=SubtaskStatus.FAILED,
                    error=f"Worker crashed: {str(e)}",
                    coverage_gaps=[f"Worker error: {str(e)}"],
                    limitations=["Execution halted due to unhandled exception."],
                )
            finally:
                # Cleanly clear worker active state so timer or partial findings from this task cannot bleed into next task
                if hasattr(self.worker, "reset_active_state"):
                    self.worker.reset_active_state()

            all_turns.extend(turns)
            store.turns_history.extend(turns)
            store.record_worker_result(worker_result)
            tasks_executed += 1

            total_prompt_tokens += getattr(worker_result, "prompt_tokens", 0)
            total_completion_tokens += getattr(worker_result, "completion_tokens", 0)

            # Emit token update event
            await self._emit_event({
                "type": "token-update",
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "task_id": current_task.id,
            })

            # Emit findings
            for f in worker_result.findings:
                await self._emit_event({
                    "type": "finding-saved",
                    "finding": {
                        "id": f.id,
                        "task_id": f.task_id,
                        "file_path": f.file_path,
                        "line_start": f.line_start,
                        "line_end": f.line_end,
                        "symbol_name": f.symbol_name,
                        "finding_type": f.finding_type.value,
                        "summary": f.summary,
                        "code_excerpt": f.code_excerpt,
                        "confidence": f.confidence,
                    },
                })

            worker_summary = (
                f"Inspected {len(worker_result.files_inspected)} files, {len(worker_result.findings)} findings verified."
                if worker_result.status == SubtaskStatus.COMPLETED
                else f"Task ended: {worker_result.error or 'Incomplete investigation'}"
            )

            await self._emit_event({
                "type": "agent-update",
                "agent_id": worker_id,
                "status": "completed" if worker_result.status == SubtaskStatus.COMPLETED else "failed",
                "summary": worker_summary,
                "files_read": worker_result.files_read,
                "files_skipped": worker_result.files_skipped,
                "read_failures": worker_result.read_failures,
                "coverage_gaps": worker_result.coverage_gaps,
            })

            await self._emit_event({
                "type": "task-update",
                "task_id": current_task.id,
                "status": current_task.status.value,
                "findings_count": len(worker_result.findings),
                "files_inspected": worker_result.files_inspected,
                "files_read": worker_result.files_read,
                "coverage_gaps": worker_result.coverage_gaps,
                "reason_failed": worker_result.error,
            })

            # Explicitly emit contribution to shared investigation memory dossier
            await self._emit_event({
                "type": "memory-update",
                "agent_id": worker_id,
                "task_id": current_task.id,
                "findings_count": len(worker_result.findings),
                "files_read_count": len(worker_result.files_read),
                "title": f"Worker returned {len(worker_result.findings)} verified findings and {len(worker_result.files_read)} inspected files to main agent memory",
                "findings": [
                    {"summary": f.summary, "file_path": f.file_path, "symbol_name": f.symbol_name}
                    for f in worker_result.findings
                ],
                "files_read": worker_result.files_read,
                "coverage_gaps": worker_result.coverage_gaps,
            })

            # Adaptive Discovery: Dynamically spawn follow-up subtasks/subagents based on findings & discovered next steps
            # Gives the agent loop full freedom to explore deeper downstream services within configured task limits
            candidate_next_items = list(worker_result.discovered_next_steps)
            for f in worker_result.findings:
                if f.discovered_dependencies:
                    for dep_symbol in f.discovered_dependencies:
                        if dep_symbol not in candidate_next_items:
                            candidate_next_items.append(f"dependency {dep_symbol} discovered in {f.file_path}")

            if candidate_next_items and len(store.tasks) < self.max_total_tasks:
                available_slots = self.max_total_tasks - len(store.tasks)
                for next_item in candidate_next_items[:available_slots]:
                    new_id = f"task_discovered_{len(store.tasks) + 1}"
                    if new_id not in store.tasks:
                        # If current task completed, the new task is immediately actionable (no unmet dependency blocker)
                        deps = [] if worker_result.status == SubtaskStatus.COMPLETED else [current_task.id]
                        new_task = store.create_task(
                            task_id=new_id,
                            title=f"Investigate {next_item[:60]}",
                            description=f"Adaptive subtask spawned following {current_task.title}: {next_item}",
                            search_strategy="Use search_repository, search_code, and read_file to inspect downstream code",
                            dependencies=deps,
                        )
                        logger.info(f"[InvestigationOrchestrator] Spawned dynamic subtask '{new_id}': {new_task.title} (total tasks: {len(store.tasks)}/{self.max_total_tasks})")
                        await self._emit_event({
                            "type": "task-discovered",
                            "task": {
                                "id": new_task.id,
                                "title": new_task.title,
                                "description": new_task.description,
                                "status": new_task.status.value,
                                "dependencies": new_task.dependencies,
                            },
                        })

        # Ensure any remaining PENDING tasks whose dependencies were not met are transitioned to BLOCKED
        for task in store.tasks.values():
            if task.status == SubtaskStatus.PENDING:
                task.status = SubtaskStatus.BLOCKED
                task.error = "Unresolved or failed dependencies prevented execution."
                store.coverage_gaps.append(f"Task '{task.title}' was blocked by dependency failure.")
                await self._emit_event({
                    "type": "task-update",
                    "task_id": task.id,
                    "status": "BLOCKED",
                    "reason_failed": task.error,
                })

        # 3. Main LLM: Synthesize final answer from verified evidence dossier
        await self._emit_event({
            "type": "agent-update",
            "agent_id": "planner-main",
            "status": "running",
            "current_task": "Synthesizing final verified response from evidence dossier",
        })

        raw_answer = await self.planner.synthesize_answer(question, store)

        await self._emit_event({
            "type": "agent-update",
            "agent_id": "planner-main",
            "status": "completed",
            "summary": "Completed final grounded synthesis.",
        })

        # 4. Phase 5 Verification Gate: Validate factual claims using REAL turns collected during worker execution
        result = QALoopResult(
            answer=raw_answer,
            stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
            turns=all_turns,
            tool_call_count=len(all_turns),
            files_read=list(store.files_read or store.inspected_files),
        )

        is_valid, feedback, caveated = validate_final_answer_against_evidence(raw_answer, result)
        result.answer = caveated or raw_answer
        elapsed = time.perf_counter() - start_time
        result.latency_ms = {"total": elapsed * 1000}

        return result

    async def _emit_event(self, event_data: Dict[str, Any]) -> None:
        if self.on_event:
            try:
                res = self.on_event(event_data)
                if hasattr(res, "__await__"):
                    await res
            except Exception as e:
                logger.warning(f"[InvestigationOrchestrator] Event emission error: {e}")

