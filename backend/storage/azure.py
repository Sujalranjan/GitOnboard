"""
Azure Blob Storage / Azurite implementation of ObjectStorage.
"""
from __future__ import annotations
import io
import logging
import socket
from typing import BinaryIO, List, Optional, Union

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContainerClient, BlobClient, ContentSettings

from .base import ObjectStorage

logger = logging.getLogger(__name__)


def _resolve_azurite_endpoint(url_or_conn: Optional[str]) -> Optional[str]:
    if not url_or_conn:
        return url_or_conn
    if "azurite:10000" in url_or_conn:
        try:
            socket.gethostbyname("azurite")
        except socket.gaierror:
            # azurite host cannot be resolved (running outside Docker network on host mapped to 10100)
            return url_or_conn.replace("azurite:10000", "127.0.0.1:10100")
    return url_or_conn


class AzureBlobStorage(ObjectStorage):
    """
    ObjectStorage implementation backed by Azure Blob Storage / Azurite emulator.
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        container_name: str = "gitonboard-repos",
        account_name: Optional[str] = None,
        account_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        self.container_name = container_name
        self._container_created = False

        connection_string = _resolve_azurite_endpoint(connection_string)
        endpoint_url = _resolve_azurite_endpoint(endpoint_url)

        if connection_string:
            self.service_client = BlobServiceClient.from_connection_string(connection_string, api_version="2023-11-03")
        elif endpoint_url and account_key:
            self.service_client = BlobServiceClient(
                account_url=endpoint_url,
                credential={"account_name": account_name or "devstoreaccount1", "account_key": account_key},
                api_version="2023-11-03",
            )
        elif account_name and account_key:
            self.service_client = BlobServiceClient(
                account_url=f"https://{account_name}.blob.core.windows.net",
                credential=account_key,
            )
        elif endpoint_url:
            self.service_client = BlobServiceClient(account_url=endpoint_url)
        else:
            try:
                from azure.identity import DefaultAzureCredential
                self.service_client = BlobServiceClient(
                    account_url=f"https://{account_name}.blob.core.windows.net",
                    credential=DefaultAzureCredential(),
                )
            except Exception:
                # Default to standard Azurite local connection
                default_endpoint = _resolve_azurite_endpoint("http://azurite:10000/devstoreaccount1")
                default_conn = (
                    "DefaultEndpointsProtocol=http;"
                    "AccountName=devstoreaccount1;"
                    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
                    f"BlobEndpoint={default_endpoint};"
                )
                self.service_client = BlobServiceClient.from_connection_string(default_conn, api_version="2023-11-03")

        self.container_client: ContainerClient = self.service_client.get_container_client(self.container_name)

    def ensure_container_exists(self) -> None:
        if self._container_created:
            return
        try:
            self.container_client.create_container()
            self._container_created = True
        except ResourceExistsError:
            self._container_created = True
        except Exception as e:
            logger.warning(f"Could not auto-create container {self.container_name}: {e}")

    def put_object(
        self,
        key: str,
        data: Union[bytes, str, BinaryIO],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        self.ensure_container_exists()
        blob_client = self.container_client.get_blob_client(key)

        content_settings = ContentSettings(content_type=content_type) if content_type else None

        if isinstance(data, str):
            payload = data.encode("utf-8")
        else:
            payload = data

        blob_client.upload_blob(
            payload,
            overwrite=True,
            content_settings=content_settings,
            metadata=metadata,
        )
        return key

    def get_object(self, key: str) -> bytes:
        self.ensure_container_exists()
        blob_client = self.container_client.get_blob_client(key)
        try:
            stream = blob_client.download_blob()
            return stream.readall()
        except ResourceNotFoundError:
            raise FileNotFoundError(f"Object not found in storage: {key}")

    def get_object_text(self, key: str, encoding: str = "utf-8") -> str:
        raw_bytes = self.get_object(key)
        return raw_bytes.decode(encoding, errors="replace")

    def delete_object(self, key: str) -> bool:
        self.ensure_container_exists()
        blob_client = self.container_client.get_blob_client(key)
        try:
            blob_client.delete_blob()
            return True
        except ResourceNotFoundError:
            return False

    def object_exists(self, key: str) -> bool:
        self.ensure_container_exists()
        blob_client = self.container_client.get_blob_client(key)
        return blob_client.exists()

    def list_objects(self, prefix: str = "") -> List[str]:
        self.ensure_container_exists()
        blobs = self.container_client.list_blobs(name_starts_with=prefix if prefix else None)
        return [b.name for b in blobs]

    def delete_prefix(self, prefix: str) -> int:
        self.ensure_container_exists()
        count = 0
        for blob_name in self.list_objects(prefix=prefix):
            if self.delete_object(blob_name):
                count += 1
        return count
