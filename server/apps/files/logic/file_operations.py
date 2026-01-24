"""Business logic for file operations."""

import logging
from typing import TYPE_CHECKING, BinaryIO

from django.contrib.auth import get_user_model
from django.core.files.base import File as DjangoFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import QuerySet

from server.apps.files.infrastructure.metadata import (
    calculate_checksum,
    detect_mime_type,
    extract_filename,
    validate_storage_path,
)
from server.apps.files.models import File

if TYPE_CHECKING:
    from server.apps.files.infrastructure.storage import FileStorage

User = get_user_model()
logger = logging.getLogger(__name__)


def _get_storage() -> 'FileStorage':
    """Get the configured default storage backend.

    Returns:
        FileStorage instance with proper S3 configuration.
    """
    return default_storage  # type: ignore[return-value]


def upload_file(
    user: User,
    storage_path: str,
    file_obj: BinaryIO | DjangoFile,
) -> File:
    """Upload file to storage and create database record.

    Transaction safety: Upload to storage first, then create DB record.
    If DB transaction fails, the uploaded file is deleted from storage
    (rollback).

    Args:
        user: Owner of the file.
        storage_path: Full storage path ({user_id}/folder/file.ext).
        file_obj: File-like object to upload.

    Returns:
        Created File instance.

    Raises:
        ValidationError: If storage path validation fails.
        Exception: If upload or DB operation fails.
    """
    # Validate storage path follows user isolation rules
    validate_storage_path(user.id, storage_path)

    # Extract filename from path
    filename = extract_filename(storage_path)

    # Calculate metadata
    logger.info('Calculating metadata for file: %s', storage_path)
    checksum = calculate_checksum(file_obj)
    mime_type = detect_mime_type(file_obj, filename)
    if hasattr(file_obj, 'size'):
        file_size = file_obj.size
    else:
        file_size = len(file_obj.read())
        file_obj.seek(0)  # Reset after reading for size

    # Initialize storage
    storage = _get_storage()

    # Step 1: Upload to storage first
    try:
        logger.info('Uploading file to storage: %s', storage_path)
        saved_name = storage.save(storage_path, file_obj)
        logger.info('File uploaded successfully: %s', saved_name)
    except Exception:
        logger.exception('Failed to upload file to storage: %s', storage_path)
        raise

    # Step 2: Create database record (in transaction)
    try:
        with transaction.atomic():
            file_instance = File.objects.create(
                user=user,
                file=saved_name,  # Use actual saved name from storage
                size_bytes=file_size,
                mime_type=mime_type,
                checksum_sha256=checksum,
            )
            logger.info(
                'File record created in database: %s (ID: %d)',
                saved_name,
                file_instance.id,
            )
            return file_instance
    except Exception:
        # Rollback: Delete file from storage since DB transaction failed
        logger.exception(
            'Database transaction failed, rolling back storage upload: %s',
            saved_name,
        )
        storage.rollback_upload(saved_name)
        raise


def delete_file(file_id: int) -> None:
    """Delete file from database and storage.

    Transaction safety: Delete DB record first. Storage deletion is handled
    automatically by the post_delete signal handler in signals.py.

    Args:
        file_id: ID of file to delete.

    Raises:
        File.DoesNotExist: If file doesn't exist.
        Exception: If DB deletion fails.
    """
    # Get file instance
    try:
        file_instance = File.objects.get(id=file_id)
    except File.DoesNotExist:
        logger.exception('File not found: ID=%d', file_id)
        raise

    storage_name = file_instance.file.name
    logger.info(
        'Deleting file: ID=%d, path=%s',
        file_id,
        storage_name,
    )

    # Delete from database - storage cleanup handled by post_delete signal
    try:
        with transaction.atomic():
            file_instance.delete()
            logger.info('File record deleted from database: ID=%d', file_id)
    except Exception:
        logger.exception('Failed to delete file from database: ID=%d', file_id)
        raise


def list_directory(user: User, folder_path: str = '') -> QuerySet[File]:
    """List files in a directory.

    Lists all files in the specified folder path for the user.
    Supports hierarchical folders.

    Args:
        user: Owner of files.
        folder_path: Folder path relative to user root (e.g., 'documents').
                    Empty string lists root directory.

    Returns:
        QuerySet of File objects in the directory.
    """
    # Construct full path
    if folder_path:
        full_path = '{user_id}/{folder}'.format(
            user_id=user.id,
            folder=folder_path.strip('/'),
        )
    else:
        full_path = str(user.id)

    logger.debug('Listing directory: %s', full_path)

    # Query files starting with this path
    # Use startswith to include files in subdirectories
    return File.objects.filter(
        user=user,
        file__startswith=full_path,
    ).select_related('user')


