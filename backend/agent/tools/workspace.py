"""
Workspace Tools: Thin adapters for isolated file and patch operations inside Git worktrees.

Isolation Guard:
  All file operations are strictly verified to reside within context.worktree_path.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from backend.agent.tools.contracts import AgentToolContext, ToolDefinition
from backend.services.git_manager import GitManager


def _resolve_worktree_file(context: AgentToolContext, relative_path: str) -> Path:
    """
    Resolves relative path inside assigned worktree and strictly validates
    that the resolved path does not escape the worktree root.
    """
    if not context.worktree_path:
        raise ValueError("Worktree path is not configured in AgentToolContext")

    wt_root = Path(context.worktree_path).resolve()
    if not wt_root.exists():
        wt_root.mkdir(parents=True, exist_ok=True)

    target = (wt_root / relative_path).resolve()

    # Isolation guard
    try:
        target.relative_to(wt_root)
    except ValueError as err:
        raise ValueError(f"Path '{relative_path}' escapes worktree boundary '{wt_root}'") from err

    return target


# ──────────────────────────────────────────────────────────────────────────────
# Tool Handlers
# ──────────────────────────────────────────────────────────────────────────────

def handle_create_file(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    rel_path = args["path"]
    content = args.get("content", "")
    target_path = _resolve_worktree_file(context, rel_path)

    if target_path.exists() and not args.get("overwrite", False):
        raise FileExistsError(f"File '{rel_path}' already exists; set overwrite=True to replace")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    byte_count = target_path.stat().st_size

    return {"path": rel_path, "bytes_written": byte_count, "created": True}


def handle_modify_file(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    rel_path = args["path"]
    content = args["content"]
    target_path = _resolve_worktree_file(context, rel_path)

    if not target_path.exists():
        raise FileNotFoundError(f"File '{rel_path}' does not exist in worktree")

    target_path.write_text(content, encoding="utf-8")
    byte_count = target_path.stat().st_size

    return {"path": rel_path, "bytes_written": byte_count, "modified": True}


def handle_apply_patch(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    if not context.worktree_path:
        raise ValueError("Worktree path is not configured in context")

    patch_text = args["patch_text"]
    gm = GitManager(base_worktree_dir=Path(context.worktree_path).parent)
    success = gm.apply_patch(worktree_path=context.worktree_path, patch_text=patch_text)

    if not success:
        raise RuntimeError("git apply failed to apply unified patch to worktree")

    modified = gm.list_modified_files(worktree_path=context.worktree_path)
    return {"patch_applied": True, "modified_files": modified}


def handle_delete_file(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    rel_path = args["path"]
    target_path = _resolve_worktree_file(context, rel_path)

    if not target_path.exists():
        raise FileNotFoundError(f"File '{rel_path}' does not exist in worktree")

    target_path.unlink()
    return {"path": rel_path, "deleted": True}


def handle_get_diff(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    if not context.worktree_path:
        return {"diff": "", "modified_files": [], "message": "No worktree configured"}

    base_branch = args.get("base_branch", "main")
    gm = GitManager(base_worktree_dir=Path(context.worktree_path).parent)
    diff_text = gm.get_diff(worktree_path=context.worktree_path, base_branch=base_branch)
    modified = gm.list_modified_files(worktree_path=context.worktree_path, base_branch=base_branch)

    return {"diff": diff_text, "modified_files": modified, "file_count": len(modified)}


# ──────────────────────────────────────────────────────────────────────────────
# Tool Definitions Catalog
# ──────────────────────────────────────────────────────────────────────────────

WORKSPACE_TOOLS: List[ToolDefinition] = [
    ToolDefinition(
        name="create_file",
        description="Create a new file in the assigned isolated worktree",
        category="workspace",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path inside worktree"},
                "content": {"type": "string", "default": "", "description": "Initial file content"},
                "overwrite": {"type": "boolean", "default": False, "description": "Whether to overwrite if existing"},
            },
            "required": ["path"],
        },
        handler=handle_create_file,
    ),
    ToolDefinition(
        name="modify_file",
        description="Update file contents in the assigned isolated worktree",
        category="workspace",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path inside worktree"},
                "content": {"type": "string", "description": "Full new file content"},
            },
            "required": ["path", "content"],
        },
        handler=handle_modify_file,
    ),
    ToolDefinition(
        name="apply_patch",
        description="Apply a unified diff patch to the assigned worktree",
        category="workspace",
        input_schema={
            "type": "object",
            "properties": {
                "patch_text": {"type": "string", "description": "Unified diff patch string"},
            },
            "required": ["patch_text"],
        },
        handler=handle_apply_patch,
    ),
    ToolDefinition(
        name="delete_file",
        description="Delete a file from the assigned worktree",
        category="workspace",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path to delete"},
            },
            "required": ["path"],
        },
        handler=handle_delete_file,
    ),
    ToolDefinition(
        name="get_diff",
        description="Get current unified diff and modified file list from the worktree",
        category="workspace",
        input_schema={
            "type": "object",
            "properties": {
                "base_branch": {"type": "string", "default": "main", "description": "Base branch to compare against"},
            },
        },
        handler=handle_get_diff,
    ),
]
