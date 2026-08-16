"""
Storage package exposing ObjectStorage abstraction and Azure Blob Storage provider.
"""
from typing import Optional
from backend.config import settings
from .base import ObjectStorage
from .azure import AzureBlobStorage
from .naming import build_blob_key, sanitize_relative_path

_storage_instance: Optional[ObjectStorage] = None


def get_storage() -> ObjectStorage:
    """
    Returns a configured ObjectStorage instance based on application settings.
    """
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = AzureBlobStorage(
            connection_string=settings.azure_storage_connection_string or None,
            container_name=settings.azure_storage_container,
            account_name=settings.azure_storage_account_name or None,
            account_key=settings.azure_storage_account_key or None,
            endpoint_url=settings.azure_storage_endpoint or None,
        )
    return _storage_instance


def set_storage(storage: Optional[ObjectStorage]) -> None:
    """
    Explicitly set or override storage instance (useful in tests).
    """
    global _storage_instance
    _storage_instance = storage


__all__ = [
    "ObjectStorage",
    "AzureBlobStorage",
    "get_storage",
    "set_storage",
    "build_blob_key",
    "sanitize_relative_path",
]
