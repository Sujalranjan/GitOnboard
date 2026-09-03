from dataclasses import dataclass
from typing import List
from .severity import Severity

@dataclass
class Cycle:
    members: List[str]
    size: int
    severity: Severity
    description: str
