from typing import Callable, Optional
from sqlalchemy.orm import Session
from backend.services.qa_loop import QALoop, QALoopTurn, QALoopResult
from backend.services.tool_dispatch import ToolDispatchTable, TargetEntityResolver
from backend.services.qa_protocol import QAProtocolAdapter
from backend.intelligence.retrieval.graph_traverser import FactStoreGraphTraverser
from backend.repository_tools.tools import RepositoryToolLayer
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
        tool_layer: RepositoryToolLayer,
        graph_traverser: Optional[FactStoreGraphTraverser] = None,
        target_resolver: Optional[TargetEntityResolver] = None,
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
        self.last_prompt_parts = None
        self.last_tool_dispatch = None

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
        self.last_tool_dispatch = tool_dispatch

        # Build system prompt
        protocol = QAProtocolAdapter(model_id=self.model)
        prompt_parts = protocol.build_system_prompt(
            tool_specs=tool_dispatch.specs(include_rim=include_rim),
            rim_metadata_block=self.rim_metadata_block if include_rim else None,
        )
        self.last_prompt_parts = prompt_parts

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


def build_analysis_service(
    *,
    llm_service,
    db: Session,
    repo_name: str,
    analysis_id: Optional[int],
    user_id: int,
    model: str,
    tool_layer: Optional[RepositoryToolLayer] = None,
    repo_root: Optional[str] = None,
    config: Optional[AgentLoopConfig] = None,
    rim_metadata_block: Optional[str] = None,
    on_turn_callback: Optional[Callable] = None,
    structured_logger=None,
    request_id: Optional[str] = None,
    repository: Optional[str] = None,
    mode: Optional[str] = None,
) -> LLMAnalysisService:
    """Factory function to create LLMAnalysisService with unified configuration.

    Eliminates code duplication between endpoints by centralizing construction
    of tool_layer, graph_traverser, target_resolver, and AgentLoopConfig.

    Tool selection remains entirely inside ToolDispatchTable.specs() — this
    function contains zero tool-name literals (hard constraint).

    Args:
        llm_service: LLM service instance
        db: SQLAlchemy session
        repo_name: Repository name
        analysis_id: Optional analysis ID (used for graph_traverser/target_resolver)
        user_id: User ID
        model: Model identifier
        tool_layer: Optional pre-built RepositoryToolLayer (reused if provided)
        repo_root: Repository root path (only used if tool_layer is None)
        config: Optional AgentLoopConfig (uses canonical 256KB default if None)
        rim_metadata_block: Optional RIM metadata to include in prompt
        on_turn_callback: Optional callback for turn events
        structured_logger: Optional structured logger for persistent logging
        request_id: Request ID for logging
        repository: Repository name for logging
        mode: Mode name (e.g., "baseline", "rim") for logging

    Returns:
        LLMAnalysisService instance ready to run queries
    """
    tool_layer = tool_layer or RepositoryToolLayer(
        repo_name=repo_name,
        analysis_id=analysis_id,
        db=db,
        repo_root=repo_root,
        user_id=user_id,
    )

    graph_traverser = FactStoreGraphTraverser(db, analysis_id) if analysis_id else None
    target_resolver = TargetEntityResolver(db, analysis_id) if analysis_id else None

    config = config or AgentLoopConfig(
        max_agent_turns=50,
        max_tool_calls=10,
        max_command_executions=0,
        max_execution_seconds=180,
        max_observation_bytes=256000,
        max_repeated_tool_calls=3,
    )

    return LLMAnalysisService(
        llm_service=llm_service,
        tool_layer=tool_layer,
        graph_traverser=graph_traverser,
        target_resolver=target_resolver,
        model=model,
        config=config,
        rim_metadata_block=rim_metadata_block,
        on_turn_callback=on_turn_callback,
        structured_logger=structured_logger,
        request_id=request_id,
        repository=repository,
        mode=mode,
    )
