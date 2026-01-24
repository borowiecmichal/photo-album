"""Session management for WebDAV connections.

Tracks active WebDAV sessions and enforces per-user limits.
"""

import logging
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from server.apps.webdav.models import WebDAVSession

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

# Session ID length in bytes (generates 32 hex chars)
_SESSION_ID_BYTES: Final = 16


def get_session_limit() -> int:
    """Get maximum concurrent sessions per user.

    Returns:
        Session limit from settings or default of 5.
    """
    return getattr(settings, 'WEBDAV_SESSION_LIMIT', 5)


def get_session_timeout() -> int:
    """Get session timeout in seconds.

    Returns:
        Timeout in seconds from settings or default of 1800 (30 min).
    """
    return getattr(settings, 'WEBDAV_SESSION_TIMEOUT', 1800)


def create_session(
    user: 'User',
    ip_address: str,
    user_agent: str = '',
) -> WebDAVSession:
    """Create a new WebDAV session for the user.

    Cleans stale sessions first, then checks if the user has
    exceeded their session limit.

    Args:
        user: Django user for the session.
        ip_address: Client IP address.
        user_agent: Client user agent string.

    Returns:
        Created WebDAVSession instance.

    Raises:
        SessionLimitExceeded: If user has too many active sessions.
    """
    # Clean stale sessions first
    cleanup_stale_sessions()

    with transaction.atomic():
        # Row-level locking prevents race condition when checking limit
        active_count = (
            WebDAVSession.objects.select_for_update()
            .filter(user=user)
            .count()
        )
        limit = get_session_limit()

        if active_count >= limit:
            logger.warning(
                'Session limit exceeded for user %s: %d/%d',
                user.username,
                active_count,
                limit,
            )
            raise SessionLimitExceededError(
                f'Maximum concurrent sessions ({limit}) exceeded',
            )

        # Generate unique session ID
        session_id = secrets.token_hex(_SESSION_ID_BYTES)

        # Create session
        session = WebDAVSession.objects.create(
            user=user,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent[:255],  # Truncate if needed
        )

        logger.info(
            'WebDAV session created for user %s: %s',
            user.username,
            session_id[:8],
        )

        return session


def update_session_activity(session_id: str) -> bool:
    """Update last activity timestamp for a session.

    Args:
        session_id: Session ID to update.

    Returns:
        True if session was found and updated, False otherwise.
    """
    updated = WebDAVSession.objects.filter(
        session_id=session_id,
    ).update(
        last_activity=timezone.now(),
    )

    return updated > 0


def end_session(session_id: str) -> bool:
    """End a WebDAV session.

    Args:
        session_id: Session ID to end.

    Returns:
        True if session was found and deleted, False otherwise.
    """
    deleted, _ = WebDAVSession.objects.filter(
        session_id=session_id,
    ).delete()

    if deleted:
        logger.info('WebDAV session ended: %s', session_id[:8])

    return deleted > 0


def cleanup_stale_sessions() -> int:
    """Remove sessions that have been inactive past the timeout.

    Returns:
        Number of sessions cleaned up.
    """
    timeout = get_session_timeout()
    cutoff = timezone.now() - timedelta(seconds=timeout)

    deleted, _ = WebDAVSession.objects.filter(
        last_activity__lt=cutoff,
    ).delete()

    if deleted:
        logger.info('Cleaned up %d stale WebDAV sessions', deleted)

    return deleted


def get_user_sessions(user: 'User') -> list[WebDAVSession]:
    """Get all active sessions for a user.

    Args:
        user: User to get sessions for.

    Returns:
        List of active WebDAVSession instances.
    """
    return list(
        WebDAVSession.objects.filter(user=user).order_by('-last_activity'),
    )


def get_session(session_id: str) -> WebDAVSession | None:
    """Get a session by ID.

    Args:
        session_id: Session ID to look up.

    Returns:
        WebDAVSession if found, None otherwise.
    """
    try:
        return WebDAVSession.objects.get(session_id=session_id)
    except WebDAVSession.DoesNotExist:
        return None


class SessionLimitExceededError(Exception):
    """Raised when user exceeds maximum concurrent sessions."""