def get_folder_tree(user: User) -> dict[str, list[str]]:
    """Build folder hierarchy for user.

    Extracts implicit folder structure from storage paths.
    Returns a dictionary mapping folder paths to their subfolders.

    Args:
        user: Owner of files.

    Returns:
        Dictionary with folder paths as keys and lists of subfolders.
    """
    # Get all files for user
    files = File.objects.filter(user=user).values_list('file', flat=True)

    # Extract unique folder paths
    folders = set()
    for file_path in files:
        folder_path = file_path.rsplit('/', 1)[0]  # Remove filename
        folders.add(folder_path)

        # Also add parent folders
        parts = folder_path.split('/')
        for i in range(1, len(parts)):
            parent = '/'.join(parts[:i])
            folders.add(parent)

    # Build hierarchy
    folder_tree: dict[str, list[str]] = {folder: [] for folder in folders}

    for folder in sorted(folders):
        if '/' in folder:
            parent = folder.rsplit('/', 1)[0]
            if parent in folder_tree:
                folder_tree[parent].append(folder)

    return folder_tree


def get_file_by_path(user: User, storage_path: str) -> File:
    """Get file by its storage path.

    Args:
        user: Owner of the file.
        storage_path: Full storage path.

    Returns:
        File instance.

    Raises:
        File.DoesNotExist: If file not found.
    """
    return File.objects.get(user=user, file=storage_path)


def file_exists(user: User, storage_path: str) -> bool:
    """Check if a file exists at the given storage path.

    Args:
        user: Owner of the file.
        storage_path: Full storage path.

    Returns:
        True if file exists, False otherwise.
    """
    return File.objects.filter(user=user, file=storage_path).exists()


def folder_exists(user: User, folder_path: str) -> bool:
    """Check if a folder exists (has files with the given prefix).

    Since folders are implicit, a folder exists if any file has
    a path starting with the folder path.

    Args:
        user: Owner of files.
        folder_path: Folder path prefix.

    Returns:
        True if folder exists (has files), False otherwise.
    """
    prefix = folder_path.rstrip('/') + '/'
    return File.objects.filter(user=user, file__startswith=prefix).exists()


def move_file(user: User, old_path: str, new_path: str) -> File:
    """Move/rename a file by updating its storage path.

    This updates both the database record and the actual file in storage.

    Args:
        user: Owner of the file.
        old_path: Current storage path.
        new_path: New storage path.

    Returns:
        Updated File instance.

    Raises:
        File.DoesNotExist: If source file not found.
        ValidationError: If new path validation fails.
    """
    # Validate new path follows user isolation rules
    validate_storage_path(user.id, new_path)

    # Get the file
    file_instance = File.objects.get(user=user, file=old_path)
    storage = _get_storage()

    logger.info(
        'Moving file from %s to %s',
        old_path,
        new_path,
    )

    # Step 1: Copy file in storage
    try:
        old_file = file_instance.file.open('rb')
        storage.save(new_path, old_file)
        old_file.close()
        logger.info('File copied to new location: %s', new_path)
    except Exception:
        logger.exception('Failed to copy file in storage')
        raise

    # Step 2: Update database record
    try:
        with transaction.atomic():
            file_instance.file.name = new_path
            file_instance.save(update_fields=['file', 'modified_at'])
            logger.info('File record updated in database')
    except Exception:
        # Rollback: Delete the new copy
        logger.exception('Database update failed, rolling back storage copy')
        storage.rollback_upload(new_path)
        raise

    # Step 3: Delete old file from storage
    try:
        storage.delete(old_path)
        logger.info('Old file deleted from storage: %s', old_path)
    except Exception:
        # Log but don't raise - the move succeeded, old file is orphaned
        logger.exception(
            'Failed to delete old file (orphaned): %s',
            old_path,
        )

    return file_instance


def copy_file(user: User, source_path: str, dest_path: str) -> File:
    """Copy a file to a new location.

    Creates a new file with the same content at the destination path.

    Args:
        user: Owner of the file.
        source_path: Source storage path.
        dest_path: Destination storage path.

    Returns:
        New File instance for the copy.

    Raises:
        File.DoesNotExist: If source file not found.
        ValidationError: If destination path validation fails.
    """
    # Validate destination path follows user isolation rules
    validate_storage_path(user.id, dest_path)

    # Get source file
    source_file = File.objects.get(user=user, file=source_path)
    storage = _get_storage()

    logger.info(
        'Copying file from %s to %s',
        source_path,
        dest_path,
    )

    # Step 1: Copy file in storage
    try:
        file_content = source_file.file.open('rb')
        storage.save(dest_path, file_content)
        file_content.close()
        logger.info('File copied to storage: %s', dest_path)
    except Exception:
        logger.exception('Failed to copy file in storage')
        raise

    # Step 2: Create new database record
    try:
        with transaction.atomic():
            new_file = File.objects.create(
                user=user,
                file=dest_path,
                size_bytes=source_file.size_bytes,
                mime_type=source_file.mime_type,
                checksum_sha256=source_file.checksum_sha256,
            )
            # Copy tags from source file
            new_file.tags.set(source_file.tags.all())
            logger.info(
                'File record created: %s (ID: %d)',
                dest_path,
                new_file.id,
            )
            return new_file
    except Exception:
        # Rollback: Delete the copied file
        logger.exception('Database creation failed, rolling back storage copy')
        storage.rollback_upload(dest_path)
        raise


