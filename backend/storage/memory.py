"""
In-Memory ObjectStorage Implementation.
Useful for deterministic unit and integration testing without requiring a live Azurite/Azure storage service.
"""
from __future__ import annotations
import io
from typing import BinaryIO, Dict, List, Optional, Union
from .base import ObjectStorage


class InMemoryObjectStorage(ObjectStorage):
    """
    In-memory mock/test storage implementing ObjectStorage interface.
    """

    def __init__(self):
        self._store: Dict[str, bytes] = {}

    def put_object(
        self,
        key: str,
        data: Union[bytes, str, BinaryIO],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        if isinstance(data, str):
            payload = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray)):
            payload = bytes(data)
        elif hasattr(data, "read"):
            payload = data.read()
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
        else:
            payload = bytes(data)

        self._store[key] = payload
        return key

    def get_object(self, key: str) -> bytes:
        if key not in self._store:
            raise KeyError(f"Blob '{key}' not found in in-memory storage")
        return self._store[key]

    def get_object_text(self, key: str, encoding: str = "utf-8") -> str:
        return self.get_object(key).decode(encoding, errors="replace")

    def delete_object(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def object_exists(self, key: str) -> bool:
        return key in self._store

    def list_objects(self, prefix: str = "") -> List[str]:
        if not prefix:
            return list(self._store.keys())
        return [k for k in self._store.keys() if k.startswith(prefix)]

    def delete_prefix(self, prefix: str) -> int:
        keys_to_delete = self.list_objects(prefix)
        for k in keys_to_delete:
            del self._store[k]
        return len(keys_to_delete)

    def ensure_container_exists(self) -> None:
        pass
