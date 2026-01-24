"""WebDAV file resource (DAVNonCollection) implementation."""

import logging
from io import BytesIO
from typing import TYPE_CHECKING, BinaryIO, final, override

from django.core.files.base import ContentFile
from wsgidav.dav_error import HTTP_INSUFFICIENT_STORAGE, DAVError
from wsgidav.dav_provider import DAVNonCollection

from server.apps.files.exceptions import QuotaExceededError
from server.apps.files.logic.file_operations import (
    copy_file,
    delete_file,
    update_file_content,
    upload_file,
)
from server.apps.files.models import File
from server.apps.webdav.path_mapper import PathMapper

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


@final
class FileResource(DAVNonCollection):
    """WebDAV resource representing a file in storage.

    Maps WebDAV operations to the files app file_operations module.
    Each instance represents a single file owned by the authenticated user.
    """

    def __init__(
        self,
        path: str,
        environ: dict,
        file_instance: File,
        path_mapper: PathMapper,
    ) -> None:
        """Initialize file resource.

        Args:
            path: WebDAV path to the file.
            environ: WSGI environ dictionary.
            file_instance: Django File model instance.
            path_mapper: PathMapper for path translation.
        """
        super().__init__(path, environ)
        self._file = file_instance
        self._path_mapper = path_mapper

    @override
    def get_content_length(self) -> int:
        """Get file size in bytes.

        Returns:
            File size in bytes.
        """
        return self._file.size_bytes

    @override
    def get_content_type(self) -> str:
        """Get file MIME type.

        Returns:
            MIME type string.
        """
        return self._file.mime_type

    @override
    def get_creation_date(self) -> float:
        """Get file creation timestamp.

        Returns:
            Unix timestamp of upload time.
        """
        return self._file.uploaded_at.timestamp()

    @override
    def get_last_modified(self) -> float:
        """Get file modification timestamp.

        Returns:
            Unix timestamp of last modification.
        """
        return self._file.modified_at.timestamp()

    @override
    def get_etag(self) -> str:
        """Get entity tag for the file.

        Uses SHA256 checksum as ETag for content-based caching.

        Returns:
            ETag string (checksum without quotes - WsgiDAV adds them).
        """
        return self._file.checksum_sha256

    @override
    def support_etag(self) -> bool:
        """Check if ETag is supported.

        Returns:
            True - we support ETags via checksum.
        """
        return True

    @override
    def get_content(self) -> BinaryIO:
        """Get file content as file-like object.

        Streams content from S3 storage backend.

        Returns:
            File-like object with file content.
        """
        logger.debug('Getting content for file: %s', self._file.file.name)
        return self._file.file.open('rb')

    @override
    def begin_write(self, content_type: str | None = None) -> BinaryIO:
        """Begin writing new content to the file.

        Creates a buffer to collect uploaded content.
        The actual upload happens in end_write().

        Args:
            content_type: MIME type of content (optional).

        Returns:
            Writable file-like object.
        """
        logger.debug('Beginning write for file: %s', self.path)
        return _UploadBuffer(self)

    @override
    def delete(self) -> None:
        """Delete the file from storage and database.

        Uses the files app delete_file operation which handles
        transaction safety (DB first, then S3).
        """
        logger.info('Deleting file via WebDAV: %s', self._file.file.name)
        delete_file(self._file.id)

    @override
    def support_ranges(self) -> bool:
        """Check if byte ranges are supported.

        Returns:
            True - S3 supports range requests.
        """
        return True

    @override
    def support_recursive_move(self, dest_path: str) -> bool:
        """Check if recursive move is supported.

        Files don't have recursive move - that's for collections.

        Args:
            dest_path: Destination path.

        Returns:
            False - files don't support recursive move.
        """
        return False

    @override
    def copy_move_single(self, dest_path: str, *, is_move: bool) -> None:
        """Copy or move this file to a new path.

        For both copy and move, we only copy the file here.
        WsgiDAV will call delete() separately for moves after this succeeds.

        Args:
            dest_path: Destination WebDAV path.
            is_move: True for move, False for copy.

        Raises:
            DAVError: HTTP 507 if quota exceeded (for copy operations).
        """
        # Get user from the file instance
        user = self._file.user

        # Convert WebDAV dest path to storage path
        dest_storage_path = self._path_mapper.to_storage_path(dest_path)
        source_storage_path = self._file.file.name

        logger.info(
            '%s file from %s to %s (copy phase)',
            'Moving' if is_move else 'Copying',
            source_storage_path,
            dest_storage_path,
        )

        # Always copy - WsgiDAV calls delete() after for moves
        try:
            copy_file(user, source_storage_path, dest_storage_path)
        except QuotaExceededError as exc:
            logger.warning('Quota exceeded during file copy: %s', exc)
            raise DAVError(HTTP_INSUFFICIENT_STORAGE, str(exc)) from exc

    def get_file_instance(self) -> File:
        """Get underlying File model instance.

        Returns:
            Django File model instance.
        """
        return self._file


