from .base import BaseCapabilityDetector
from .auth_detector import AuthenticationDetector
from .crud_detector import CRUDDetector
from .background_tasks_detector import BackgroundTaskDetector
from .file_upload_detector import FileUploadDetector
from .deduplicator import CapabilityDeduplicator

__all__ = [
    "BaseCapabilityDetector",
    "AuthenticationDetector",
    "CRUDDetector",
    "BackgroundTaskDetector",
    "FileUploadDetector",
    "CapabilityDeduplicator",
]
