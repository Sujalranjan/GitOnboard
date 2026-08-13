from typing import List, Dict, Set, Tuple
from backend.intelligence.capabilities.detectors.base import BaseCapabilityDetector
from backend.intelligence.capabilities.model import (
    CapabilityCategory,
    CapabilityMemberRole,
    CapabilityDetection,
)
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.enums import EntityType, RelationshipType

class BackgroundTaskDetector(BaseCapabilityDetector):
    """
    Detects background task execution (FastAPI BackgroundTasks, Celery @task, .delay(), worker routines).
    Explicitly excludes standard async def functions that do not invoke background task queues.
    """

    BACKGROUND_FUNC_KEYWORDS = {"backgroundtasks", "add_task", "delay", "apply_async", "enqueue", "shared_task", "celery"}
    DECORATOR_KEYWORDS = {"task", "shared_task", "background_task", "worker"}

    def detect(self, rim: RepositoryModel) -> List[CapabilityDetection]:
        detections: List[CapabilityDetection] = []
        seen_workers: Set[str] = set()

        # Build caller index
        callers_map: Dict[str, List[str]] = {}
        for rel in rim.relationships.values():
            if rel.type in (RelationshipType.CALLS, RelationshipType.USES):
                if rel.target_id not in callers_map:
                    callers_map[rel.target_id] = []
                callers_map[rel.target_id].append(rel.source_id)

        for entity in rim.entities.values():
            if entity.type not in (EntityType.FUNCTION, EntityType.METHOD, EntityType.BACKGROUND_JOB, EntityType.WORKER):
                continue

            name_lower = entity.name.lower()
            params = entity.metadata.get("parameters", [])
            param_types = [str(p).lower() for p in params] if isinstance(params, list) else []
            decorators = [str(d).lower() for d in entity.metadata.get("decorators", [])]

            # 1. FastAPI BackgroundTasks parameter check
            is_fastapi_bg = any("backgroundtasks" in p for p in param_types) or any("background_tasks" in p for p in param_types)
            
            # 2. Celery / Queue decorator check
            is_celery_task = any(any(kw in dec for kw in self.DECORATOR_KEYWORDS) for dec in decorators) or entity.type in (EntityType.BACKGROUND_JOB, EntityType.WORKER)

            # 3. Method invocation check (.add_task, .delay, .apply_async)
            calls_bg_method = any(kw in name_lower for kw in ("add_task", "delay", "apply_async", "enqueue_job"))

            rule_id = None
            task_name = None

            if is_fastapi_bg or calls_bg_method:
                rule_id = "BACKGROUND_FASTAPI_TASK"
                task_name = f"FastAPI Background Task: {entity.name}"
            elif is_celery_task:
                rule_id = "BACKGROUND_CELERY_TASK"
                task_name = f"Celery Task Worker: {entity.name}"
            elif "worker" in name_lower or "queue_processor" in name_lower:
                rule_id = "BACKGROUND_WORKER_ROUTINE"
                task_name = f"Background Worker Routine: {entity.name}"

            if rule_id and entity.id not in seen_workers:
                seen_workers.add(entity.id)
                members: List[Tuple[str, str]] = [(entity.id, CapabilityMemberRole.WORKER.value)]
                evidence = [{
                    "fact_type": "background_execution",
                    "symbol_id": entity.id,
                    "details": f"Rule {rule_id} matched on {entity.name} with decorators={decorators}, params={param_types}"
                }]

                # Add triggering callers as ENTRY_POINT if any
                for caller_id in callers_map.get(entity.id, []):
                    caller_ent = rim.entities.get(caller_id)
                    if caller_ent:
                        members.append((caller_id, CapabilityMemberRole.ENTRY_POINT.value))
                        evidence.append({
                            "fact_type": "background_trigger",
                            "symbol_id": caller_id,
                            "details": f"Triggered by caller {caller_ent.name}"
                        })

                detections.append(CapabilityDetection(
                    rule_id=rule_id,
                    category=CapabilityCategory.BACKGROUND_TASKS,
                    name=task_name,
                    members=members,
                    evidence=evidence,
                ))

        return detections
