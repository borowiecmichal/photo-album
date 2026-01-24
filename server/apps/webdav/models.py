"""Database models for WebDAV session management."""

from typing import ClassVar, Final, final, override

from django.conf import settings
from django.db import models

# Constants for field max lengths
_SESSION_ID_MAX_LENGTH: Final = 64
_USER_AGENT_MAX_LENGTH: Final = 255


@final
class WebDAVSession(models.Model):
    """Active WebDAV session for tracking concurrent connections.

    Used to enforce per-user session limits and track active
    WebDAV connections from native file browsers.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='webdav_sessions',
        db_index=True,
    )

    session_id = models.CharField(
        max_length=_SESSION_ID_MAX_LENGTH,
        unique=True,
        help_text='Unique session identifier',
    )

    ip_address = models.GenericIPAddressField(
        help_text='Client IP address',
    )

    user_agent = models.CharField(
        max_length=_USER_AGENT_MAX_LENGTH,
        blank=True,
        default='',
        help_text='Client user agent string',
    )

    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Session start time',
    )

    last_activity = models.DateTimeField(
        auto_now=True,
        db_index=True,
        help_text='Last activity timestamp',
    )

    class Meta:
        """Model metadata."""

        verbose_name = 'WebDAV Session'  # type: ignore[mutable-override]
        verbose_name_plural = 'WebDAV Sessions'  # type: ignore[mutable-override]
        ordering: ClassVar[list[str]] = ['-last_activity']

        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=['user', '-last_activity'],
                name='webdav_user_activity_idx',
            ),
        ]

    @override
    def __str__(self) -> str:
        """String representation."""
        return f'{self.user.username}@{self.ip_address} ({self.session_id[:8]})'