class _UploadBuffer(BytesIO):
    """Buffer for collecting uploaded file content.

    Wraps BytesIO to capture uploaded content and trigger
    actual file creation when the buffer is closed.
    """

    def __init__(self, resource: FileResource) -> None:
        """Initialize upload buffer.

        Args:
            resource: FileResource this buffer belongs to.
        """
        super().__init__()
        self._resource = resource

    @override
    def close(self) -> None:
        """Close buffer and write file to storage.

        This is called by WsgiDAV when upload is complete.

        Raises:
            DAVError: HTTP 507 if quota exceeded.
        """
        if self.closed:
            return

        # Get buffer content
        self.seek(0)
        content = self.read()

        if content:
            try:
                self._write_file(content)
            except QuotaExceededError as exc:
                logger.warning('Quota exceeded during file update: %s', exc)
                raise DAVError(HTTP_INSUFFICIENT_STORAGE, str(exc)) from exc

        super().close()

    def _write_file(self, content: bytes) -> None:
        """Write file content to storage atomically.

        Uses update_file_content for atomic updates to prevent
        data loss if the upload fails.

        Args:
            content: File content bytes.
        """
        logger.debug(
            'Writing %d bytes to file: %s',
            len(content),
            self._resource.path,
        )

        # Get file ID for atomic update
        file_instance = self._resource.get_file_instance()

        # Use atomic update - uploads new content first, then updates DB
        content_file = ContentFile(content)
        update_file_content(file_instance.id, content_file)


@final
class NewFileResource(DAVNonCollection):
    """WebDAV resource for a file being created (doesn't exist yet).

    Used when a PUT request creates a new file.
    """

    def __init__(
        self,
        path: str,
        environ: dict,
        user: 'User',
        path_mapper: PathMapper,
    ) -> None:
        """Initialize new file resource.

        Args:
            path: WebDAV path where file will be created.
            environ: WSGI environ dictionary.
            user: Authenticated Django user.
            path_mapper: PathMapper for path translation.
        """
        super().__init__(path, environ)
        self._user = user
        self._path_mapper = path_mapper

    @override
    def get_content_length(self) -> int:
        """Get file size (0 for new files)."""
        return 0

    @override
    def get_content_type(self) -> str:
        """Get content type (unknown for new files)."""
        return 'application/octet-stream'

    @override
    def get_content(self) -> BinaryIO:
        """Get content (empty for new files)."""
        return BytesIO(b'')

    @override
    def get_etag(self) -> str | None:
        """Get entity tag (none for new files)."""
        return None

    @override
    def support_etag(self) -> bool:
        """Check if ETag is supported (not for new files)."""
        return False

    @override
    def begin_write(self, content_type: str | None = None) -> BinaryIO:
        """Begin writing content to create the file.

        Args:
            content_type: MIME type of content.

        Returns:
            Writable buffer that creates file on close.
        """
        logger.debug('Beginning write for new file: %s', self.path)
        return _NewFileBuffer(self, self._user, self._path_mapper)


class _NewFileBuffer(BytesIO):
    """Buffer for creating new files.

    Captures uploaded content and creates the file when closed.
    """

    def __init__(
        self,
        resource: NewFileResource,
        user: 'User',
        path_mapper: PathMapper,
    ) -> None:
        """Initialize buffer.

        Args:
            resource: NewFileResource this buffer belongs to.
            user: User who owns the new file.
            path_mapper: PathMapper for path translation.
        """
        super().__init__()
        self._resource = resource
        self._user = user
        self._path_mapper = path_mapper

    @override
    def close(self) -> None:
        """Close buffer and create file in storage.

        Raises:
            DAVError: HTTP 507 if quota exceeded.
        """
        if self.closed:
            return

        # Get buffer content
        self.seek(0)
        content = self.read()

        # Always create file, even if empty
        # Finder sends empty PUT first, then LOCK, then PUT with content
        try:
            self._create_file(content)
        except QuotaExceededError as exc:
            logger.warning('Quota exceeded during file creation: %s', exc)
            raise DAVError(HTTP_INSUFFICIENT_STORAGE, str(exc)) from exc

        super().close()

    def _create_file(self, content: bytes) -> None:
        """Create new file with content.

        Args:
            content: File content bytes.
        """
        storage_path = self._path_mapper.to_storage_path(self._resource.path)
        logger.info(
            'Creating new file via WebDAV: %s (%d bytes)',
            storage_path,
            len(content),
        )

        content_file = ContentFile(content)
        upload_file(self._user, storage_path, content_file)
