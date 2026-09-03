from enum import Enum
from pydantic import BaseModel
from typing import List, Optional

class IntentType(Enum):
    EXPLAIN_FEATURE = "Explain Feature"
    TRACE_EXECUTION = "Trace Execution"
    EXPLAIN_ARCHITECTURE = "Explain Architecture"
    IMPACT_ANALYSIS = "Impact Analysis"
    UNKNOWN = "Unknown"

class UserIntent(BaseModel):
    type: IntentType
    targets: List[str]
    scope: str = "global"

class IntentAnalyzer:
    """
    Parses natural language requests into structured Intents.
    """
    def analyze(self, query: str) -> UserIntent:
        # Mock implementation for MVP. A real implementation might use basic NLP or an LLM call.
        query_lower = query.lower()
        if "how does" in query_lower and "work" in query_lower:
            # Extract target heuristically
            target = query.split("does ")[1].split(" work")[0].strip()
            return UserIntent(type=IntentType.EXPLAIN_FEATURE, targets=[target])
            
        elif "trace" in query_lower:
            return UserIntent(type=IntentType.TRACE_EXECUTION, targets=[])
            
        return UserIntent(type=IntentType.UNKNOWN, targets=[])
