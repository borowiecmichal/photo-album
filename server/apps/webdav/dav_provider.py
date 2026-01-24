"""Main WsgiDAV provider for Django integration.

This module provides the DAVProvider that bridges WsgiDAV with
Django models and S3 storage.
"""

import logging
from typing import final, override

from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider

from server.apps.files.models import File
from server.apps.webdav.path_mapper import PathMapper
from server.apps.webdav.resources.base import get_user_from_environ
from server.apps.webdav.resources.collection import FolderCollection
from server.apps.webdav.resources.file_resource import FileResource

logger = logging.getLogger(__name__)


@final
class DjangoDAVProvider(DAVProvider):
    """WsgiDAV provider for Django integration.

    Maps WebDAV requests to Django File model and S3 storage.
    Each authenticated user sees only their own files.
    """

    @override
    def __init__(self) -> None:
        """Initialize the DAV provider."""
        super().__init__()

    @override
    def get_resource_inst(
        self,
        path: str,
        environ: dict,
    ) -> DAVCollection | DAVNonCollection | None:
        """Get resource instance for a given path.

        Returns a FolderCollection for directories, FileResource for files,
        or None if the path doesn't exist.

        Args:
            path: WebDAV path requested.
            environ: WSGI environ dictionary.

        Returns:
            DAV resource instance, or None if not found.
        """
        # Get authenticated user from environ
        user = get_user_from_environ(environ)
        path_mapper = PathMapper(user.id)

        # Validate path for security
        if not path_mapper.validate_path(path):
            logger.warning(
                'Invalid path rejected: %s (user: %s)',
                path,
                user.username,
            )
            return None

        logger.debug(
            'Getting resource for path: %s (user: %s)',
            path,
            user.username,
        )

        # Check if it's the root directory
        if path_mapper.is_root(path):
            return FolderCollection(path, environ, user, path_mapper)

        # Convert to storage path
        storage_path = path_mapper.to_storage_path(path)

        # Check if it's an existing file
        try:
            file_instance = File.objects.get(
                user=user,
                file=storage_path,
            )
            return FileResource(
                path,
                environ,
                file_instance,
                path_mapper,
            )
        except File.DoesNotExist:
            pass

        # Check if it's a folder (has files with this prefix)
        folder_prefix = storage_path.rstrip('/') + '/'
        has_children = File.objects.filter(
            user=user,
            file__startswith=folder_prefix,
        ).exists()

        if has_children:
            return FolderCollection(path, environ, user, path_mapper)

        # Path doesn't exist
        # Note: Empty folders are supported via marker files created by MKCOL
        logger.debug('Resource not found: %s', path)
        return None

    @override
    def is_readonly(self) -> bool:
        """Check if the provider is read-only.

        Returns:
            False - we support write operations.
        """
        return False
