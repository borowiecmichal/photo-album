"""Tests for WebDAV domain controller authentication."""

from io import BytesIO

import pytest

from server.apps.webdav.domain_controller import (
    ENVIRON_USER_KEY,
    DjangoDomainController,
)


@pytest.fixture
def domain_controller():
    """Create domain controller instance.

    Returns:
        DjangoDomainController instance.
    """
    # Create minimal controller without full WsgiDAV app
    controller = DjangoDomainController.__new__(DjangoDomainController)
    controller._realm = 'Photo Album'
    return controller


@pytest.fixture
def minimal_environ():
    """Create minimal WSGI environ for WSGIRequest.

    Returns:
        Dict with minimal WSGI environ keys.
    """
    return {
        'REQUEST_METHOD': 'GET',
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '8080',
        'wsgi.input': BytesIO(b''),
    }


class TestDjangoDomainController:
    """Tests for DjangoDomainController."""

    def test_get_domain_realm(self, domain_controller):
        """Test realm name is returned."""
        environ = {}

        realm = domain_controller.get_domain_realm('/path', environ)

        assert realm == 'Photo Album'

    def test_require_authentication_always_true(self, domain_controller):
        """Test that authentication is always required."""
        environ = {}

        result = domain_controller.require_authentication('Photo Album', environ)

        assert result is True

    def test_supports_http_digest_auth_false(self, domain_controller):
        """Test that digest auth is not supported."""
        result = domain_controller.supports_http_digest_auth()

        assert result is False

    @pytest.mark.django_db
    def test_basic_auth_user_success(
        self,
        domain_controller,
        user,
        minimal_environ,
    ):
        """Test successful authentication."""
        result = domain_controller.basic_auth_user(
            realm_name='Photo Album',
            user_name='testuser',
            password='testpass123',
            environ=minimal_environ,
        )

        assert result is True
        assert ENVIRON_USER_KEY in minimal_environ
        assert minimal_environ[ENVIRON_USER_KEY].username == 'testuser'

    @pytest.mark.django_db
    def test_basic_auth_user_wrong_password(
        self,
        domain_controller,
        user,
        minimal_environ,
    ):
        """Test authentication fails with wrong password."""
        result = domain_controller.basic_auth_user(
            realm_name='Photo Album',
            user_name='testuser',
            password='wrongpassword',
            environ=minimal_environ,
        )

        assert result is False
        assert ENVIRON_USER_KEY not in minimal_environ

    @pytest.mark.django_db
    def test_basic_auth_user_nonexistent(
        self,
        domain_controller,
        minimal_environ,
    ):
        """Test authentication fails for nonexistent user."""
        result = domain_controller.basic_auth_user(
            realm_name='Photo Album',
            user_name='nonexistent',
            password='password',
            environ=minimal_environ,
        )

        assert result is False
        assert ENVIRON_USER_KEY not in minimal_environ

    @pytest.mark.django_db
    def test_basic_auth_user_inactive(
        self,
        domain_controller,
        user,
        minimal_environ,
    ):
        """Test authentication fails for inactive user."""
        # Make user inactive
        user.is_active = False
        user.save()

        result = domain_controller.basic_auth_user(
            realm_name='Photo Album',
            user_name='testuser',
            password='testpass123',
            environ=minimal_environ,
        )

        assert result is False
        assert ENVIRON_USER_KEY not in minimal_environ
