"""
Terminal Tools: Thin adapters for controlled command detection and execution via SandboxManager.

Security Invariant:
  All commands execute strictly inside the assigned run worktree session via SandboxManager.
  No raw unrestricted host subprocesses are spawned.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from backend.agent.tools.contracts import AgentToolContext, ToolDefinition
from backend.services.sandbox_manager import sandbox_manager


def handle_detect_commands(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    """Detects available runners and build tools in the repository/worktree."""
    target_dir = Path(context.worktree_path) if context.worktree_path else Path("data/repos") / context.repository_id
    detected: List[Dict[str, str]] = []

    if (target_dir / "pyproject.toml").exists() or (target_dir / "setup.py").exists() or (target_dir / "requirements.txt").exists():
        detected.append({"tool": "pytest", "category": "test", "command": "uv run pytest"})
        detected.append({"tool": "python", "category": "runtime", "command": "python"})

    if (target_dir / "package.json").exists():
        detected.append({"tool": "npm", "category": "package_manager", "command": "npm test"})
        detected.append({"tool": "tsc", "category": "compiler", "command": "npx tsc --noEmit"})

    if (target_dir / "Cargo.toml").exists():
        detected.append({"tool": "cargo", "category": "build", "command": "cargo test"})

    return {"detected_commands": detected, "count": len(detected)}


def handle_execute_command(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    """Executes command inside the isolated worktree shell session via SandboxManager."""
    command = args["command"]
    timeout_sec = args.get("timeout_sec", 30)
    run_id = context.agent_run_id

    # Run async sandbox_manager.execute_command synchronously in threadpool
    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(
            sandbox_manager.execute_command(
                run_id=run_id,
                command=command,
                timeout_sec=timeout_sec,
                custom_worktree_path=context.worktree_path,
            )
        )
    finally:
        loop.close()

    return {
        "command": command,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "exit_code": res.exit_code,
        "duration_ms": res.duration_ms,
        "timed_out": res.timed_out,
        "cwd": res.cwd,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tool Definitions Catalog
# ──────────────────────────────────────────────────────────────────────────────

TERMINAL_TOOLS: List[ToolDefinition] = [
    ToolDefinition(
        name="detect_commands",
        description="Detect available test runners, compilers, and tools in the repository",
        category="terminal",
        input_schema={"type": "object", "properties": {}},
        handler=handle_detect_commands,
    ),
    ToolDefinition(
        name="execute_command",
        description="Execute a shell command inside the assigned isolated worktree session",
        category="terminal",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command line to execute"},
                "timeout_sec": {"type": "integer", "default": 30, "description": "Execution timeout in seconds"},
            },
            "required": ["command"],
        },
        default_timeout_sec=60.0,
        handler=handle_execute_command,
    ),
]
