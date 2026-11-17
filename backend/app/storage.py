"""Storage backend abstraction supporting local filesystem and Azure Blob Storage."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import AppConfig, Settings

logger = logging.getLogger(__name__)

try:
    from azure.core.exceptions import ResourceNotFoundError
    from azure.storage.blob import BlobServiceClient, ContentSettings
except ImportError:
    BlobServiceClient = None  # type: ignore[assignment, misc]
    ContentSettings = None  # type: ignore[assignment, misc]
    ResourceNotFoundError = Exception  # type: ignore[assignment, misc]


class StorageBackend(ABC):
    """Abstract base class for persistent file storage."""

    @abstractmethod
    def save(self, filename: str, content: bytes, content_type: str) -> None:
        """Save file content persistently."""
        ...

    @abstractmethod
    def get(self, filename: str) -> bytes | None:
        """Retrieve file binary content if it exists."""
        ...

    @abstractmethod
    def delete(self, filename: str) -> bool:
        """Delete file from persistent storage."""
        ...

    @abstractmethod
    def exists(self, filename: str) -> bool:
        """Check if file exists in storage."""
        ...


class LocalFileStorage(StorageBackend):
    """Local filesystem storage backend for development and single-container deployments."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, filename: str) -> Path:
        safe_name = Path(filename).name
        return self.root_dir / safe_name

    def save(self, filename: str, content: bytes, content_type: str) -> None:
        path = self._resolve(filename)
        path.write_bytes(content)

    def get(self, filename: str) -> bytes | None:
        path = self._resolve(filename)
        if path.is_file():
            return path.read_bytes()
        return None

    def delete(self, filename: str) -> bool:
        path = self._resolve(filename)
        if path.is_file():
            path.unlink()
            return True
        return False

    def exists(self, filename: str) -> bool:
        return self._resolve(filename).is_file()


class AzureBlobStorage(StorageBackend):
    """Azure Blob Storage backend for persistent multi-instance cloud deployments."""

    def __init__(
        self,
        connection_string: str,
        container_name: str = "invoices",
        local_cache_dir: Path | None = None,
    ) -> None:
        if BlobServiceClient is None:
            raise RuntimeError(
                "azure-storage-blob package is not installed. "
                "Install azure-storage-blob to enable Azure Blob Storage."
            )
        self.client = BlobServiceClient.from_connection_string(connection_string)
        self.container_name = container_name
        self.local_cache_dir = local_cache_dir
        if self.local_cache_dir:
            self.local_cache_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_container()

    def _ensure_container(self) -> None:
        try:
            container_client = self.client.get_container_client(self.container_name)
            if not container_client.exists():
                container_client.create_container()
        except Exception:
            logger.exception(
                "Failed to verify or create Azure Blob container '%s'", self.container_name
            )

    def save(self, filename: str, content: bytes, content_type: str) -> None:
        safe_name = Path(filename).name
        if self.local_cache_dir:
            (self.local_cache_dir / safe_name).write_bytes(content)

        blob_client = self.client.get_blob_client(
            container=self.container_name, blob=safe_name
        )
        content_settings = (
            ContentSettings(content_type=content_type) if ContentSettings else None
        )
        blob_client.upload_blob(content, overwrite=True, content_settings=content_settings)

    def get(self, filename: str) -> bytes | None:
        safe_name = Path(filename).name
        if self.local_cache_dir:
            local_path = self.local_cache_dir / safe_name
            if local_path.is_file():
                return local_path.read_bytes()

        try:
            blob_client = self.client.get_blob_client(
                container=self.container_name, blob=safe_name
            )
            data = blob_client.download_blob().readall()
            if self.local_cache_dir:
                (self.local_cache_dir / safe_name).write_bytes(data)
            return data
        except ResourceNotFoundError:
            return None
        except Exception:
            logger.exception("Error downloading blob '%s'", safe_name)
            return None

    def delete(self, filename: str) -> bool:
        safe_name = Path(filename).name
        if self.local_cache_dir:
            (self.local_cache_dir / safe_name).unlink(missing_ok=True)
        try:
            blob_client = self.client.get_blob_client(
                container=self.container_name, blob=safe_name
            )
            blob_client.delete_blob()
            return True
        except ResourceNotFoundError:
            return False
        except Exception:
            logger.exception("Error deleting blob '%s'", safe_name)
            return False

    def exists(self, filename: str) -> bool:
        safe_name = Path(filename).name
        if self.local_cache_dir and (self.local_cache_dir / safe_name).is_file():
            return True
        try:
            blob_client = self.client.get_blob_client(
                container=self.container_name, blob=safe_name
            )
            return bool(blob_client.exists())
        except Exception:
            return False


def build_storage_backend(config: AppConfig, settings: Settings) -> StorageBackend:
    """Build and return configured StorageBackend instance."""
    if settings.azure_storage_connection_string and BlobServiceClient is not None:
        try:
            return AzureBlobStorage(
                connection_string=settings.azure_storage_connection_string,
                container_name=settings.azure_storage_container_name,
                local_cache_dir=config.upload_dir,
            )
        except Exception as error:
            logger.warning(
                "Could not initialize AzureBlobStorage: %s. Falling back to LocalFileStorage.",
                error,
            )
    return LocalFileStorage(config.upload_dir)
