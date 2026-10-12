"""
Unit tests for InvestigationStateStore.
"""
from backend.agent.investigation.schemas import (
    EvidenceCard,
    FindingType,
    SubtaskStatus,
    WorkerTaskResult,
)
from backend.agent.investigation.state_store import InvestigationStateStore


def test_investigation_state_store_task_lifecycle_and_dossier():
    store = InvestigationStateStore(investigation_id="inv_test_123")

    # 1. Create tasks with dependency
    t1 = store.create_task(
        task_id="t1",
        title="Find Auth Middleware",
        description="Search for authenticateToken",
    )
    t2 = store.create_task(
        task_id="t2",
        title="Verify Token Rotation",
        description="Inspect /refresh endpoint",
        dependencies=["t1"],
    )

    ready_tasks = store.get_ready_tasks()
    assert len(ready_tasks) == 1
    assert ready_tasks[0].id == "t1"

    # 2. Complete t1 via worker result
    worker_res = WorkerTaskResult(
        task_id="t1",
        status=SubtaskStatus.COMPLETED,
        files_inspected=["middleware/auth.js"],
        findings=[
            EvidenceCard(
                id="ev_1",
                task_id="t1",
                file_path="middleware/auth.js",
                line_start=15,
                line_end=40,
                symbol_name="authenticateToken",
                finding_type=FindingType.SOURCE_IMPLEMENTATION,
                summary="Extracts Bearer token from header",
                code_excerpt="const token = req.headers.authorization;",
            )
        ],
    )
    store.record_worker_result(worker_res)

    assert store.tasks["t1"].status == SubtaskStatus.COMPLETED
    assert "middleware/auth.js" in store.inspected_files

    # 3. Now t2 should be ready
    ready_tasks_after = store.get_ready_tasks()
    assert len(ready_tasks_after) == 1
    assert ready_tasks_after[0].id == "t2"

    # 4. Format dossier
    dossier = store.format_evidence_dossier()
    assert "middleware/auth.js (lines 15-40)" in dossier
    assert "authenticateToken" in dossier
    assert "Extracts Bearer token" in dossier
