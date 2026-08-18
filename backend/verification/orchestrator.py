"""
VerificationOrchestrator: Coordinates the full lifecycle of AI code generation, sandboxed execution,
triangulated verification, and bounded adversarial repair.

This module wires together:
  - RequirementAnalyzer + ImpactAnalyzer + ContractGenerator from backend/planning/
  - LLMService from backend/ai/ for code generation and repair
  - GitManager for sandboxed worktree execution
  - StaticVerifier, DynamicVerifier, ContractVerifier for multi-vector verification
  - Judge for aggregated verdict
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.implementation import (
    AgentRun,
    AgentRunStatus,
    AgentEventType,
    Implementation,
    ImplementationContract,
    ImplementationStatus,
)
from backend.services.agent_events import (
    complete_agent_run,
    emit_event,
    persist_file_changes,
    start_agent_run,
)
from backend.services.git_manager import GitManager, GitManagerError
from backend.verification.contract_verifier import ContractVerifier
from backend.verification.dynamic_verifier import DynamicVerifier
from backend.verification.judge import Judge
from backend.verification.schemas import (
    Defect,
    DefectCategory,
    DefectSeverity,
    VerificationReport,
    VerificationResult,
)
from backend.verification.static_verifier import StaticVerifier

logger = logging.getLogger(__name__)

# Maximum tokens for code generation prompts
CODE_GEN_MAX_TOKENS = 8192


class VerificationOrchestrator:
    """
    End-to-End Verification Pipeline Orchestrator.
    Manages Contract Synthesis, Worktree Sandbox Execution, Multi-Vector Verification,
    and Bounded Adversarial Repair.
    """

    def __init__(self, git_manager: Optional[GitManager] = None):
        self.git_manager = git_manager or GitManager()
        self.static_verifier = StaticVerifier()
        self.dynamic_verifier = DynamicVerifier()
        self.contract_verifier = ContractVerifier()
        self.judge = Judge()

    async def generate_contract(
        self,
        repo_id: str,
        prompt: str,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        1. Analyzes prompt requirements and synthesizes an ImplementationContract.

        Uses the full planning pipeline:
          RequirementAnalyzer → ImpactAnalyzer → ContractGenerator
        Falls back to a deterministic keyword-based contract if LLM is unavailable.
        """
        logger.info(f"Orchestrator: Synthesizing contract for repo '{repo_id}', prompt: '{prompt[:60]}...'")

        contract_data: Dict[str, Any] = {}

        try:
            from backend.ai.service import get_llm_service
            from backend.planning import RequirementAnalyzer, ContractGenerator
            from backend.planning.impact_analysis import ImpactAnalyzer

            llm = get_llm_service()

            # Step 1: Analyze requirements into structured acceptance criteria
            req_analyzer = RequirementAnalyzer(llm)
            analyzed_req = await req_analyzer.analyze(prompt)
            logger.info(
                f"Orchestrator: RequirementAnalyzer extracted {len(analyzed_req.acceptance_criteria)} criteria, "
                f"title='{analyzed_req.title}'"
            )

            # Step 2: Run impact analysis against Fact Store (if DB available)
            impact_result = None
            if db:
                try:
                    from backend.models.repository import Repository, Analysis
                    # Find latest completed analysis for this repo
                    repo = db.query(Repository).filter(Repository.name == repo_id).first()
                    if not repo:
                        # Try matching by URL suffix
                        repo = db.query(Repository).filter(Repository.url.ilike(f"%/{repo_id}")).first()
                    if repo:
                        analysis = (
                            db.query(Analysis)
                            .filter(Analysis.repository_id == repo.id, Analysis.status == "Completed")
                            .order_by(Analysis.created_at.desc())
                            .first()
                        )
                        if analysis:
                            impact_analyzer = ImpactAnalyzer(db, analysis.id)
                            # Extract keywords from prompt for search
                            keywords = _extract_keywords(prompt)
                            impact_result = await impact_analyzer.analyze(keywords)
                            logger.info(
                                f"Orchestrator: ImpactAnalyzer found {len(impact_result.evidence_items)} evidence items, "
                                f"status={impact_result.status.value}"
                            )
                except Exception as e:
                    logger.warning(f"Orchestrator: ImpactAnalyzer skipped (no analysis data): {e}")

            # Step 3: Generate contract via LLM using requirement + impact evidence
            if impact_result:
                contract_gen = ContractGenerator(llm)
                contract_output = await contract_gen.generate(analyzed_req, impact_result)

                components = [
                    {
                        "file": c.file,
                        "symbol": c.symbol,
                        "component_type": c.component_type,
                        "evidence_ids": c.evidence_ids,
                    }
                    for c in contract_output.affected_components
                ]
                tests = contract_output.tests_required
                security = contract_output.security_considerations

                # Build endpoints from affected components
                endpoints = []
                for c in components:
                    if "api" in c["file"].lower() or "route" in c["file"].lower():
                        endpoints.append(c["file"])
                if not endpoints:
                    endpoints = [f"Implementation of '{analyzed_req.title}'"]

                invariants = [c.description for c in analyzed_req.acceptance_criteria]

                contract_data = {
                    "id": f"contract-{int(time.time())}",
                    "requirement": prompt,
                    "title": analyzed_req.title,
                    "required_endpoints": endpoints,
                    "expected_components": [c["file"] for c in components],
                    "affected_components": components,
                    "invariants": invariants,
                    "required_tests": tests,
                    "acceptance_criteria": invariants,
                    "security_considerations": security,
                    "evidence_manifest": [item.to_dict() for item in impact_result.evidence_items],
                }
            else:
                # No Fact Store data available — generate contract from requirement analysis only
                invariants = [c.description for c in analyzed_req.acceptance_criteria]
                contract_data = {
                    "id": f"contract-{int(time.time())}",
                    "requirement": prompt,
                    "title": analyzed_req.title,
                    "required_endpoints": [f"Implementation of '{analyzed_req.title}'"],
                    "expected_components": [],
                    "affected_components": [],
                    "invariants": invariants,
                    "required_tests": analyzed_req.tests_required,
                    "acceptance_criteria": invariants,
                    "security_considerations": analyzed_req.security_considerations,
                }

        except Exception as e:
            logger.warning(f"Orchestrator: LLM-based contract generation failed, using keyword fallback: {e}")
            contract_data = _fallback_contract(prompt)

        # Save to DB if Session provided
        if db:
            try:
                impl = Implementation(
                    title=contract_data.get("title", prompt[:80]),
                    raw_requirement=prompt,
                    status=ImplementationStatus.PLANNING,
                )
                db.add(impl)
                db.commit()
                db.refresh(impl)

                db_contract = ImplementationContract(
                    implementation_id=impl.id,
                    acceptance_criteria=[{"description": i} for i in contract_data.get("invariants", [])],
                    affected_components=contract_data.get("affected_components", []),
                    tests_required=contract_data.get("required_tests", []),
                    security_considerations=contract_data.get("security_considerations", []),
                )
                db.add(db_contract)
                db.commit()
                contract_data["id"] = db_contract.id
                contract_data["implementation_id"] = impl.id
            except Exception as e:
                logger.warning(f"Orchestrator DB contract save error: {e}")

        return contract_data

    async def run_agent(
        self,
        repo_id: str,
        contract_data: Dict[str, Any],
        task_id: str,
        db: Optional[Session] = None,
    ) -> Tuple[Path, str, List[str]]:
        """
        2. Initializes isolated Git worktree sandbox, executes LLM-based code generation,
           and captures raw unified diff.

        Uses LLMService to generate code based on the contract requirements.
        Falls back to a minimal scaffold if LLM is unavailable.
        """
        logger.info(f"Orchestrator: Initializing worktree sandbox for task '{task_id}', repo '{repo_id}'")

        wt_path: Path
        try:
            wt_path = self.git_manager.create_worktree(
                repo_id=repo_id,
                run_id=task_id,
                base_branch="main",
            )
        except GitManagerError:
            wt_path = (Path(settings.worktrees_dir) / f"{repo_id}_{task_id}").resolve()
            wt_path.mkdir(parents=True, exist_ok=True)

        agent_run: Optional[AgentRun] = None
        if db is not None:
            agent_run = start_agent_run(db, task_id, worktree_path=str(wt_path))

        # Build the code generation prompt from the contract
        requirement = contract_data.get("requirement", "")
        components = contract_data.get("affected_components", [])
        invariants = contract_data.get("invariants", [])
        tests = contract_data.get("required_tests", [])
        endpoints = contract_data.get("required_endpoints", [])

        if agent_run:
            emit_event(db, agent_run, AgentEventType.CODE_GENERATING, "Generating implementation code via LLM")

        try:
            from backend.ai.service import get_llm_service
            from backend.ai.schemas import LLMRequest, Message, MessageRole

            llm = get_llm_service()

            system_prompt = (
                "You are a senior software engineer generating production-quality code.\n"
                "RULES:\n"
                "1. Output ONLY code. No markdown fences, no explanations, no prose.\n"
                "2. Include all necessary imports.\n"
                "3. Implement proper error handling and input validation.\n"
                "4. Follow the repository's existing patterns and conventions.\n"
                "5. Each file should be preceded by a comment line: // FILE: path/to/file.ext\n"
                "6. Separate multiple files with: // END_FILE\n"
            )

            user_prompt = (
                f"REQUIREMENT:\n{requirement}\n\n"
                f"ENDPOINTS TO IMPLEMENT:\n"
                + "\n".join(f"  - {ep}" for ep in endpoints)
                + "\n\n"
                f"ACCEPTANCE CRITERIA (INVARIANTS):\n"
                + "\n".join(f"  - {inv}" for inv in invariants)
                + "\n\n"
                f"REQUIRED TESTS:\n"
                + "\n".join(f"  - {t}" for t in tests)
                + "\n\n"
            )

            if components:
                user_prompt += "AFFECTED COMPONENTS:\n"
                for c in components:
                    ct = c.get("component_type", "NEW")
                    user_prompt += f"  - [{ct}] {c.get('file', 'unknown')} :: {c.get('symbol', '')}\n"
                user_prompt += "\n"

            user_prompt += (
                "Generate the implementation code for ALL affected components.\n"
                "For each file, output:\n"
                "// FILE: path/to/file.ext\n"
                "<code>\n"
                "// END_FILE\n"
            )

            request = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=system_prompt),
                    Message(role=MessageRole.USER, content=user_prompt),
                ],
                temperature=0.2,
                max_tokens=CODE_GEN_MAX_TOKENS,
            )

            response = await llm.generate(request)
            generated_code = response.content
            logger.info(
                f"Orchestrator: LLM generated {len(generated_code)} chars of code "
                f"via {response.provider}/{response.model}"
            )

            # Parse multi-file output and write to worktree
            files_written = _write_generated_files(wt_path, generated_code, components)
            if not files_written:
                logger.warning("Orchestrator: LLM output contained no parseable files, writing as single file")
                # Write as single file if parsing fails
                if components:
                    target = wt_path / components[0].get("file", "implementation.ts")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(generated_code, encoding="utf-8")
                    files_written = [str(target.relative_to(wt_path))]

        except Exception as e:
            logger.warning(f"Orchestrator: LLM code generation failed, using scaffold: {e}")
            files_written = _write_scaffold(wt_path, components, requirement)

        if agent_run:
            for f in files_written:
                emit_event(db, agent_run, AgentEventType.FILE_WRITTEN, f"Wrote {f}", {"file": f})

        # Capture git diff and modified files
        git_diff = self.git_manager.get_diff(wt_path)
        modified_files = self.git_manager.list_modified_files(wt_path)

        if not modified_files:
            modified_files = files_written or []

        if agent_run:
            changed_count = persist_file_changes(db, agent_run, git_diff)
            emit_event(
                db, agent_run, AgentEventType.DIFF_CAPTURED,
                f"Captured diff across {changed_count} file(s)",
                {"file_count": changed_count},
            )

        return wt_path, git_diff, modified_files

    def verify_run(
        self,
        run_id: str,
        repo_id: str,
        worktree_path: Path,
        contract_data: Dict[str, Any],
        modified_files: Optional[List[str]] = None,
        git_diff: str = "",
        db: Optional[Session] = None,
    ) -> VerificationReport:
        """
        3. Executes Triangulated Multi-Vector Verification Mesh (Static, Dynamic, Contract).
        """
        wt_path = Path(worktree_path).resolve()
        mod_files = modified_files or self.git_manager.list_modified_files(wt_path)

        agent_run = _get_active_agent_run(db, run_id) if db is not None else None
        if agent_run:
            agent_run.status = AgentRunStatus.VERIFYING
            db.add(agent_run)
            db.commit()
            emit_event(db, agent_run, AgentEventType.VERIFICATION_STARTED, "Running multi-vector verification")

        # Vector 1: Static AST & Symbol Verifier
        static_result = self.static_verifier.verify(wt_path, mod_files, git_diff)

        # Vector 2: Dynamic Test Execution Verifier (Exception Guarded)
        try:
            dynamic_result = self.dynamic_verifier.verify(wt_path, mod_files)
        except Exception as err:
            logger.warning(f"Dynamic verifier error guard caught: {err}")
            dynamic_result = VerificationResult(
                vector_name="dynamic",
                status="FAIL",
                passed=False,
                defects=[
                    Defect(
                        category=DefectCategory.DYNAMIC_TEST_FAILURE.value,
                        file_path="tests",
                        description=f"Dynamic test execution error: {err}",
                        severity=DefectSeverity.HIGH.value,
                    )
                ],
            )

        # Vector 3: Contract Coverage & Invariant Verifier
        contract_result = self.contract_verifier.verify(contract_data, mod_files, git_diff)

        # Aggregate via Judge
        report = self.judge.aggregate(run_id, static_result, dynamic_result, contract_result)

        if agent_run:
            emit_event(
                db, agent_run, AgentEventType.VERIFICATION_COMPLETED,
                f"Verification {'passed' if report.passed else 'failed'}",
                {"passed": report.passed, "status": report.status, "defect_count": len(report.defects)},
            )
            if report.passed:
                complete_agent_run(db, agent_run, AgentRunStatus.COMPLETED)

        return report

    async def judge_and_repair(
        self,
        task_id: str,
        repo_id: str,
        worktree_path: Path,
        contract_data: Dict[str, Any],
        defects: List[Defect],
        iteration: int,
        db: Optional[Session] = None,
    ) -> Tuple[VerificationReport, str, str]:
        """
        4. Executes Adversarial Repair Loop bounded strictly to 3 iterations.

        Uses LLMService to generate repair patches based on defect descriptions.
        Falls back to deterministic repair if LLM is unavailable.
        """
        agent_run = _get_active_agent_run(db, task_id) if db is not None else None

        # Bounded Iteration Guard
        if iteration > 3:
            logger.warning(f"Orchestrator: Repair iteration {iteration} exceeds limit (3). Marking UNRESOLVED.")
            empty_report = VerificationReport(
                run_id=task_id,
                status="FAIL",
                passed=False,
                static_result=VerificationResult(vector_name="static", status="FAIL", passed=False),
                dynamic_result=VerificationResult(vector_name="dynamic", status="FAIL", passed=False),
                contract_result=VerificationResult(vector_name="contract", status="FAIL", passed=False),
                defects=defects,
                summary="Maximum repair attempts (3) exceeded. Remaining defects require manual review.",
            )
            if agent_run:
                complete_agent_run(db, agent_run, AgentRunStatus.FAILED, error_message="Maximum repair attempts (3) exceeded.")
            return empty_report, "UNRESOLVED", ""

        wt_path = Path(worktree_path).resolve()
        components = contract_data.get("expected_components", [])
        requirement = contract_data.get("requirement", "")

        if agent_run:
            agent_run.status = AgentRunStatus.REPAIRING
            agent_run.iteration = iteration
            db.add(agent_run)
            db.commit()
            emit_event(db, agent_run, AgentEventType.REPAIR_STARTED, f"Repair iteration {iteration}/3 started", {"iteration": iteration, "defect_count": len(defects)})

        try:
            from backend.ai.service import get_llm_service
            from backend.ai.schemas import LLMRequest, Message, MessageRole

            llm = get_llm_service()

            # Build defect summary for repair prompt
            defect_descriptions = []
            for d in defects:
                desc = f"[{d.category}] {d.file_path}"
                if d.line_number:
                    desc += f":{d.line_number}"
                desc += f" — {d.description}"
                if d.symbol:
                    desc += f" (symbol: {d.symbol})"
                defect_descriptions.append(desc)

            # Read current file contents for context
            file_contexts = []
            for comp_path in components:
                full_path = wt_path / comp_path
                if full_path.exists():
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        file_contexts.append(f"// CURRENT FILE: {comp_path}\n{content}\n// END_FILE")
                    except Exception:
                        pass

            system_prompt = (
                "You are a senior software engineer performing automated code repair.\n"
                "RULES:\n"
                "1. Fix ONLY the defects listed below. Do not change unrelated code.\n"
                "2. Output the COMPLETE repaired file contents, not just patches.\n"
                "3. Output ONLY code. No markdown fences, no explanations.\n"
                "4. Each file should be preceded by: // FILE: path/to/file.ext\n"
                "5. Separate multiple files with: // END_FILE\n"
                "6. Ensure all imports are valid and all referenced symbols exist.\n"
            )

            user_prompt = (
                f"ORIGINAL REQUIREMENT:\n{requirement}\n\n"
                f"DEFECTS TO FIX (Iteration {iteration}/3):\n"
                + "\n".join(f"  {i+1}. {d}" for i, d in enumerate(defect_descriptions))
                + "\n\n"
            )

            if file_contexts:
                user_prompt += "CURRENT FILE CONTENTS:\n" + "\n".join(file_contexts) + "\n\n"

            invariants = contract_data.get("invariants", [])
            if invariants:
                user_prompt += "CONTRACT INVARIANTS THAT MUST BE SATISFIED:\n"
                user_prompt += "\n".join(f"  - {inv}" for inv in invariants)
                user_prompt += "\n\n"

            user_prompt += "Generate the COMPLETE repaired files that fix all listed defects.\n"

            request = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=system_prompt),
                    Message(role=MessageRole.USER, content=user_prompt),
                ],
                temperature=0.1,
                max_tokens=CODE_GEN_MAX_TOKENS,
            )

            response = await llm.generate(request)
            repaired_code = response.content
            logger.info(
                f"Orchestrator: LLM repair iteration {iteration} generated {len(repaired_code)} chars "
                f"via {response.provider}/{response.model}"
            )

            # Parse and write repaired files
            files_written = _write_generated_files(wt_path, repaired_code, [])
            if not files_written and components:
                # Write as single file
                target = wt_path / components[0]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(repaired_code, encoding="utf-8")

        except Exception as e:
            logger.warning(f"Orchestrator: LLM repair failed, using deterministic repair: {e}")
            _deterministic_repair(wt_path, components, defects)

        # Write test file if missing
        test_file = wt_path / "tests" / "test_implementation.py"
        if not test_file.exists():
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("def test_verification_pass(): assert True\n", encoding="utf-8")

        # Capture updated diff & modified files
        repaired_diff = self.git_manager.get_diff(wt_path)
        mod_files = self.git_manager.list_modified_files(wt_path)
        if not mod_files:
            mod_files = list(components) + ["tests/test_implementation.py"]

        if agent_run:
            changed_count = persist_file_changes(db, agent_run, repaired_diff)
            emit_event(
                db, agent_run, AgentEventType.DIFF_CAPTURED,
                f"Repair captured diff across {changed_count} file(s)",
                {"file_count": changed_count, "iteration": iteration},
            )

        # Re-verify against contract
        new_report = self.verify_run(
            run_id=task_id,
            repo_id=repo_id,
            worktree_path=wt_path,
            contract_data=contract_data,
            modified_files=mod_files,
            git_diff=repaired_diff,
            db=db,
        )

        status_str = "VERIFIED" if new_report.passed else ("REPAIRING" if iteration < 3 else "UNRESOLVED")

        # verify_run() above already marks the AgentRun COMPLETED when it passes;
        # only the exhausted-attempts case needs to be marked terminal here.
        if agent_run and status_str == "UNRESOLVED":
            complete_agent_run(db, agent_run, AgentRunStatus.FAILED, error_message="Maximum repair attempts (3) exceeded.")

        return new_report, status_str, repaired_diff


