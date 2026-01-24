"""Database models for files app."""

from pathlib import Path
from typing import Final, final, override

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

# Constants for field max lengths
_MIME_TYPE_MAX_LENGTH: Final = 255
_CHECKSUM_MAX_LENGTH: Final = 64  # SHA256 hex length
_TAG_NAME_MAX_LENGTH: Final = 100
_TAG_COLOR_MAX_LENGTH: Final = 7  # Hex color: #RRGGBB


@final
class File(models.Model):
    """File stored in S3-compatible storage.

    Each file belongs to a user and has a path in storage following
    the pattern: {user_id}/folder/subfolder/filename.ext

    The file path serves as both the storage key and the hierarchical
    organization structure (no separate Folder model).
    """

    # Owner relationship
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='files',
        db_index=True,
    )

    # File stored in S3-compatible storage
    # upload_to='' means we control the full path
    file = models.FileField(
        upload_to='',
        help_text='Path in storage: {user_id}/folder/file.ext',
    )

    # File metadata (cached for performance)
    size_bytes = models.BigIntegerField(
        help_text='File size in bytes',
    )

    mime_type = models.CharField(
        max_length=_MIME_TYPE_MAX_LENGTH,
        help_text='MIME type detected via python-magic',
    )

    checksum_sha256 = models.CharField(
        max_length=_CHECKSUM_MAX_LENGTH,
        help_text='SHA256 hash for integrity verification',
        db_index=True,
    )

    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    # Tags relationship (Phase 2+)
    tags = models.ManyToManyField(
        'Tag',
        related_name='files',
        blank=True,
    )

    class Meta:
        """Model metadata."""

        verbose_name = 'File'  # type: ignore[mutable-override]
        verbose_name_plural = 'Files'  # type: ignore[mutable-override]
        ordering = ['-uploaded_at']

        indexes = [
            # Optimize directory listing queries
            models.Index(
                fields=['user', 'file'],
                name='files_user_file_idx',
            ),
            # Optimize recent files queries
            models.Index(
                fields=['user', '-uploaded_at'],
                name='files_user_recent_idx',
            ),
        ]

        constraints = [
            # Prevent duplicate file paths for the same user
            models.UniqueConstraint(
                fields=['user', 'file'],
                name='files_user_path_unique',
            ),
        ]

    @override
    def __str__(self) -> str:
        """String representation."""
        return f'{self.user.username}:{self.file.name}'

    def get_folder_path(self) -> str:
        """Extract folder path from file.name.

        Example: '123/documents/reports/file.pdf' -> '123/documents/reports'

        Returns:
            Folder path (parent directory of file).
        """
        return str(Path(self.file.name).parent)

    def get_filename(self) -> str:
        """Extract filename from file.name.

        Example: '123/documents/reports/file.pdf' -> 'file.pdf'

        Returns:
            Filename without path.
        """
        return Path(self.file.name).name

    def get_extension(self) -> str:
        """Extract file extension.

        Example: 'file.pdf' -> 'pdf'

        Returns:
            Extension without dot (lowercase).
        """
        extension = Path(self.file.name).suffix
        return extension.lstrip('.').lower()

    def get_url(self) -> str:
        """Get download URL for file.

        Returns:
            Full URL to access file via storage backend.
        """
        return self.file.url


@final
class Tag(models.Model):
    """User-defined tag for organizing files.

    Tags are scoped to individual users to prevent naming conflicts
    and maintain user isolation.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tags',
        db_index=True,
    )

    name = models.CharField(
        max_length=_TAG_NAME_MAX_LENGTH,
    )

    color = models.CharField(
        max_length=_TAG_COLOR_MAX_LENGTH,
        blank=True,
        default='',
        help_text='Hex color code for UI display (e.g., #FF5733)',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Model metadata."""

        verbose_name = 'Tag'  # type: ignore[mutable-override]
        verbose_name_plural = 'Tags'  # type: ignore[mutable-override]
        ordering = ['name']

        constraints = [
            # Ensure tag names are unique per user
            models.UniqueConstraint(
                fields=['user', 'name'],
                name='tags_user_name_unique',
            ),
        ]

        indexes = [
            models.Index(
                fields=['user', 'name'],
                name='tags_user_name_idx',
            ),
        ]

    @override
    def __str__(self) -> str:
        """String representation."""
        return f'{self.user.username}:{self.name}'


# Default quota: 10 GB in bytes
_DEFAULT_QUOTA_BYTES: Final = 10 * 1024 * 1024 * 1024


@final
class UserQuota(models.Model):
    """Storage quota for a user.

    Tracks user's storage limit and current usage. Quota includes all files
    including soft-deleted files (trash) to prevent circumventing limits.

    When over quota, users can still read and delete files, but uploads
    are blocked until usage falls below the limit.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='quota',
        primary_key=True,
    )

    quota_bytes = models.BigIntegerField(
        default=_DEFAULT_QUOTA_BYTES,
        help_text='Storage quota limit in bytes',
    )

    used_bytes = models.BigIntegerField(
        default=0,
        help_text='Currently used storage in bytes',
    )

    class Meta:
        """Model metadata."""

        verbose_name = 'User Quota'  # type: ignore[mutable-override]
        verbose_name_plural = 'User Quotas'  # type: ignore[mutable-override]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(quota_bytes__gte=0),
                name='quota_bytes_non_negative',
            ),
            models.CheckConstraint(
                condition=models.Q(used_bytes__gte=0),
                name='used_bytes_non_negative',
            ),
        ]

    @override
    def __str__(self) -> str:
        """String representation."""
        return f'{self.user.username}: {self.used_bytes}/{self.quota_bytes}'

    def has_space_for(self, size_bytes: int) -> bool:
        """Check if there's enough space for the given size.

        Args:
            size_bytes: Size to check in bytes.

        Returns:
            True if there's enough space, False otherwise.
        """
        return self.used_bytes + size_bytes <= self.quota_bytes

    def available_bytes(self) -> int:
        """Get available storage space.

        Returns:
            Available bytes (never negative).
        """
        available = self.quota_bytes - self.used_bytes
        return max(0, available)
