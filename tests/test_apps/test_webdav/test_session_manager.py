"""Tests for WebDAV session management."""

from datetime import timedelta

import pytest
from django.utils import timezone

from server.apps.webdav.logic.session_manager import (
    SessionLimitExceededError,
    cleanup_stale_sessions,
    create_session,
    end_session,
    get_session,
    get_session_limit,
    get_session_timeout,
    get_user_sessions,
    update_session_activity,
)
from server.apps.webdav.models import WebDAVSession


class TestSessionManagerConfig:
    """Tests for session configuration."""

    def test_get_session_limit_default(self, settings):
        """Test default session limit."""
        # Remove setting if exists
        if hasattr(settings, 'WEBDAV_SESSION_LIMIT'):
            delattr(settings, 'WEBDAV_SESSION_LIMIT')

        limit = get_session_limit()

        assert limit == 5

    def test_get_session_limit_from_settings(self, settings):
        """Test session limit from settings."""
        settings.WEBDAV_SESSION_LIMIT = 10

        limit = get_session_limit()

        assert limit == 10

    def test_get_session_timeout_default(self, settings):
        """Test default session timeout."""
        if hasattr(settings, 'WEBDAV_SESSION_TIMEOUT'):
            delattr(settings, 'WEBDAV_SESSION_TIMEOUT')

        timeout = get_session_timeout()

        assert timeout == 1800  # 30 minutes

    def test_get_session_timeout_from_settings(self, settings):
        """Test session timeout from settings."""
        settings.WEBDAV_SESSION_TIMEOUT = 3600

        timeout = get_session_timeout()

        assert timeout == 3600


class TestCreateSession:
    """Tests for session creation."""

    @pytest.mark.django_db
    def test_create_session_success(self, user):
        """Test successful session creation."""
        session = create_session(
            user=user,
            ip_address='192.168.1.1',
            user_agent='Finder/1.0',
        )

        assert session.id is not None
        assert session.user == user
        assert session.ip_address == '192.168.1.1'
        assert session.user_agent == 'Finder/1.0'
        assert len(session.session_id) == 32  # 16 bytes = 32 hex chars

    @pytest.mark.django_db
    def test_create_session_limit_exceeded(self, user, settings):
        """Test session limit enforcement."""
        settings.WEBDAV_SESSION_LIMIT = 2

        # Create sessions up to limit
        create_session(user, '192.168.1.1', 'Agent1')
        create_session(user, '192.168.1.2', 'Agent2')

        # Third session should fail
        with pytest.raises(SessionLimitExceededError):
            create_session(user, '192.168.1.3', 'Agent3')

    @pytest.mark.django_db
    def test_create_session_different_users(self, user, other_user, settings):
        """Test that session limits are per-user."""
        settings.WEBDAV_SESSION_LIMIT = 2

        # Create sessions for first user
        create_session(user, '192.168.1.1', 'Agent1')
        create_session(user, '192.168.1.2', 'Agent2')

        # Second user should be able to create sessions
        session = create_session(other_user, '192.168.1.3', 'Agent3')

        assert session.user == other_user

    @pytest.mark.django_db
    def test_create_session_truncates_user_agent(self, user):
        """Test that long user agents are truncated."""
        long_agent = 'A' * 500

        session = create_session(user, '192.168.1.1', long_agent)

        assert len(session.user_agent) == 255


class TestUpdateSessionActivity:
    """Tests for session activity updates."""

    @pytest.mark.django_db
    def test_update_session_activity_success(self, user):
        """Test updating session activity."""
        session = create_session(user, '192.168.1.1')
        original_activity = session.last_activity

        # Update activity
        result = update_session_activity(session.session_id)

        # Reload from DB
        session.refresh_from_db()

        assert result is True
        assert session.last_activity >= original_activity

    @pytest.mark.django_db
    def test_update_session_activity_not_found(self):
        """Test updating nonexistent session."""
        result = update_session_activity('nonexistent-session-id')

        assert result is False


class TestEndSession:
    """Tests for session termination."""

    @pytest.mark.django_db
    def test_end_session_success(self, user):
        """Test ending a session."""
        session = create_session(user, '192.168.1.1')
        session_id = session.session_id

        result = end_session(session_id)

        assert result is True
        assert not WebDAVSession.objects.filter(session_id=session_id).exists()

    @pytest.mark.django_db
    def test_end_session_not_found(self):
        """Test ending nonexistent session."""
        result = end_session('nonexistent-session-id')

        assert result is False


class TestCleanupStaleSessions:
    """Tests for stale session cleanup."""

    @pytest.mark.django_db
    def test_cleanup_stale_sessions(self, user, settings):
        """Test that stale sessions are cleaned up."""
        settings.WEBDAV_SESSION_TIMEOUT = 1800  # 30 minutes

        # Create a session
        session = create_session(user, '192.168.1.1')

        # Make it stale by updating last_activity directly
        stale_time = timezone.now() - timedelta(seconds=3600)  # 1 hour ago
        WebDAVSession.objects.filter(id=session.id).update(
            last_activity=stale_time,
        )

        # Cleanup
        deleted = cleanup_stale_sessions()

        assert deleted == 1
        assert not WebDAVSession.objects.filter(id=session.id).exists()

    @pytest.mark.django_db
    def test_cleanup_keeps_active_sessions(self, user, settings):
        """Test that active sessions are not cleaned up."""
        settings.WEBDAV_SESSION_TIMEOUT = 1800

        # Create an active session
        session = create_session(user, '192.168.1.1')

        # Cleanup
        deleted = cleanup_stale_sessions()

        assert deleted == 0
        assert WebDAVSession.objects.filter(id=session.id).exists()


class TestGetUserSessions:
    """Tests for getting user sessions."""

    @pytest.mark.django_db
    def test_get_user_sessions(self, user):
        """Test getting all sessions for a user."""
        create_session(user, '192.168.1.1', 'Agent1')
        create_session(user, '192.168.1.2', 'Agent2')

        sessions = get_user_sessions(user)

        assert len(sessions) == 2

    @pytest.mark.django_db
    def test_get_user_sessions_empty(self, user):
        """Test getting sessions when user has none."""
        sessions = get_user_sessions(user)

        assert sessions == []

    @pytest.mark.django_db
    def test_get_user_sessions_isolation(self, user, other_user):
        """Test that only user's sessions are returned."""
        create_session(user, '192.168.1.1', 'Agent1')
        create_session(other_user, '192.168.1.2', 'Agent2')

        sessions = get_user_sessions(user)

        assert len(sessions) == 1
        assert sessions[0].user == user


class TestGetSession:
    """Tests for getting a session by ID."""

    @pytest.mark.django_db
    def test_get_session_exists(self, user):
        """Test getting existing session."""
        created = create_session(user, '192.168.1.1')

        session = get_session(created.session_id)

        assert session is not None
        assert session.id == created.id

    @pytest.mark.django_db
    def test_get_session_not_found(self):
        """Test getting nonexistent session."""
        session = get_session('nonexistent-session-id')

        assert session is None
