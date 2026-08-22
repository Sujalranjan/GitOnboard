"""
Phase 6 Engineering Agent Loop.

Controlled tool-calling loop that executes an approved engineering task inside
an isolated worktree, enforcing hard limits, tool policies, repetition detection,
and a strict completion protocol.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.agent.event_coordinator import AgentEventCoordinator
from backend.agent.loop.contracts import (
    AgentExecutionResult,
    AgentLoopConfig,
    CompletionSignal,
    StopReason,
    ToolCall,
    ToolObservation,
)
from backend.agent.loop.guardrails import LoopGuardrails
from backend.agent.loop.model_adapter import ModelAdapter, ModelMessage, ParsedModelOutput
from backend.agent.tasks.contracts import TaskExecutionContext
from backend.agent.tools.contracts import AgentToolContext, ToolResult
from backend.agent.tools.registry import AgentToolRegistry
from backend.agent.tools import create_default_tool_registry
from backend.models.implementation import AgentEventType, AgentRun

logger = logging.getLogger(__name__)


class EngineeringAgentLoop:
    """
    Controlled tool-calling execution loop for a single engineering task.
    """

    def __init__(
        self,
        tool_registry: Optional[AgentToolRegistry] = None,
        model_adapter: Optional[ModelAdapter] = None,
        event_coordinator: Optional[AgentEventCoordinator] = None,
        config: Optional[AgentLoopConfig] = None,
    ):
        self.tool_registry = tool_registry or create_default_tool_registry()
        self.model_adapter = model_adapter or ModelAdapter()
        self.events = event_coordinator or AgentEventCoordinator()
        self.default_config = config or AgentLoopConfig()

    def run(
        self,
        task_context: TaskExecutionContext,
        config: Optional[AgentLoopConfig] = None,
        db: Optional[Any] = None,
        run_model: Optional[AgentRun] = None,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> AgentExecutionResult:
        """
        Synchronous entry point for executing the agent loop.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.run_async(
                            task_context=task_context,
                            config=config,
                            db=db,
                            run_model=run_model,
                            cancel_checker=cancel_checker,
                        ),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.run_async(
                        task_context=task_context,
                        config=config,
                        db=db,
                        run_model=run_model,
                        cancel_checker=cancel_checker,
                    )
                )
        except RuntimeError:
            return asyncio.run(
                self.run_async(
                    task_context=task_context,
                    config=config,
                    db=db,
                    run_model=run_model,
                    cancel_checker=cancel_checker,
                )
            )

    async def run_async(
        self,
        task_context: TaskExecutionContext,
        config: Optional[AgentLoopConfig] = None,
        db: Optional[Any] = None,
        run_model: Optional[AgentRun] = None,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> AgentExecutionResult:
        """
        Asynchronous core tool-calling loop for implementing a single task.
        """
        start_time = time.perf_counter()
        effective_config = config or self.default_config
        guardrails = LoopGuardrails(config=effective_config)

        task_def = task_context.task_definition
        task_id = task_context.task_id

        logger.info(f"EngineeringAgentLoop: Starting execution for task '{task_id}' ('{task_def.title}')")

        # 1. Assemble compact task context and prompt messages
        available_tools = self.tool_registry.list_tools()
        system_prompt = self.model_adapter.build_system_prompt(
            tools=available_tools,
            acceptance_criteria=task_def.acceptance_criteria,
            constraints=[
                "Perform edits strictly within assigned worktree.",
                "Ensure syntax and interfaces remain intact.",
                f"Maximum {effective_config.max_agent_turns} iterations permitted.",
            ],
        )

        user_prompt = self._build_task_prompt(task_context)

        messages: List[ModelMessage] = [
            ModelMessage(role="system", content=system_prompt),
            ModelMessage(role="user", content=user_prompt),
        ]

        recorded_tool_calls: List[Dict[str, Any]] = []
        observations_log: List[str] = []

        # Emit initial task started event
        self._emit_event(
            db,
            run_model,
            AgentEventType.TASK_STARTED,
            f"EngineeringAgentLoop started for task '{task_id}': {task_def.title}",
            {"task_id": task_id, "step_number": task_def.step_number},
        )

        # 2. Main Execution Loop
        while True:
            # Check Cancellation
            if (cancel_checker and cancel_checker()) or (run_model and getattr(run_model, "cancel_requested", False)):
                logger.info(f"EngineeringAgentLoop: Execution cancelled for task '{task_id}'")
                self._emit_event(
                    db, run_model, AgentEventType.CANCELLED, f"Execution cancelled for task '{task_id}'", {"task_id": task_id}
                )
                return self._finalize_result(
                    task_context=task_context,
                    status="CANCELLED",
                    stop_reason=StopReason.CANCELLED,
                    guardrails=guardrails,
                    recorded_tool_calls=recorded_tool_calls,
                    observations_log=observations_log,
                    start_time=start_time,
                    error="Task execution was explicitly cancelled.",
                )

            # Pre-turn guardrail checks (turns, task timeout)
            stop_reason = guardrails.check_pre_turn_limits()
            if stop_reason:
                err_msg = f"Task terminated due to guardrail limit: {stop_reason.value}"
                logger.warning(f"EngineeringAgentLoop: {err_msg}")
                self._emit_event(
                    db, run_model, AgentEventType.AGENT_LOOP_STOPPED, err_msg, {"task_id": task_id, "stop_reason": stop_reason.value}
                )
                return self._finalize_result(
                    task_context=task_context,
                    status="FAILED",
                    stop_reason=stop_reason,
                    guardrails=guardrails,
                    recorded_tool_calls=recorded_tool_calls,
                    observations_log=observations_log,
                    start_time=start_time,
                    error=err_msg,
                )

            guardrails.record_turn()

            # Emit AGENT_THINKING event (activity status only, no chain-of-thought leaked)
            self._emit_event(
                db,
                run_model,
                AgentEventType.AGENT_THINKING,
                f"Agent planning next action for task '{task_id}' (iteration {guardrails.turn_count})...",
                {"task_id": task_id, "turn": guardrails.turn_count, "activity": "planning next action"},
            )

            # Call Model Adapter
            try:
                raw_response = await self.model_adapter.call_model(messages)
            except Exception as err:
                logger.error(f"EngineeringAgentLoop: Model generation failed: {err}")
                self._emit_event(
                    db, run_model, AgentEventType.AGENT_LOOP_STOPPED, f"Model generation error: {str(err)}", {"task_id": task_id}
                )
                return self._finalize_result(
                    task_context=task_context,
                    status="FAILED",
                    stop_reason=StopReason.MODEL_ERROR,
                    guardrails=guardrails,
                    recorded_tool_calls=recorded_tool_calls,
                    observations_log=observations_log,
                    start_time=start_time,
                    error=f"Model error: {str(err)}",
                )

            # Parse Model Output
            parsed: ParsedModelOutput = self.model_adapter.parse_response(raw_response)

            # ──────────────────────────────────────────────────────────────────
            # A. Malformed Output Handling
            # ──────────────────────────────────────────────────────────────────
            if parsed.is_malformed:
                logger.warning(f"EngineeringAgentLoop: Malformed output on turn {guardrails.turn_count}: {parsed.parse_error}")
                self._emit_event(
                    db,
                    run_model,
                    AgentEventType.AGENT_LIMIT_WARNING,
                    f"Received malformed response from model: {parsed.parse_error}",
                    {"task_id": task_id, "parse_error": parsed.parse_error},
                )
                messages.append(ModelMessage(role="assistant", content=parsed.raw_response))
                messages.append(
                    ModelMessage(
                        role="user",
                        content=(
                            f"PROTOCOL ERROR: Your response could not be parsed: {parsed.parse_error}\n"
                            f"You MUST respond with a single valid JSON object containing either "
                            f"{{\"action\": \"tool_call\", ...}} or {{\"action\": \"complete\", ...}}."
                        ),
                    )
                )
                continue

            # ──────────────────────────────────────────────────────────────────
            # B. Completion Signal Handling
            # ──────────────────────────────────────────────────────────────────
            if parsed.completion_signal:
                signal = parsed.completion_signal
                logger.info(f"EngineeringAgentLoop: Agent requested completion for task '{task_id}' with {len(signal.acceptance_criteria_status)} criteria evaluations.")

                self._emit_event(
                    db,
                    run_model,
                    AgentEventType.AGENT_COMPLETION_REQUESTED,
                    f"Agent completed implementation steps: {signal.summary}",
                    {"task_id": task_id, "summary": signal.summary, "criteria_count": len(signal.acceptance_criteria_status)},
                )

                # Capture diff and changed files
                changed_files, diff_text = self._capture_changes(task_context)

                self._emit_event(
                    db,
                    run_model,
                    AgentEventType.AGENT_TASK_READY_FOR_VERIFICATION,
                    f"Task '{task_id}' ready for Phase 7 verification.",
                    {"task_id": task_id, "changed_files": changed_files},
                )

                return self._finalize_result(
                    task_context=task_context,
                    status="COMPLETED_FOR_VERIFICATION",
                    stop_reason=StopReason.COMPLETED_FOR_VERIFICATION,
                    guardrails=guardrails,
                    recorded_tool_calls=recorded_tool_calls,
                    observations_log=observations_log,
                    start_time=start_time,
                    changed_files=changed_files,
                    diff=diff_text,
                    completion_signal=signal,
                )

            # ──────────────────────────────────────────────────────────────────
            # C. Tool Call Handling
            # ──────────────────────────────────────────────────────────────────
            if parsed.tool_call:
                tool_call: ToolCall = parsed.tool_call

                self._emit_event(
                    db,
                    run_model,
                    AgentEventType.AGENT_TOOL_REQUESTED,
                    f"Model requested tool '{tool_call.tool_name}'",
                    {"task_id": task_id, "tool_name": tool_call.tool_name, "arguments": tool_call.arguments},
                )

                # Guardrail check (tool counts and repetition loop)
                limit_stop_reason, should_warn = guardrails.record_tool_call(
                    tool_call.tool_name, tool_call.arguments
                )
                if limit_stop_reason:
                    err_msg = f"Loop terminated by guardrails: {limit_stop_reason.value}"
                    logger.warning(f"EngineeringAgentLoop: {err_msg}")
                    self._emit_event(
                        db,
                        run_model,
                        AgentEventType.AGENT_LOOP_STOPPED,
                        err_msg,
                        {"task_id": task_id, "stop_reason": limit_stop_reason.value},
                    )
                    return self._finalize_result(
                        task_context=task_context,
                        status="FAILED",
                        stop_reason=limit_stop_reason,
                        guardrails=guardrails,
                        recorded_tool_calls=recorded_tool_calls,
                        observations_log=observations_log,
                        start_time=start_time,
                        error=err_msg,
                    )

                # Tool Dispatch via AgentToolRegistry (Enforces ToolPolicy & worktree boundaries)
                tool_result = self._execute_tool(task_context=task_context, tool_call=tool_call, db=db, run_model=run_model)

                # Sanitize observation data
                sanitized_data = guardrails.sanitize_observation(tool_result.data)

                # Log tool execution record
                recorded_tool_calls.append({
                    "tool_call_id": tool_call.tool_call_id,
                    "tool_name": tool_call.tool_name,
                    "arguments": tool_call.arguments,
                    "success": tool_result.success,
                    "duration_ms": tool_result.metadata.get("duration_ms", 0.0),
                    "error": tool_result.error.model_dump() if tool_result.error else None,
                })
                observations_log.append(
                    f"Turn {guardrails.turn_count} | {tool_call.tool_name}: {'SUCCESS' if tool_result.success else 'FAILED'}"
                )

                # Append assistant tool call proposal and tool observation message
                messages.append(ModelMessage(role="assistant", content=parsed.raw_response))

                obs_payload = {
                    "tool_call_id": tool_call.tool_call_id,
                    "tool_name": tool_call.tool_name,
                    "success": tool_result.success,
                    "data": sanitized_data,
                    "error": tool_result.error.model_dump() if tool_result.error else None,
                }
                obs_content = json.dumps(obs_payload, default=str)

                if should_warn:
                    obs_content += (
                        f"\n\nWARNING: You have called tool '{tool_call.tool_name}' with identical parameters "
                        f"multiple times consecutively. Proceeding with the same call again will cause "
                        f"immediate loop termination for loop detection."
                    )
                    self._emit_event(
                        db,
                        run_model,
                        AgentEventType.AGENT_LIMIT_WARNING,
                        f"Repeated tool call warning emitted for tool '{tool_call.tool_name}'",
                        {"task_id": task_id, "tool_name": tool_call.tool_name},
                    )

                messages.append(
                    ModelMessage(
                        role="tool",
                        content=obs_content,
                        tool_call_id=tool_call.tool_call_id,
                    )
                )

    def _execute_tool(
        self,
        task_context: TaskExecutionContext,
        tool_call: ToolCall,
        db: Optional[Any] = None,
        run_model: Optional[AgentRun] = None,
    ) -> ToolResult:
        """
        Executes a proposed tool call through the AgentToolRegistry.
        Guarantees that ToolPolicy and worktree isolation are enforced.
        """
        tool_ctx = AgentToolContext(
            agent_run_id=task_context.agent_run_id,
            repository_id=task_context.repository_id,
            task_id=task_context.task_id,
            worktree_path=task_context.worktree_path,
            config=task_context.execution_config,
            db=db,
        )

        self._emit_event(
            db,
            run_model,
            AgentEventType.TOOL_CALL_STARTED,
            f"Executing tool '{tool_call.tool_name}'...",
            {"task_id": task_context.task_id, "tool_name": tool_call.tool_name},
        )

        tool_result: ToolResult = self.tool_registry.invoke(
            name=tool_call.tool_name,
            arguments=tool_call.arguments,
            context=tool_ctx,
        )

        if tool_result.success:
            self._emit_event(
                db,
                run_model,
                AgentEventType.TOOL_CALL_COMPLETED,
                f"Tool '{tool_call.tool_name}' completed successfully in {tool_result.metadata.get('duration_ms', 0.0):.1f}ms",
                {"task_id": task_context.task_id, "tool_name": tool_call.tool_name, "duration_ms": tool_result.metadata.get("duration_ms", 0.0)},
            )
        else:
            err_code = tool_result.error.code if tool_result.error else "UNKNOWN_ERROR"
            err_msg = tool_result.error.message if tool_result.error else "Execution failed"
            self._emit_event(
                db,
                run_model,
                AgentEventType.TOOL_CALL_FAILED,
                f"Tool '{tool_call.tool_name}' failed ({err_code}): {err_msg}",
                {"task_id": task_context.task_id, "tool_name": tool_call.tool_name, "error_code": err_code, "error_message": err_msg},
            )

        return tool_result

    def _capture_changes(self, task_context: TaskExecutionContext) -> Tuple[List[str], Optional[str]]:
        """
        Captures modified files and unified diff from the worktree via git tools or filesystem.
        """
        changed_files: List[str] = []
        diff_text: Optional[str] = None

        if self.tool_registry.get_tool("get_status") and task_context.worktree_path:
            tool_ctx = AgentToolContext(
                agent_run_id=task_context.agent_run_id,
                repository_id=task_context.repository_id,
                task_id=task_context.task_id,
                worktree_path=task_context.worktree_path,
            )
            res = self.tool_registry.invoke("get_status", {}, tool_ctx)
            if res.success and isinstance(res.data, dict):
                changed_files = res.data.get("modified_files", [])

        if self.tool_registry.get_tool("get_diff") and task_context.worktree_path:
            tool_ctx = AgentToolContext(
                agent_run_id=task_context.agent_run_id,
                repository_id=task_context.repository_id,
                task_id=task_context.task_id,
                worktree_path=task_context.worktree_path,
            )
            diff_res = self.tool_registry.invoke("get_diff", {}, tool_ctx)
            if diff_res.success and isinstance(diff_res.data, dict):
                diff_text = diff_res.data.get("diff")
                if not changed_files:
                    changed_files = diff_res.data.get("modified_files", [])

        # Fallback to task's affected files if no git status is available
        if not changed_files and task_context.task_definition.affected_files:
            changed_files = list(task_context.task_definition.affected_files)

        return changed_files, diff_text

    def _build_task_prompt(self, context: TaskExecutionContext) -> str:
        """
        Builds the task-specific user prompt containing task definition, criteria, and context.
        """
        task = context.task_definition
        criteria_str = "\n".join([f"- {c}" for c in task.acceptance_criteria]) if task.acceptance_criteria else "None specified"
        files_str = "\n".join([f"- {f}" for f in task.affected_files]) if task.affected_files else "None specified"

        repo_summary = json.dumps(context.repository_context_summary or {}, indent=2)

        return f"""### TASK TO EXECUTE:
Task ID: {task.task_id} (Step {task.step_number})
Title: {task.title}
Description: {task.description}

### TARGET FILES:
{files_str}

### ACCEPTANCE CRITERIA:
{criteria_str}

### VERIFICATION STRATEGY:
{task.verification_strategy}

### REPOSITORY CONTEXT SUMMARY:
{repo_summary}

### WORKTREE PATH:
{context.worktree_path or "Isolated in-memory / local workspace"}

Please begin by inspecting the necessary files or searching the codebase, make the required modifications, and finally propose the 'complete' action once all acceptance criteria are met.
"""

    def _finalize_result(
        self,
        task_context: TaskExecutionContext,
        status: str,
        stop_reason: StopReason,
        guardrails: LoopGuardrails,
        recorded_tool_calls: List[Dict[str, Any]],
        observations_log: List[str],
        start_time: float,
        changed_files: Optional[List[str]] = None,
        diff: Optional[str] = None,
        completion_signal: Optional[CompletionSignal] = None,
        error: Optional[str] = None,
    ) -> AgentExecutionResult:
        """
        Constructs the final AgentExecutionResult payload.
        """
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return AgentExecutionResult(
            status=status,
            task_id=task_context.task_id,
            iterations=guardrails.turn_count,
            tool_call_count=guardrails.tool_call_count,
            changed_files=changed_files or [],
            diff=diff,
            observations=observations_log,
            tool_calls=recorded_tool_calls,
            completion_signal=completion_signal,
            stop_reason=stop_reason,
            error=error,
            duration_ms=round(duration_ms, 2),
            metadata={
                "command_count": guardrails.command_count,
                "agent_run_id": task_context.agent_run_id,
                "plan_id": task_context.plan_id,
            },
        )

    def _emit_event(
        self,
        db: Optional[Any],
        run_model: Optional[AgentRun],
        event_type: AgentEventType,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emits structured SSE events via AgentEventCoordinator without exposing private reasoning.
        """
        if db and run_model and self.events:
            try:
                self.events.emit_event(
                    db=db,
                    run=run_model,
                    event_type=event_type,
                    message=message,
                    payload=payload or {},
                )
            except Exception as err:
                logger.warning(f"EngineeringAgentLoop: Failed to emit event {event_type.value}: {err}")