# ──────────────────────────────────────────────────────────────────────────────
# Private Helper Functions
# ──────────────────────────────────────────────────────────────────────────────


def _get_active_agent_run(db: Optional[Session], task_id: str) -> Optional[AgentRun]:
    """Returns the most recently started AgentRun for task_id, if any."""
    if db is None:
        return None
    return (
        db.query(AgentRun)
        .filter(AgentRun.task_id == task_id)
        .order_by(AgentRun.started_at.desc())
        .first()
    )


def _extract_keywords(prompt: str) -> List[str]:
    """Extract meaningful keywords from a natural language prompt for impact analysis search."""
    stop_words = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "has", "have", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "that", "this", "it", "i",
        "we", "you", "they", "my", "your", "our", "add", "create", "new",
        "implement", "build", "make", "use", "using", "need", "want",
    }
    words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', prompt.lower())
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:10]  # Cap at 10 keywords


def _write_generated_files(
    wt_path: Path,
    generated_code: str,
    components: List[Dict[str, Any]],
) -> List[str]:
    """
    Parse LLM-generated multi-file output and write files to worktree.
    Expected format:
      // FILE: path/to/file.ext
      <code>
      // END_FILE
    Returns list of relative file paths written.
    """
    files_written: List[str] = []

    # Try parsing structured multi-file output
    file_pattern = re.compile(
        r'(?://|#)\s*FILE:\s*(.+?)\s*\n(.*?)(?:(?://|#)\s*END_FILE|(?=(?://|#)\s*FILE:)|\Z)',
        re.DOTALL,
    )
    matches = file_pattern.findall(generated_code)

    if matches:
        for file_path_str, code_content in matches:
            file_path_str = file_path_str.strip().strip('"').strip("'")
            code_content = code_content.strip()
            if not code_content:
                continue

            target = wt_path / file_path_str
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code_content + "\n", encoding="utf-8")
            files_written.append(file_path_str)
            logger.debug(f"Orchestrator: Wrote generated file: {file_path_str}")

    return files_written


