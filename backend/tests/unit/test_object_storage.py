import io
import pytest
from unittest.mock import MagicMock, patch
from backend.storage.base import ObjectStorage
from backend.storage.azure import AzureBlobStorage


class InMemoryMockStorage(ObjectStorage):
    def __init__(self):
        self.store = {}
        self.container_created = False

    def ensure_container_exists(self) -> None:
        self.container_created = True

    def put_object(self, key: str, data, content_type=None, metadata=None) -> str:
        self.ensure_container_exists()
        if isinstance(data, str):
            self.store[key] = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray)):
            self.store[key] = bytes(data)
        elif hasattr(data, "read"):
            self.store[key] = data.read()
        else:
            self.store[key] = bytes(data)
        return key

    def get_object(self, key: str) -> bytes:
        self.ensure_container_exists()
        if key not in self.store:
            raise FileNotFoundError(f"Object not found: {key}")
        return self.store[key]

    def get_object_text(self, key: str, encoding: str = "utf-8") -> str:
        return self.get_object(key).decode(encoding)

    def delete_object(self, key: str) -> bool:
        self.ensure_container_exists()
        if key in self.store:
            del self.store[key]
            return True
        return False

    def object_exists(self, key: str) -> bool:
        self.ensure_container_exists()
        return key in self.store

    def list_objects(self, prefix: str = "") -> list:
        self.ensure_container_exists()
        return [k for k in self.store if k.startswith(prefix)]

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list_objects(prefix)
        for k in keys:
            self.delete_object(k)
        return len(keys)


def test_in_memory_storage_contract():
    storage = InMemoryMockStorage()
    
    # 1. Put and get text
    storage.put_object("repos/1/test.py", "def hello(): pass")
    assert storage.object_exists("repos/1/test.py") is True
    assert storage.get_object_text("repos/1/test.py") == "def hello(): pass"

    # 2. Put bytes
    storage.put_object("repos/1/data.bin", b"binary_data_123")
    assert storage.get_object("repos/1/data.bin") == b"binary_data_123"

    # 3. Stream upload
    stream = io.BytesIO(b"streaming content")
    storage.put_object("repos/1/stream.txt", stream)
    assert storage.get_object_text("repos/1/stream.txt") == "streaming content"

    # 4. List and prefix deletion
    assert len(storage.list_objects("repos/1/")) == 3
    assert storage.delete_prefix("repos/1/") == 3
    assert storage.object_exists("repos/1/test.py") is False


def test_azure_storage_mocked_calls():
    with patch("backend.storage.azure.BlobServiceClient") as mock_service_cls:
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = MagicMock()

        mock_service_cls.from_connection_string.return_value = mock_service
        mock_service.get_container_client.return_value = mock_container
        mock_container.get_blob_client.return_value = mock_blob

        storage = AzureBlobStorage(connection_string="DefaultEndpointsProtocol=http;AccountName=test;AccountKey=key;BlobEndpoint=http://localhost:10000/test;")
        
        # Test put_object
        storage.put_object("repos/1/file.py", "print(123)", content_type="text/x-python")
        mock_container.get_blob_client.assert_called_with("repos/1/file.py")
        mock_blob.upload_blob.assert_called_once()

        # Test get_object
        mock_download = MagicMock()
        mock_download.readall.return_value = b"print(123)"
        mock_blob.download_blob.return_value = mock_download

        res_text = storage.get_object_text("repos/1/file.py")
        assert res_text == "print(123)"

        # Test delete_object
        mock_blob.delete_blob.return_value = None
        assert storage.delete_object("repos/1/file.py") is True
