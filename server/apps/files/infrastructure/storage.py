"""Custom storage backend for S3-compatible storage."""

import logging
from typing import Any, final, override

from storages.backends.s3 import S3Storage

logger = logging.getLogger(__name__)


@final
class FileStorage(S3Storage):
    """Custom S3 storage backend for user files.

    Extends django-storages S3Storage with:
    - Transaction rollback support for failed DB operations
    - Enhanced error logging
    - Future: metrics, caching, CDN integration
    """

    @override
    def save(  # noqa: WPS211
        self,
        name: str,
        content: Any,
        max_length: int | None = None,
    ) -> str:
        """Save file to S3 with error handling and logging.

        Args:
            name: Storage path for the file.
            content: File content (file-like object).
            max_length: Optional maximum length for the filename.

        Returns:
            Actual storage path used (may differ from name if conflicts).

        Raises:
            Exception: If S3 upload fails.
        """
        try:
            logger.info('Uploading file to storage: %s', name)
            saved_name = super().save(name, content, max_length)
            logger.info('Successfully uploaded file: %s', saved_name)
        except Exception:
            logger.exception('Failed to upload file to storage: %s', name)
            raise
        else:
            return saved_name

    @override
    def delete(self, name: str) -> None:
        """Delete file from S3 with error handling and logging.

        Args:
            name: Storage path of file to delete.

        Raises:
            Exception: If S3 delete fails.
        """
        try:
            logger.info('Deleting file from storage: %s', name)
            super().delete(name)
            logger.info('Successfully deleted file: %s', name)
        except Exception:
            logger.exception('Failed to delete file from storage: %s', name)
            raise

    def rollback_upload(self, name: str) -> None:
        """Delete uploaded file for DB transaction rollback.

        This method is called when a database transaction fails after
        a file has been successfully uploaded to S3. It attempts to
        delete the file to maintain consistency.

        This is a best-effort operation - if deletion fails, the error
        is logged but not raised, as the DB rollback has already occurred.

        Args:
            name: Storage path of file to delete.
        """
        try:
            logger.warning('Rolling back upload, deleting file: %s', name)
            self.delete(name)
            logger.info('Successfully rolled back file upload: %s', name)
        except Exception:
            # Log but don't raise - rollback is best-effort
            # The file will remain in storage but not in database
            # A cleanup job can handle orphaned files
            logger.exception(
                'Failed to rollback upload, orphaned file: %s',
                name,
            )

    def move_object(self, source: str, destination: str) -> None:
        """Move/rename an object in S3 storage.

        S3 doesn't support native rename, so this performs a server-side
        copy followed by deletion of the source.

        Note: This operation is not atomic. If copy succeeds but delete
        fails, both files will exist (source becomes orphaned). This is
        acceptable as orphaned files can be cleaned up by a maintenance
        job, and no data is lost.

        Args:
            source: Source storage path.
            destination: Destination storage path.

        Raises:
            Exception: If copy or delete fails.
        """
        try:
            logger.info('Moving file: %s -> %s', source, destination)
            # Server-side copy using boto3
            copy_source = {
                'Bucket': self.bucket_name,
                'Key': source,
            }
            self.bucket.copy(copy_source, destination)
            # Delete source after successful copy
            self.delete(source)
            logger.info('Moved file: %s -> %s', source, destination)
        except Exception:
            logger.exception('Move failed: %s -> %s', source, destination)
            raise
