"""
Git Tools: Thin adapters for worktree status, diffs, checkpoints, and rollbacks via GitManager.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from backend.agent.tools.contracts import AgentToolContext, ToolDefinition
from backend.services.git_manager import GitManager


def _get_git_manager(context: AgentToolContext) -> tuple[GitManager, Path]:
    if not context.worktree_path:
        raise ValueError("Worktree path is not configured in AgentToolContext")
    wt_path = Path(context.worktree_path).resolve()
    if not wt_path.exists():
        raise FileNotFoundError(f"Worktree path '{wt_path}' does not exist on disk")
    gm = GitManager(base_worktree_dir=wt_path.parent)
    return gm, wt_path


# ──────────────────────────────────────────────────────────────────────────────
# Tool Handlers
# ──────────────────────────────────────────────────────────────────────────────

def handle_get_status(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    gm, wt_path = _get_git_manager(context)
    modified = gm.list_modified_files(worktree_path=wt_path)

    # Run git status porcelain for status flags
    res = subprocess.run(["git", "status", "--porcelain"], cwd=wt_path, capture_output=True, text=True)
    status_output = res.stdout.strip()

    return {
        "modified_files": modified,
        "is_clean": len(modified) == 0,
        "porcelain_output": status_output,
    }


def handle_get_diff(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    gm, wt_path = _get_git_manager(context)
    base_branch = args.get("base_branch", "main")
    diff_text = gm.get_diff(worktree_path=wt_path, base_branch=base_branch)
    modified = gm.list_modified_files(worktree_path=wt_path, base_branch=base_branch)

    return {
        "base_branch": base_branch,
        "diff": diff_text,
        "modified_files": modified,
        "file_count": len(modified),
    }


def handle_create_checkpoint(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    gm, wt_path = _get_git_manager(context)
    message = args.get("message", "Agent sandbox checkpoint")

    # Add all changes and commit
    subprocess.run(["git", "add", "."], cwd=wt_path, capture_output=True, check=True)
    res = subprocess.run(
        ["git", "commit", "-m", f"[CHECKPOINT] {message}", "--allow-empty"],
        cwd=wt_path,
        capture_output=True,
        text=True,
    )
    commit_sha_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt_path, capture_output=True, text=True)
    commit_sha = commit_sha_res.stdout.strip()

    return {"checkpoint_created": True, "commit_sha": commit_sha, "message": message}


def handle_rollback(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    gm, wt_path = _get_git_manager(context)
    target_ref = args.get("target_ref", "HEAD~1")

    # Reset hard to target commit
    subprocess.run(["git", "reset", "--hard", target_ref], cwd=wt_path, capture_output=True, check=True)
    subprocess.run(["git", "clean", "-fd"], cwd=wt_path, capture_output=True, check=True)

    commit_sha_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt_path, capture_output=True, text=True)
    current_sha = commit_sha_res.stdout.strip()

    return {"rolled_back": True, "current_sha": current_sha, "target_ref": target_ref}


# ──────────────────────────────────────────────────────────────────────────────
# Tool Definitions Catalog
# ──────────────────────────────────────────────────────────────────────────────

GIT_TOOLS: List[ToolDefinition] = [
    ToolDefinition(
        name="git_status",
        description="Get current status and list of modified/untracked files in the worktree",
        category="git",
        input_schema={"type": "object", "properties": {}},
        handler=handle_get_status,
    ),
    ToolDefinition(
        name="git_diff",
        description="Get unified git diff of worktree against base branch or HEAD",
        category="git",
        input_schema={
            "type": "object",
            "properties": {
                "base_branch": {"type": "string", "default": "main"},
            },
        },
        handler=handle_get_diff,
    ),
    ToolDefinition(
        name="create_checkpoint",
        description="Commit worktree changes as a recoverable checkpoint",
        category="git",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "default": "Agent checkpoint"},
            },
        },
        handler=handle_create_checkpoint,
    ),
    ToolDefinition(
        name="rollback",
        description="Roll back worktree changes to a previous checkpoint commit",
        category="git",
        input_schema={
            "type": "object",
            "properties": {
                "target_ref": {"type": "string", "default": "HEAD~1"},
            },
        },
        handler=handle_rollback,
    ),
]
