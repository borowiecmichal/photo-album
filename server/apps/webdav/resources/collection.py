"""WebDAV folder collection (DAVCollection) implementation."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, final, override

from django.core.files.base import ContentFile
from wsgidav.dav_provider import DAVCollection

from server.apps.files.logic.file_operations import (
    delete_file,
    upload_file,
)
from server.apps.files.models import File
from server.apps.webdav.path_mapper import PathMapper
from server.apps.webdav.resources.file_resource import (
    FileResource,
    NewFileResource,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from wsgidav.dav_provider import DAVNonCollection

logger = logging.getLogger(__name__)

# Marker file to keep empty folders visible
# Hidden file that Finder won't display
FOLDER_MARKER_NAME = '.folder'


def _is_hidden_file(name: str) -> bool:
    """Check if a file should be hidden from directory listings.

    Hides macOS-specific metadata files:
    - .folder (our marker file)
    - .DS_Store* (Finder folder settings)
    - ._* (AppleDouble/resource fork files)

    Args:
        name: Filename to check.

    Returns:
        True if file should be hidden.
    """
    return (
        name == FOLDER_MARKER_NAME
        or name.startswith(('.DS_Store', '._'))
    )


@final
class FolderCollection(DAVCollection):
    """WebDAV collection representing a folder.

    Folders are implicit in our storage model - they don't exist as
    separate database entries. A folder exists if any file has a path
    that starts with the folder path.
    """

    def __init__(
        self,
        path: str,
        environ: dict,
        user: 'User',
        path_mapper: PathMapper,
    ) -> None:
        """Initialize folder collection.

        Args:
            path: WebDAV path to the folder.
            environ: WSGI environ dictionary.
            user: Authenticated Django user.
            path_mapper: PathMapper for path translation.
        """
        super().__init__(path, environ)
        self._user = user
        self._path_mapper = path_mapper

    @override
    def get_creation_date(self) -> float:
        """Get folder creation timestamp.

        Folders are implicit, so we return a fixed date.

        Returns:
            Unix timestamp.
        """
        # Use epoch as creation date for implicit folders
        return 0.0

    @override
    def get_last_modified(self) -> float:
        """Get folder modification timestamp.

        Returns the most recent modification time of any file in folder.

        Returns:
            Unix timestamp.
        """
        storage_prefix = self._path_mapper.to_storage_path(self.path)

        # Get most recently modified file in this folder
        latest_file = (
            File.objects.filter(
                user=self._user,
                file__startswith=storage_prefix,
            )
            .order_by('-modified_at')
            .first()
        )

        if latest_file:
            return latest_file.modified_at.timestamp()

        return datetime.now(tz=UTC).timestamp()

    @override
    def get_member_names(self) -> list[str]:
        """Get names of all direct children in this folder.

        Returns both files and subfolders that are direct children
        of this folder path.

        Returns:
            List of member names (filenames and folder names).
        """
        storage_path = self._path_mapper.to_storage_path(self.path)

        # Handle root vs subfolder differently
        if self._path_mapper.is_root(self.path):
            prefix = f'{self._user.id}/'
        else:
            prefix = storage_path.rstrip('/') + '/'

        # Get all files under this prefix
        files = File.objects.filter(
            user=self._user,
            file__startswith=prefix,
        ).values_list('file', flat=True)

        # Extract direct children
        members: set[str] = set()
        prefix_len = len(prefix)

        for file_path in files:
            # Get the path after the prefix
            remainder = file_path[prefix_len:]

            # Get the first path component
            if '/' in remainder:
                # This is a file in a subfolder - add the subfolder name
                folder_name = remainder.split('/')[0]
                members.add(folder_name)
            else:
                # This is a direct child file
                members.add(remainder)

        # Filter out hidden files (markers, .DS_Store, AppleDouble ._* files)
        members = {m for m in members if not _is_hidden_file(m)}

        return sorted(members)

    @override
    def get_member(self, name: str) -> 'DAVNonCollection | DAVCollection':
        """Get a specific child member by name.

        Args:
            name: Name of the child (file or folder).

        Returns:
            FileResource for files, FolderCollection for folders.

        Raises:
            Exception: If member doesn't exist.
        """
        child_path = self._path_mapper.join_paths(self.path, name)
        storage_path = self._path_mapper.to_storage_path(child_path)

        # Check if it's a file
        try:
            file_instance = File.objects.get(
                user=self._user,
                file=storage_path,
            )
            return FileResource(
                child_path,
                self.environ,
                file_instance,
                self._path_mapper,
            )
        except File.DoesNotExist:
            pass

        # Check if it's a folder (has files with this prefix)
        folder_prefix = storage_path.rstrip('/') + '/'
        has_children = File.objects.filter(
            user=self._user,
            file__startswith=folder_prefix,
        ).exists()

        if has_children:
            return FolderCollection(
                child_path,
                self.environ,
                self._user,
                self._path_mapper,
            )

        # Member doesn't exist
        raise ValueError(f'Member not found: {name}')

    @override
    def create_empty_resource(self, name: str) -> 'DAVNonCollection':
        """Create placeholder for a new file (before PUT content).

        Called when a PUT request is about to create a new file.

        Args:
            name: Filename to create.

        Returns:
            NewFileResource placeholder.
        """
        child_path = self._path_mapper.join_paths(self.path, name)
        logger.debug('Creating empty resource for: %s', child_path)

        return NewFileResource(
            child_path,
            self.environ,
            self._user,
            self._path_mapper,
        )

    @override
    def create_collection(self, name: str) -> 'DAVCollection':
        """Create a new subfolder (MKCOL operation).

        Creates a marker file to ensure the folder persists even when empty.
        The marker file is hidden (starts with .) so Finder won't show it.

        Args:
            name: Folder name to create.

        Returns:
            FolderCollection for the new folder.
        """
        child_path = self._path_mapper.join_paths(self.path, name)
        logger.info('Creating collection: %s', child_path)

        # Create marker file to keep folder visible
        marker_path = self._path_mapper.join_paths(
            child_path,
            FOLDER_MARKER_NAME,
        )
        storage_path = self._path_mapper.to_storage_path(marker_path)

        # Create empty marker file
        marker_content = ContentFile(b'')
        upload_file(self._user, storage_path, marker_content)

        logger.info('Created folder marker: %s', storage_path)

        return FolderCollection(
            child_path,
            self.environ,
            self._user,
            self._path_mapper,
        )

    @override
    def delete(self) -> None:
        """Delete this folder and all its contents.

        Recursively deletes all files in this folder.
        """
        storage_path = self._path_mapper.to_storage_path(self.path)
        prefix = storage_path.rstrip('/') + '/'

        logger.info(
            'Deleting folder and contents: %s (prefix: %s)',
            self.path,
            prefix,
        )

        # Get all files in this folder
        files = File.objects.filter(
            user=self._user,
            file__startswith=prefix,
        )

        # Delete each file
        for file_instance in files:
            try:
                delete_file(file_instance.id)
            except Exception:
                logger.exception(
                    'Failed to delete file in folder: %s',
                    file_instance.file.name,
                )
                raise

    @override
    def support_recursive_delete(self) -> bool:
        """Check if recursive delete is supported.

        Returns:
            True - we support deleting folders with contents.
        """
        return True

    @override
    def get_etag(self) -> str | None:
        """Get entity tag for folder.

        Folders don't have a stable ETag since their contents change.

        Returns:
            None - no ETag for folders.
        """
        return None

    @override
    def support_recursive_move(self, dest_path: str) -> bool:
        """Check if recursive move is supported.

        We support moving folders with all their contents.

        Args:
            dest_path: Destination path.

        Returns:
            True - we support recursive move.
        """
        return True

    @override
    def move_recursive(self, dest_path: str) -> None:
        """Move this folder and all its contents to a new path.

        Overrides the default implementation which raises HTTP_FORBIDDEN.
        This performs an atomic move of all files with the folder prefix.

        Args:
            dest_path: Destination WebDAV path.
        """
        from server.apps.files.logic.file_operations import move_file

        # Convert paths
        source_storage_prefix = self._path_mapper.to_storage_path(self.path)
        dest_storage_prefix = self._path_mapper.to_storage_path(dest_path)

        # Normalize prefixes (ensure trailing slash)
        source_prefix = source_storage_prefix.rstrip('/') + '/'
        dest_prefix = dest_storage_prefix.rstrip('/') + '/'

        logger.info(
            'Moving folder from %s to %s',
            source_prefix,
            dest_prefix,
        )

        # Get all files under the source prefix
        files = list(File.objects.filter(
            user=self._user,
            file__startswith=source_prefix,
        ))

        # Move each file to the new location
        for file_instance in files:
            relative_path = file_instance.file.name[len(source_prefix):]
            new_path = dest_prefix + relative_path

            logger.debug(
                'Moving file: %s -> %s',
                file_instance.file.name,
                new_path,
            )
            move_file(self._user, file_instance.file.name, new_path)

        logger.info('Moved %d files', len(files))
