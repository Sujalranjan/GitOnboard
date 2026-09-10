from ...query.api.base import RepositoryAPI
from ..intent.analyzer import UserIntent
from ..intent.planner import QueryPlanner
from .expansion import EvidenceCollector, GraphExpansion
from .ranking import ContextRanking, SourceSelection
from .compression import ContextCompression
from ..knowledge.model import KnowledgePack

class RetrievalEngine:
    """
    Orchestrates the deterministic retrieval pipeline to build a KnowledgePack.
    """
    def __init__(self, api: RepositoryAPI):
        self.planner = QueryPlanner()
        self.collector = EvidenceCollector(api)
        self.expansion = GraphExpansion()
        self.ranking = ContextRanking()
        self.selection = SourceSelection()
        self.compression = ContextCompression()
        
    def build_knowledge_pack(self, intent: UserIntent) -> KnowledgePack:
        # 1. Plan queries
        plan = self.planner.plan(intent)
        
        # 2. Collect initial evidence
        evidence = self.collector.collect(plan)
        
        # 3. Expand graph relationships
        expanded = self.expansion.expand(evidence)
        
        # 4. Filter to representative sources
        selected = self.selection.select_representative(expanded)
        
        # 5. Rank by relevance
        ranked = self.ranking.rank(selected)
        
        # 6. Compress into token-budgeted Knowledge Pack
        target = intent.targets[0] if intent.targets else None
        pack = self.compression.compress(intent.type.value, ranked, target)
        
        return pack
