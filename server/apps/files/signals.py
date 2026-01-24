"""Signal handlers for files app."""

import logging

from django.core.files.storage import default_storage
from django.db.models.signals import post_delete
from django.dispatch import receiver

from server.apps.files.models import File

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=File)
def delete_file_from_storage(
    sender: type[File],
    instance: File,
    **kwargs: object,
) -> None:
    """Delete file from storage when File record is deleted.

    This signal handler ensures that when a File record is deleted
    (via admin, ORM, or any other method), the actual file in S3
    storage is also cleaned up.

    Args:
        sender: The File model class.
        instance: The File instance being deleted.
        **kwargs: Additional signal arguments.
    """
    if not instance.file:
        return

    storage_name = instance.file.name
    logger.info(
        'Deleting file from storage after DB delete: %s',
        storage_name,
    )

    try:
        if default_storage.exists(storage_name):
            default_storage.delete(storage_name)
            logger.info('File deleted from storage: %s', storage_name)
        else:
            logger.warning(
                'File not found in storage (already deleted?): %s',
                storage_name,
            )
    except Exception:
        # Log error but don't raise - DB delete already succeeded
        # Orphaned file can be cleaned up by background job
        logger.exception(
            'Failed to delete file from storage (orphaned): %s',
            storage_name,
        )