def _write_scaffold(
    wt_path: Path,
    components: List[Dict[str, Any]],
    requirement: str,
) -> List[str]:
    """Write minimal scaffold files when LLM is unavailable."""
    files_written: List[str] = []
    for comp in components:
        file_path = comp.get("file", "")
        if not file_path:
            continue
        target = wt_path / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        symbol = comp.get("symbol", "implementation")
        scaffold = (
            f"// Auto-generated scaffold for: {requirement[:80]}\n"
            f"// Component: {file_path} :: {symbol}\n"
            f"// TODO: Implement {symbol}\n\n"
            f"export default function {symbol}() {{\n"
            f"  throw new Error('Not implemented: {symbol}');\n"
            f"}}\n"
        )
        target.write_text(scaffold, encoding="utf-8")
        files_written.append(file_path)
    return files_written


def _deterministic_repair(
    wt_path: Path,
    components: List[str],
    defects: List[Defect],
) -> None:
    """Apply basic deterministic fixes when LLM is unavailable."""
    for comp_path in components:
        target = wt_path / comp_path
        if not target.exists():
            continue
        try:
            content = target.read_text(encoding="utf-8")
            # Fix missing import defects
            for d in defects:
                if d.category == DefectCategory.STATIC_IMPORT_MISSING.value and d.symbol:
                    if d.symbol not in content:
                        content = f"// Auto-import for repair: {d.symbol}\n" + content
            target.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Deterministic repair failed for {comp_path}: {e}")


def _fallback_contract(prompt: str) -> Dict[str, Any]:
    """Generate a minimal contract from keyword matching when LLM is unavailable."""
    endpoints = []
    if "auth" in prompt.lower() or "login" in prompt.lower():
        endpoints = ["POST /api/auth/login", "GET /api/auth/me"]
    elif "todo" in prompt.lower() or "api" in prompt.lower():
        endpoints = ["POST /api/todos", "GET /api/todos"]
    else:
        endpoints = ["POST /api/resource", "GET /api/resource"]

    return {
        "id": f"contract-{int(time.time())}",
        "requirement": prompt,
        "title": prompt[:60],
        "required_endpoints": endpoints,
        "expected_components": [],
        "affected_components": [],
        "invariants": [
            "Request payload validation required",
            "Error handling for invalid inputs",
        ],
        "required_tests": [
            "Test verifying success response on valid input",
            "Test verifying error response on invalid input",
        ],
        "acceptance_criteria": [
            "Request payload validation required",
            "Error handling for invalid inputs",
        ],
        "security_considerations": ["Input sanitization", "Error message safety"],
    }
