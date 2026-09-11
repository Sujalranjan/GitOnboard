from typing import Callable, Optional
from backend.services.qa_loop import QALoop, QALoopTurn, QALoopResult
from backend.services.tool_dispatch import ToolDispatchTable
from backend.services.qa_protocol import QAProtocolAdapter
from backend.intelligence.graph_traverser import GraphTraverser
from backend.intelligence.target_resolver import TargetResolver
from backend.repository_tools.tools import RepositoryTools
from backend.agent.loop.contracts import AgentLoopConfig


class LLMAnalysisService:
    """Shared service for LLM-based repository analysis.

    Used by both:
    - POST /api/repos/{repo}/llm/analyze/stream (standalone)
    - POST /api/repos/{repo}/rim-comparison/compare (baseline + with RIM)
    """

    def __init__(
        self,
        llm_service,
        tool_layer: RepositoryTools,
        graph_traverser: Optional[GraphTraverser] = None,
        target_resolver: Optional[TargetResolver] = None,
        model: str = "qwen3:4b-instruct",
        config: Optional[AgentLoopConfig] = None,
        rim_metadata_block: Optional[str] = None,
        on_turn_callback: Optional[Callable[[QALoopTurn], None]] = None,
        structured_logger=None,
        request_id: Optional[str] = None,
        repository: Optional[str] = None,
        mode: Optional[str] = None,
    ):
        self.llm_service = llm_service
        self.tool_layer = tool_layer
        self.graph_traverser = graph_traverser
        self.target_resolver = target_resolver
        self.model = model
        self.config = config
        self.rim_metadata_block = rim_metadata_block
        self.on_turn_callback = on_turn_callback
        self.structured_logger = structured_logger
        self.request_id = request_id
        self.repository = repository
        self.mode = mode

    async def run(self, query: str, include_rim: bool = True) -> QALoopResult:
        """Run LLM analysis on the repository.

        Args:
            query: User question
            include_rim: Whether to enable RIM comparison tools

        Returns:
            QALoopResult with answer and metadata
        """
        # Create tool dispatch
        tool_dispatch = ToolDispatchTable(
            self.tool_layer,
            self.graph_traverser if include_rim else None,
            self.target_resolver if include_rim else None,
        )

        # Build system prompt
        protocol = QAProtocolAdapter(model_id=self.model)
        prompt_parts = protocol.build_system_prompt(
            tool_specs=tool_dispatch.specs(include_rim=include_rim),
            rim_metadata_block=self.rim_metadata_block if include_rim else None,
        )

        # Run analysis
        loop = QALoop(
            llm_service=self.llm_service,
            tool_dispatch=tool_dispatch,
            system_prompt_parts=prompt_parts,
            model=self.model,
            config=self.config,
            on_turn=self.on_turn_callback,
            structured_logger=self.structured_logger,
            request_id=self.request_id,
            repository=self.repository,
            mode=self.mode,
        )

        return await loop.run(query)
