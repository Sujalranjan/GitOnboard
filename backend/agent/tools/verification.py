"""
Verification Tools: Thin adapters delegating to StaticVerifier, DynamicVerifier, ContractVerifier, and Judge.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from backend.agent.tools.contracts import AgentToolContext, ToolDefinition
from backend.services.git_manager import GitManager
from backend.verification.contract_verifier import ContractVerifier
from backend.verification.dynamic_verifier import DynamicVerifier
from backend.verification.judge import Judge
from backend.verification.static_verifier import StaticVerifier


def _get_modified_and_diff(context: AgentToolContext) -> tuple[List[str], str]:
    if not context.worktree_path or not Path(context.worktree_path).exists():
        return [], ""
    gm = GitManager(base_worktree_dir=Path(context.worktree_path).parent)
    modified = gm.list_modified_files(worktree_path=context.worktree_path)
    diff = gm.get_diff(worktree_path=context.worktree_path)
    return modified, diff


# ──────────────────────────────────────────────────────────────────────────────
# Tool Handlers
# ──────────────────────────────────────────────────────────────────────────────

def handle_verify_static(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    if not context.worktree_path:
        raise ValueError("Worktree path is required for static verification")

    wt_path = Path(context.worktree_path).resolve()
    modified, diff = _get_modified_and_diff(context)
    if not modified:
        target_files = args.get("files", [])
        modified = target_files

    verifier = StaticVerifier()
    res = verifier.verify(worktree_path=wt_path, modified_files=modified, git_diff=diff)
    return res.model_dump()


def handle_verify_dynamic(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    if not context.worktree_path:
        raise ValueError("Worktree path is required for dynamic verification")

    wt_path = Path(context.worktree_path).resolve()
    verifier = DynamicVerifier()
    timeout = args.get("timeout_sec", 60)
    res = verifier.verify(worktree_path=wt_path, timeout_sec=timeout)
    return res.model_dump()


def handle_verify_contract(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    if not context.worktree_path:
        raise ValueError("Worktree path is required for contract verification")

    contract_data = args.get("contract", {})
    if not contract_data:
        return {"passed": True, "defects": [], "message": "No contract criteria provided"}

    modified, diff = _get_modified_and_diff(context)
    verifier = ContractVerifier()
    res = verifier.verify(contract=contract_data, modified_files=modified, git_diff=diff)
    return res.model_dump()


def handle_get_verification_result(args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    if not context.worktree_path:
        raise ValueError("Worktree path is required for verification aggregation")

    wt_path = Path(context.worktree_path).resolve()
    modified, diff = _get_modified_and_diff(context)

    static_res = StaticVerifier().verify(worktree_path=wt_path, modified_files=modified, git_diff=diff)
    dynamic_res = DynamicVerifier().verify(worktree_path=wt_path, timeout_sec=60)

    contract_data = args.get("contract", {})
    contract_res = ContractVerifier().verify(contract=contract_data, modified_files=modified, git_diff=diff) if contract_data else None

    judge = Judge()
    report = judge.aggregate(
        run_id=context.agent_run_id,
        static_result=static_res,
        dynamic_result=dynamic_res,
        contract_result=contract_res,
    )
    return report.model_dump()


# ──────────────────────────────────────────────────────────────────────────────
# Tool Definitions Catalog
# ──────────────────────────────────────────────────────────────────────────────

VERIFICATION_TOOLS: List[ToolDefinition] = [
    ToolDefinition(
        name="verify_static",
        description="Run static AST, phantom symbol, and import integrity checks on worktree files",
        category="verification",
        input_schema={
            "type": "object",
            "properties": {
                "files": {"type": "array", "items": {"type": "string"}, "description": "Optional list of files to verify"},
            },
        },
        handler=handle_verify_static,
    ),
    ToolDefinition(
        name="verify_dynamic",
        description="Execute dynamic test suite (pytest/npm) inside the worktree sandbox",
        category="verification",
        input_schema={
            "type": "object",
            "properties": {
                "timeout_sec": {"type": "integer", "default": 60},
            },
        },
        default_timeout_sec=120.0,
        handler=handle_verify_dynamic,
    ),
    ToolDefinition(
        name="verify_contract",
        description="Verify implementation against acceptance criteria and schema invariants",
        category="verification",
        input_schema={
            "type": "object",
            "properties": {
                "contract": {"type": "object", "description": "ImplementationContract definition"},
            },
        },
        handler=handle_verify_contract,
    ),
    ToolDefinition(
        name="get_verification_result",
        description="Aggregate multi-vector verification report and compute final verdict",
        category="verification",
        input_schema={
            "type": "object",
            "properties": {
                "contract": {"type": "object", "description": "Optional contract definition"},
            },
        },
        default_timeout_sec=180.0,
        handler=handle_get_verification_result,
    ),
]
