"""Metadata extraction utilities for files."""

import hashlib
import mimetypes
from pathlib import Path
from typing import BinaryIO, Final

from django.core.exceptions import ValidationError

_CHUNK_SIZE: Final = 8192  # 8KB chunks for checksum calculation


def detect_mime_type(file_obj: BinaryIO, filename: str) -> str:
    """Detect MIME type from file.

    Uses Python's built-in mimetypes module to guess MIME type
    from filename extension. For more accurate detection based
    on file contents, consider adding python-magic library.

    Args:
        file_obj: File-like object (not used in basic implementation).
        filename: Filename with extension.

    Returns:
        MIME type string (e.g., 'image/jpeg', 'application/pdf').
        Returns 'application/octet-stream' if type cannot be determined.
    """
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type is None:
        return 'application/octet-stream'
    return mime_type


def calculate_checksum(file_obj: BinaryIO) -> str:
    """Calculate SHA256 checksum of file.

    Reads file in chunks to handle large files efficiently.
    Resets file pointer to beginning after calculation.

    Args:
        file_obj: File-like object to checksum.

    Returns:
        Hex-encoded SHA256 hash string.
    """
    sha256_hash = hashlib.sha256()

    # Reset file pointer to beginning
    file_obj.seek(0)

    # Read in chunks to handle large files
    for chunk in iter(lambda: file_obj.read(_CHUNK_SIZE), b''):
        sha256_hash.update(chunk)

    # Reset file pointer to beginning for subsequent operations
    file_obj.seek(0)

    return sha256_hash.hexdigest()


def extract_filename(storage_path: str) -> str:
    """Extract filename from storage path.

    Args:
        storage_path: Full path (e.g., '123/docs/file.pdf').

    Returns:
        Filename (e.g., 'file.pdf').
    """
    return Path(storage_path).name


def extract_folder_path(storage_path: str) -> str:
    """Extract folder path from storage path.

    Args:
        storage_path: Full path (e.g., '123/docs/reports/file.pdf').

    Returns:
        Folder path (e.g., '123/docs/reports').
    """
    return str(Path(storage_path).parent)


def validate_storage_path(user_id: int, storage_path: str) -> None:
    """Validate storage path follows user isolation rules.

    Ensures the storage path starts with the user's ID to maintain
    multi-user isolation. This is a critical security check.

    Args:
        user_id: Owner's user ID.
        storage_path: Proposed storage path.

    Raises:
        ValidationError: If path doesn't start with user_id or is invalid.
    """
    if not storage_path:
        raise ValidationError('Storage path cannot be empty')

    # Extract first path component
    path_parts = Path(storage_path).parts
    if not path_parts:
        raise ValidationError('Storage path must have at least one component')

    first_component = path_parts[0]

    # Check if first component matches user_id
    try:
        path_user_id = int(first_component)
    except ValueError as error:
        raise ValidationError(
            'Storage path must start with user ID',
        ) from error

    if path_user_id != user_id:
        raise ValidationError(
            f'Storage path user ID ({path_user_id}) does not match '
            f'owner ({user_id})',
        )


def get_file_extension(filename: str) -> str:
    """Get file extension from filename.

    Args:
        filename: Filename (e.g., 'document.pdf').

    Returns:
        Extension without dot, lowercase (e.g., 'pdf').
        Returns empty string if no extension.
    """
    extension = Path(filename).suffix
    return extension.lstrip('.').lower()
