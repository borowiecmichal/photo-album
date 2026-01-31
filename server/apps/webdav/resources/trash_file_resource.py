"""WebDAV trash file resource implementation."""

import logging
from pathlib import Path
from typing import BinaryIO, final, override

from wsgidav.dav_error import HTTP_FORBIDDEN, DAVError
from wsgidav.dav_provider import DAVNonCollection

from server.apps.files.logic.trash_operations import (
    permanent_delete_file,
    restore_file,
)
from server.apps.files.models import File
from server.apps.webdav.path_mapper import PathMapper

logger = logging.getLogger(__name__)


@final
class TrashFileResource(DAVNonCollection):
    """A file in the trash.

    Supports:
    - GET: Download file content
    - DELETE: Permanently delete file
    - MOVE out of trash: Restore file to destination

    Does NOT support:
    - PUT/POST: Cannot modify trashed files
    - COPY: Cannot copy from trash (must restore first)
    """

    def __init__(
        self,
        path: str,
        environ: dict,
        file_instance: File,
        path_mapper: PathMapper,
    ) -> None:
        """Initialize trash file resource.

        Args:
            path: WebDAV path (/.Trash/filename).
            environ: WSGI environ dictionary.
            file_instance: Django File model instance (deleted).
            path_mapper: PathMapper for path translation.
        """
        super().__init__(path, environ)
        self._file = file_instance
        self._path_mapper = path_mapper

    @override
    def get_display_name(self) -> str:
        """Get original filename for display.

        Returns:
            Original filename (not internal trash_name).
        """
        return Path(self._file.original_path).name

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
            Unix timestamp of original upload.
        """
        return self._file.uploaded_at.timestamp()

    @override
    def get_last_modified(self) -> float:
        """Get file modification timestamp.

        For trashed files, returns deletion time.

        Returns:
            Unix timestamp of deletion.
        """
        if self._file.deleted_at:
            return self._file.deleted_at.timestamp()
        return self._file.modified_at.timestamp()

    @override
    def get_etag(self) -> str:
        """Get entity tag for the file.

        Returns:
            Checksum as ETag.
        """
        return self._file.checksum_sha256

    @override
    def support_etag(self) -> bool:
        """Check if ETag is supported.

        Returns:
            True - we support ETags.
        """
        return True

    @override
    def get_content(self) -> BinaryIO:
        """Get file content from S3.

        Returns:
            File-like object with content.
        """
        logger.debug('Getting trashed file content: %s', self._file.file.name)
        return self._file.file.open('rb')

    @override
    def get_property_value(self, name: str) -> str | None:
        """Get DAV property value.

        Exposes original_path as custom property.

        Args:
            name: Property name (e.g., '{DAV:}original-path').

        Returns:
            Property value or None.
        """
        if name == '{DAV:}original-path':
            return self._file.original_path
        return super().get_property_value(name)

    @override
    def delete(self) -> None:
        """Permanently delete file from trash.

        Removes file from S3 and database, updates quota.
        """
        logger.info(
            'Permanently deleting file from trash: %s (ID: %d)',
            self._file.trash_name,
            self._file.id,
        )
        permanent_delete_file(self._file.id)

    @override
    def copy_move_single(self, dest_path: str, *, is_move: bool) -> None:
        """Handle MOVE (restore) or reject COPY.

        MOVE out of trash restores the file to the destination.
        COPY is not allowed from trash.

        Args:
            dest_path: Destination WebDAV path.
            is_move: True for move, False for copy.

        Raises:
            DAVError: HTTP 403 for copy or move within trash.
        """
        if not is_move:
            raise DAVError(HTTP_FORBIDDEN, 'Cannot copy from trash')

        if self._path_mapper.is_trash_path(dest_path):
            raise DAVError(HTTP_FORBIDDEN, 'Cannot move within trash')

        # Restore to destination
        dest_storage = self._path_mapper.to_storage_path(dest_path)
        logger.info(
            'Restoring file from trash: %s -> %s',
            self._file.trash_name,
            dest_storage,
        )
        restore_file(self._file.id, dest_storage)

    @override
    def begin_write(self, content_type: str | None = None) -> BinaryIO:
        """Disallow modifications to trashed files.

        Args:
            content_type: MIME type (ignored).

        Raises:
            DAVError: HTTP 403 always.
        """
        raise DAVError(HTTP_FORBIDDEN, 'Cannot modify files in trash')

    @override
    def support_ranges(self) -> bool:
        """Check if byte ranges are supported.

        Returns:
            True - S3 supports range requests.
        """
        return True

    def get_file_instance(self) -> File:
        """Get underlying File model instance.

        Returns:
            Django File model instance.
        """
        return self._file
