from fastapi import APIRouter

from .core import core_router, import_router, list_repos
from .tasks import tasks_router
from .structure import structure_router
from .health import health_router
from .semantic import semantic_router
from .graph import graph_router
from .trace import trace_router
from .intelligence import intelligence_router
from .symbols import symbols_router
from .rim_comparison_v2 import rim_comparison_router
from .benchmark_pilot import benchmark_pilot_router

repo_router = APIRouter()
repo_router.add_api_route("", list_repos, methods=["GET"], tags=["repositories"])

repo_router.include_router(core_router)
repo_router.include_router(tasks_router)
repo_router.include_router(structure_router)
repo_router.include_router(health_router)
repo_router.include_router(semantic_router)
repo_router.include_router(graph_router)
repo_router.include_router(trace_router)
repo_router.include_router(intelligence_router)
repo_router.include_router(symbols_router)
repo_router.include_router(rim_comparison_router)
repo_router.include_router(benchmark_pilot_router)

__all__ = ["repo_router", "import_router"]
