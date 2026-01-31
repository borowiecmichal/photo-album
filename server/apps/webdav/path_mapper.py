"""Path translation between WebDAV paths and storage paths.

WebDAV paths are user-visible paths like /documents/report.pdf.
Storage paths include user ID prefix: {user_id}/documents/report.pdf.
"""

from typing import Final, final

# Character used to split storage paths
_PATH_SEPARATOR: Final = '/'

# Special trash path
_TRASH_PATH: Final = '/.Trash'


@final
class PathMapper:
    """Translates between WebDAV paths and storage paths.

    WebDAV paths are what users see: /documents/report.pdf
    Storage paths include user ID: {user_id}/documents/report.pdf

    This class handles all path translation and validation.
    """

    def __init__(self, user_id: int) -> None:
        """Initialize path mapper with user ID.

        Args:
            user_id: ID of the authenticated user.
        """
        self._user_id = user_id

    @property
    def user_id(self) -> int:
        """Get the user ID for this mapper."""
        return self._user_id

    def to_storage_path(self, webdav_path: str) -> str:
        """Convert WebDAV path to storage path.

        Args:
            webdav_path: User-visible WebDAV path (e.g., /documents/file.pdf).

        Returns:
            Storage path with user ID prefix (e.g., 123/documents/file.pdf).
        """
        # Normalize the path: remove leading/trailing slashes
        normalized = webdav_path.strip(_PATH_SEPARATOR)

        # Handle root path
        if not normalized:
            return str(self._user_id)

        # Prepend user ID
        return f'{self._user_id}/{normalized}'

    def to_webdav_path(self, storage_path: str) -> str:
        """Convert storage path to WebDAV path.

        Args:
            storage_path: Storage path with user ID (e.g., 123/documents/file).

        Returns:
            User-visible WebDAV path (e.g., /documents/file).
        """
        # Normalize the path
        normalized = storage_path.strip(_PATH_SEPARATOR)

        # Handle root path (just user ID)
        if normalized == str(self._user_id):
            return _PATH_SEPARATOR

        # Remove user ID prefix
        prefix = f'{self._user_id}/'
        if normalized.startswith(prefix):
            return _PATH_SEPARATOR + normalized[len(prefix):]

        # If path doesn't match user, return as-is with leading slash
        return _PATH_SEPARATOR + normalized

    def get_parent_path(self, webdav_path: str) -> str:
        """Get parent directory of a WebDAV path.

        Args:
            webdav_path: WebDAV path (e.g., /documents/reports/file.pdf).

        Returns:
            Parent path (e.g., /documents/reports).
            Returns / for root-level items.
        """
        normalized = webdav_path.strip(_PATH_SEPARATOR)

        if not normalized or _PATH_SEPARATOR not in normalized:
            return _PATH_SEPARATOR

        parent = normalized.rsplit(_PATH_SEPARATOR, 1)[0]
        return _PATH_SEPARATOR + parent

    def get_name(self, webdav_path: str) -> str:
        """Get filename or folder name from WebDAV path.

        Args:
            webdav_path: WebDAV path (e.g., /documents/file.pdf).

        Returns:
            Name component (e.g., file.pdf).
            Returns empty string for root path.
        """
        normalized = webdav_path.strip(_PATH_SEPARATOR)

        if not normalized:
            return ''

        if _PATH_SEPARATOR in normalized:
            return normalized.rsplit(_PATH_SEPARATOR, 1)[1]

        return normalized

    def join_paths(self, parent: str, name: str) -> str:
        """Join parent path and name to create full WebDAV path.

        Args:
            parent: Parent WebDAV path (e.g., /documents).
            name: Name to append (e.g., file.pdf).

        Returns:
            Joined path (e.g., /documents/file.pdf).
        """
        parent_normalized = parent.strip(_PATH_SEPARATOR)
        name_normalized = name.strip(_PATH_SEPARATOR)

        if not parent_normalized:
            return _PATH_SEPARATOR + name_normalized

        joined = parent_normalized + _PATH_SEPARATOR + name_normalized
        return _PATH_SEPARATOR + joined

    def is_root(self, webdav_path: str) -> bool:
        """Check if path is the root directory.

        Args:
            webdav_path: WebDAV path to check.

        Returns:
            True if path is root directory.
        """
        return not webdav_path.strip(_PATH_SEPARATOR)

    def validate_path(self, webdav_path: str) -> bool:
        """Validate WebDAV path for security.

        Checks for path traversal attacks and invalid characters.

        Args:
            webdav_path: WebDAV path to validate.

        Returns:
            True if path is valid and safe.
        """
        # Check for path traversal attempts
        if '..' in webdav_path:
            return False

        # Check for null bytes
        return '\x00' not in webdav_path

    def is_trash_path(self, webdav_path: str) -> bool:
        """Check if path is the trash folder or within it.

        Args:
            webdav_path: WebDAV path to check.

        Returns:
            True if path is /.Trash or /.Trash/something.
        """
        normalized = webdav_path.rstrip(_PATH_SEPARATOR)
        return normalized == _TRASH_PATH or normalized.startswith(
            _TRASH_PATH + _PATH_SEPARATOR,
        )

    def is_trash_root(self, webdav_path: str) -> bool:
        """Check if path is exactly /.Trash/.

        Args:
            webdav_path: WebDAV path to check.

        Returns:
            True if path is the trash root.
        """
        return webdav_path.rstrip(_PATH_SEPARATOR) == _TRASH_PATH

    def get_trash_item_name(self, webdav_path: str) -> str:
        """Extract item name from trash path like /.Trash/filename.

        Args:
            webdav_path: Trash path (e.g., /.Trash/report.pdf).

        Returns:
            Item name (e.g., report.pdf), empty string if not a trash item.
        """
        normalized = webdav_path.strip(_PATH_SEPARATOR)
        prefix = '.Trash/'
        if normalized.startswith(prefix):
            return normalized[len(prefix):]
        return ''
