"""WebDAV trash collection (/.Trash/) implementation."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, final, override

from wsgidav.dav_error import HTTP_FORBIDDEN, HTTP_NOT_FOUND, DAVError
from wsgidav.dav_provider import DAVCollection

from server.apps.files.logic.trash_operations import (
    empty_trash,
    list_trash,
)
from server.apps.webdav.path_mapper import PathMapper
from server.apps.webdav.resources.trash_file_resource import TrashFileResource

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from wsgidav.dav_provider import DAVNonCollection

logger = logging.getLogger(__name__)


@final
class TrashCollection(DAVCollection):
    """Virtual /.Trash/ folder showing soft-deleted files.

    Provides WebDAV access to trashed files:
    - PROPFIND: Lists deleted files by original filename
    - DELETE on collection: Empties entire trash
    - GET/DELETE on members: Download or permanently delete files
    - MOVE from trash: Restore files
    """

    def __init__(
        self,
        path: str,
        environ: dict,
        user: 'User',
        path_mapper: PathMapper,
    ) -> None:
        """Initialize trash collection.

        Args:
            path: WebDAV path (/.Trash/).
            environ: WSGI environ dictionary.
            user: Authenticated Django user.
            path_mapper: PathMapper for path translation.
        """
        super().__init__(path, environ)
        self._user = user
        self._path_mapper = path_mapper

    @override
    def get_display_name(self) -> str:
        """Get display name for trash folder.

        Returns:
            Display name '.Trash'.
        """
        return '.Trash'

    @override
    def get_creation_date(self) -> float:
        """Get folder creation timestamp.

        Returns:
            Unix timestamp (epoch for virtual folder).
        """
        return 0.0

    @override
    def get_last_modified(self) -> float:
        """Get folder modification timestamp.

        Returns most recent deletion time, or now if trash is empty.

        Returns:
            Unix timestamp.
        """
        latest = list_trash(self._user).first()
        if latest and latest.deleted_at:
            return latest.deleted_at.timestamp()
        return datetime.now(tz=UTC).timestamp()

    @override
    def get_member_names(self) -> list[str]:
        """Get original filenames of all deleted files.

        Returns original filenames for display, not internal trash_names.

        Returns:
            List of original filenames.
        """
        files = list_trash(self._user)
        return [Path(file_obj.original_path).name for file_obj in files]

    @override
    def get_member(self, name: str) -> 'DAVNonCollection':
        """Get trashed file by original filename.

        Args:
            name: Original filename to find.

        Returns:
            TrashFileResource for the file.

        Raises:
            DAVError: HTTP 404 if file not found.
        """
        files = list_trash(self._user)
        for file_obj in files:
            if Path(file_obj.original_path).name == name:
                return TrashFileResource(
                    f'/.Trash/{name}',
                    self.environ,
                    file_obj,
                    self._path_mapper,
                )

        raise DAVError(HTTP_NOT_FOUND, f'File not found in trash: {name}')

    @override
    def create_empty_resource(self, name: str) -> 'DAVNonCollection':
        """Disallow creating files in trash.

        Args:
            name: Attempted filename.

        Raises:
            DAVError: HTTP 403 always.
        """
        raise DAVError(HTTP_FORBIDDEN, 'Cannot create files in trash')

    @override
    def create_collection(self, name: str) -> 'DAVCollection':
        """Disallow creating folders in trash.

        Args:
            name: Attempted folder name.

        Raises:
            DAVError: HTTP 403 always.
        """
        raise DAVError(HTTP_FORBIDDEN, 'Cannot create folders in trash')

    @override
    def delete(self) -> None:
        """Empty entire trash (DELETE on /.Trash/).

        Permanently deletes all trashed files for the user.
        """
        logger.info('Emptying trash for user: %s', self._user.username)
        count = empty_trash(self._user)
        logger.info('Emptied %d files from trash', count)

    @override
    def support_recursive_delete(self) -> bool:
        """Check if recursive delete is supported.

        Returns:
            True - emptying trash deletes all files.
        """
        return True

    @override
    def get_etag(self) -> str | None:
        """Get entity tag for folder.

        Returns:
            None - folders don't have stable ETags.
        """
        return None
