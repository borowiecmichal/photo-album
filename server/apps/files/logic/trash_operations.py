"""Business logic for trash (soft delete) operations."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from server.apps.files.logic.quota_operations import decrement_usage
from server.apps.files.models import File

# User type for Django's dynamic user model
_User = Any

logger = logging.getLogger(__name__)


def _generate_trash_name(storage_path: str) -> str:
    """Generate unique trash filename with timestamp.

    Args:
        storage_path: Original storage path (e.g., '123/docs/report.pdf').

    Returns:
        Trash name with timestamp (e.g., 'report__20260131T143052123456.pdf').
    """
    path = Path(storage_path)
    stem = path.stem
    suffix = path.suffix
    timestamp = datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%S%f')
    return f'{stem}__{timestamp}{suffix}'


def soft_delete_file(file_id: int) -> File:
    """Move file to trash (soft delete).

    Sets is_deleted=True and records original path for restore.
    Quota is NOT decremented - trash files count toward quota.

    Args:
        file_id: ID of file to soft delete.

    Returns:
        Updated File instance.

    Raises:
        File.DoesNotExist: If file not found.
    """
    file_instance = File.objects.get(id=file_id)
    original_path = file_instance.file.name

    # Generate unique trash name
    trash_name = _generate_trash_name(original_path)

    # Update file record
    file_instance.is_deleted = True
    file_instance.deleted_at = timezone.now()
    file_instance.original_path = original_path
    file_instance.trash_name = trash_name
    file_instance.save(update_fields=[
        'is_deleted',
        'deleted_at',
        'original_path',
        'trash_name',
        'modified_at',
    ])

    logger.info(
        'File moved to trash: %s -> %s (ID: %d)',
        original_path,
        trash_name,
        file_id,
    )

    return file_instance


def restore_file(file_id: int, destination_path: str | None = None) -> File:
    """Restore file from trash.

    Args:
        file_id: ID of file to restore.
        destination_path: Optional new storage path. If None, restores to
            original_path.

    Returns:
        Updated File instance.

    Raises:
        File.DoesNotExist: If file not found or not in trash.
    """
    file_instance = File.all_objects.get(id=file_id, is_deleted=True)
    user = file_instance.user
    original_storage_path = file_instance.original_path

    # Determine target path
    target_path = destination_path or original_storage_path

    # Check for conflict at target path
    if File.objects.filter(user=user, file=target_path).exists():
        # Auto-rename with (restored) suffix
        path = Path(target_path)
        stem = path.stem
        suffix = path.suffix
        parent = str(path.parent)
        new_name = f'{stem} (restored){suffix}'
        target_path = f'{parent}/{new_name}'

        logger.info(
            'Restore conflict, renamed to: %s',
            target_path,
        )

    # Ensure parent folder marker exists (auto-create)
    _ensure_parent_folder(user, target_path)

    # Get trash name for logging before clearing
    trash_name = file_instance.trash_name

    # Get current storage location (where S3 file actually is)
    current_storage_path = file_instance.file.name

    # Determine if we need to move the S3 file
    needs_move = target_path != current_storage_path

    if needs_move:
        # First move the file in S3 to target path, then update DB
        from server.apps.files.logic.file_operations import move_file

        # Temporarily clear deletion flags so move_file works
        file_instance.is_deleted = False
        file_instance.deleted_at = None
        file_instance.original_path = ''
        file_instance.trash_name = ''
        file_instance.save(update_fields=[
            'is_deleted',
            'deleted_at',
            'original_path',
            'trash_name',
            'modified_at',
        ])

        # Move the file from current location to target (updates file.name)
        file_instance = move_file(user, current_storage_path, target_path)
    else:
        # No move needed, just restore to original path
        file_instance.is_deleted = False
        file_instance.deleted_at = None
        file_instance.original_path = ''
        file_instance.trash_name = ''
        file_instance.save(update_fields=[
            'is_deleted',
            'deleted_at',
            'original_path',
            'trash_name',
            'modified_at',
        ])

    logger.info(
        'File restored: %s -> %s (ID: %d)',
        trash_name,
        target_path,
        file_id,
    )

    return file_instance


def _ensure_parent_folder(user: _User, storage_path: str) -> None:
    """Ensure parent folder marker exists for a path.

    Creates .folder marker files for any missing parent folders.

    Args:
        user: File owner.
        storage_path: Target storage path.
    """
    from django.core.files.base import ContentFile

    from server.apps.files.logic.file_operations import file_exists, upload_file

    path = Path(storage_path)
    parent = str(path.parent)

    # Only create markers for non-root folders
    user_root = str(user.id)
    if parent == user_root:
        return

    marker_path = f'{parent}/.folder'

    # Check if marker already exists
    if file_exists(user, marker_path):
        return

    # Check if any file exists in parent folder
    if File.objects.filter(
        user=user,
        file__startswith=f'{parent}/',
    ).exists():
        return

    # Create marker file
    logger.debug('Creating folder marker: %s', marker_path)
    marker_content = ContentFile(b'')
    upload_file(user, marker_path, marker_content)


def permanent_delete_file(file_id: int) -> None:
    """Permanently delete file from trash.

    Removes file from database and S3, decrements quota.

    Args:
        file_id: ID of file to permanently delete.

    Raises:
        File.DoesNotExist: If file not found or not in trash.
    """
    file_instance = File.all_objects.get(id=file_id, is_deleted=True)
    file_size = file_instance.size_bytes
    file_user = file_instance.user
    trash_name = file_instance.trash_name

    with transaction.atomic():
        # Delete triggers post_delete signal for S3 cleanup
        file_instance.delete()
        # Decrement quota
        decrement_usage(file_user, file_size)

    logger.info(
        'File permanently deleted: %s (ID: %d, size: %d)',
        trash_name,
        file_id,
        file_size,
    )


def list_trash(user: _User) -> QuerySet[File]:
    """List all files in user's trash.

    Args:
        user: User whose trash to list.

    Returns:
        QuerySet of deleted files, newest first.
    """
    return File.all_objects.filter(
        user=user,
        is_deleted=True,
    ).order_by('-deleted_at')


def empty_trash(user: _User) -> int:
    """Permanently delete all files in user's trash.

    Args:
        user: User whose trash to empty.

    Returns:
        Number of files deleted.
    """
    trash_files = list(list_trash(user))
    count = 0

    for file_instance in trash_files:
        try:
            permanent_delete_file(file_instance.id)
            count += 1
        except Exception:
            logger.exception(
                'Failed to permanently delete file: %d',
                file_instance.id,
            )
            raise

    logger.info(
        'Trash emptied for user %s: %d files deleted',
        user.username,
        count,
    )

    return count


def get_trash_file_by_name(user: _User, trash_name: str) -> File:
    """Get trash file by its unique trash name.

    Args:
        user: File owner.
        trash_name: Unique trash filename.

    Returns:
        File instance.

    Raises:
        File.DoesNotExist: If file not found.
    """
    return File.all_objects.get(
        user=user,
        is_deleted=True,
        trash_name=trash_name,
    )
