from dataclasses import dataclass
from typing import Optional
from .severity import Severity

@dataclass
class Finding:
    title: str
    description: str
    severity: Severity
    file_path: Optional[str] = None
    line_number: Optional[int] = None
