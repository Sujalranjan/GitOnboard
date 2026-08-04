from fastapi import APIRouter

from .core import core_router, import_router, list_repos
from .tasks import tasks_router
from .structure import structure_router
from .health import health_router
from .semantic import semantic_router
from .graph import graph_router
from .trace import trace_router
from .intelligence import intelligence_router
from .services.models import get_or_build_model
from .services.analysis import get_latest_analysis, get_latest_analysis as _get_latest_analysis
from backend.dependencies.auth import get_current_user
from backend.database import get_db

repo_router = APIRouter()
repo_router.add_api_route("", list_repos, methods=["GET"])

repo_router.include_router(core_router)
repo_router.include_router(tasks_router)
repo_router.include_router(structure_router)
repo_router.include_router(health_router)
repo_router.include_router(semantic_router)
repo_router.include_router(graph_router)
repo_router.include_router(trace_router)
repo_router.include_router(intelligence_router)

__all__ = [
    "repo_router",
    "import_router",
    "get_or_build_model",
    "get_latest_analysis",
    "_get_latest_analysis",
    "get_current_user",
    "get_db",
]

