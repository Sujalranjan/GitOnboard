"""
Generic ObjectStorage Interface.

Provides a vendor-agnostic abstraction for storing and retrieving repository
files and artifacts. Applications interact through this interface rather than
directly referencing cloud-specific SDKs (e.g. Azure Blob Storage, Azurite).
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import BinaryIO, List, Optional, Union


class ObjectStorage(ABC):
    """
    Abstract interface for object storage operations.
    """

    @abstractmethod
    def put_object(
        self,
        key: str,
        data: Union[bytes, str, BinaryIO],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Uploads an object to storage.
        Supports bytes, strings, or streaming file-like objects.

        Returns the storage key/blob name.
        """
        pass

    @abstractmethod
    def get_object(self, key: str) -> bytes:
        """
        Downloads an object as raw bytes.
        """
        pass

    @abstractmethod
    def get_object_text(self, key: str, encoding: str = "utf-8") -> str:
        """
        Downloads an object and decodes it as text.
        """
        pass

    @abstractmethod
    def delete_object(self, key: str) -> bool:
        """
        Deletes an object. Returns True if deleted or False if not found.
        """
        pass

    @abstractmethod
    def object_exists(self, key: str) -> bool:
        """
        Checks whether an object exists in storage.
        """
        pass

    @abstractmethod
    def list_objects(self, prefix: str = "") -> List[str]:
        """
        Lists all object keys matching the given prefix.
        """
        pass

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """
        Deletes all objects matching the given prefix.
        Returns the number of deleted objects.
        """
        pass

    @abstractmethod
    def ensure_container_exists(self) -> None:
        """
        Ensures the underlying storage container/bucket exists.
        """
        pass