def update_file_content(
    file_id: int,
    file_obj: BinaryIO | DjangoFile,
) -> File:
    """Update file content atomically.

    Transaction safety: Upload new content first, then update DB record.
    If DB update fails, the new upload is deleted (rollback).
    Old content is deleted only after successful DB update.

    This prevents data loss if the upload fails - the original file
    remains intact until the new content is fully uploaded and
    the database is updated.

    Args:
        file_id: ID of file to update.
        file_obj: New file content.

    Returns:
        Updated File instance.

    Raises:
        File.DoesNotExist: If file not found.
        Exception: If upload or DB operation fails.
    """
    # Get existing file
    file_instance = File.objects.get(id=file_id)
    old_storage_path = file_instance.file.name
    storage = _get_storage()

    # Extract filename and calculate new metadata
    filename = extract_filename(old_storage_path)
    checksum = calculate_checksum(file_obj)
    mime_type = detect_mime_type(file_obj, filename)
    file_size = _get_file_size(file_obj)

    logger.info('Updating file content: %s (ID: %d)', old_storage_path, file_id)

    # Upload new content, update DB, cleanup old content
    _upload_and_update_file(
        file_instance,
        storage,
        old_storage_path,
        file_size,
        mime_type,
        checksum,
        file_obj,
    )

    return file_instance


def _get_file_size(file_obj: BinaryIO | DjangoFile) -> int:
    """Get file size from file object.

    Args:
        file_obj: File-like object.

    Returns:
        File size in bytes.
    """
    if hasattr(file_obj, 'size'):
        return file_obj.size
    file_size = len(file_obj.read())
    file_obj.seek(0)
    return file_size


def _upload_and_update_file(  # noqa: WPS211
    file_instance: File,
    storage: 'FileStorage',
    old_storage_path: str,
    file_size: int,
    mime_type: str,
    checksum: str,
    file_obj: BinaryIO | DjangoFile,
) -> None:
    """Upload new content and update file record atomically.

    Args:
        file_instance: File model instance to update.
        storage: Storage backend.
        old_storage_path: Current storage path.
        file_size: New file size.
        mime_type: New MIME type.
        checksum: New checksum.
        file_obj: New file content.
    """
    # Generate temporary path for new content
    temp_storage_path = f'{old_storage_path}.tmp'

    # Step 1: Upload new content to temporary path
    try:
        logger.debug('Uploading to temp path: %s', temp_storage_path)
        storage.save(temp_storage_path, file_obj)
    except Exception:
        logger.exception('Failed to upload: %s', temp_storage_path)
        raise

    # Step 2: Update database record atomically
    try:
        with transaction.atomic():
            file_instance.file.name = temp_storage_path
            file_instance.size_bytes = file_size
            file_instance.mime_type = mime_type
            file_instance.checksum_sha256 = checksum
            file_instance.save(update_fields=[
                'file',
                'size_bytes',
                'mime_type',
                'checksum_sha256',
                'modified_at',
            ])
    except Exception:
        logger.exception('DB update failed, rolling back')
        storage.rollback_upload(temp_storage_path)
        raise

    # Step 3: Delete old content from storage (best effort)
    try:
        storage.delete(old_storage_path)
    except Exception:
        logger.exception('Failed to delete old content: %s', old_storage_path)


def move_folder(user: User, old_prefix: str, new_prefix: str) -> int:
    """Move/rename a folder by updating all file paths with the prefix.

    Args:
        user: Owner of files.
        old_prefix: Current folder path prefix.
        new_prefix: New folder path prefix.

    Returns:
        Number of files moved.

    Raises:
        ValidationError: If new prefix validation fails.
    """
    # Validate new prefix follows user isolation rules
    validate_storage_path(user.id, new_prefix)

    old_prefix_normalized = old_prefix.rstrip('/') + '/'
    new_prefix_normalized = new_prefix.rstrip('/') + '/'

    logger.info(
        'Moving folder from %s to %s',
        old_prefix_normalized,
        new_prefix_normalized,
    )

    # Get all files with the old prefix
    files = File.objects.filter(
        user=user,
        file__startswith=old_prefix_normalized,
    )

    moved_count = 0
    for file_instance in files:
        # Calculate new path
        relative_path = file_instance.file.name[len(old_prefix_normalized):]
        new_path = new_prefix_normalized + relative_path

        try:
            move_file(user, file_instance.file.name, new_path)
            moved_count += 1
        except Exception:
            logger.exception(
                'Failed to move file: %s',
                file_instance.file.name,
            )
            raise

    logger.info(
        'Moved %d files from %s to %s',
        moved_count,
        old_prefix,
        new_prefix,
    )
    return moved_count
