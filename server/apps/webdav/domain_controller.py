"""WsgiDAV domain controller for Django authentication.

This module provides authentication for WebDAV requests using Django's
authentication system. It validates HTTP Basic Auth credentials against
Django's User model.
"""

import logging
from typing import TYPE_CHECKING, Final, final, override

from django.contrib.auth import authenticate
from django.core.handlers.wsgi import WSGIRequest
from wsgidav.dc.base_dc import BaseDomainController

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

# Key to store authenticated user in WSGI environ
ENVIRON_USER_KEY: Final = 'webdav.user'


@final
class DjangoDomainController(BaseDomainController):
    """WsgiDAV domain controller using Django authentication.

    Authenticates WebDAV requests using HTTP Basic Auth credentials
    validated against Django's User model.

    Stores the authenticated Django User object in the WSGI environ
    for access by the DAV provider.
    """

    @override
    def __init__(self, wsgidav_app: object, config: dict) -> None:
        """Initialize the domain controller.

        Args:
            wsgidav_app: WsgiDAV application instance.
            config: WsgiDAV configuration dictionary.
        """
        super().__init__(wsgidav_app, config)
        self._realm = 'Photo Album'

    def get_domain_realm(
        self,
        path_info: str,
        environ: dict,
    ) -> str:
        """Return the realm name for authentication.

        Args:
            path_info: Request path.
            environ: WSGI environ dictionary.

        Returns:
            Realm name for WWW-Authenticate header.
        """
        return self._realm

    def require_authentication(
        self,
        realm_name: str,
        environ: dict,
    ) -> bool:
        """Check if authentication is required for this request.

        All WebDAV paths require authentication in our system.

        Args:
            realm_name: Realm name for authentication.
            environ: WSGI environ dictionary.

        Returns:
            Always True - authentication is required for all paths.
        """
        return True

    def basic_auth_user(
        self,
        realm_name: str,
        user_name: str,
        password: str,
        environ: dict,
    ) -> bool:
        """Authenticate user with HTTP Basic Auth credentials.

        Validates credentials against Django's authentication system
        and stores the authenticated user in the WSGI environ.

        Args:
            realm_name: Realm name.
            user_name: Username from Basic Auth.
            password: Password from Basic Auth.
            environ: WSGI environ dictionary.

        Returns:
            True if authentication succeeded, False otherwise.
        """
        logger.debug('Authenticating user: %s', user_name)

        # Create Django request from WSGI environ for django-axes compatibility
        request = WSGIRequest(environ)

        # Authenticate using Django
        user: User | None = authenticate(
            request=request,
            username=user_name,
            password=password,
        )

        if user is None:
            logger.warning('Authentication failed for user: %s', user_name)
            return False

        if not user.is_active:
            logger.warning('Inactive user attempted login: %s', user_name)
            return False

        # Store authenticated user in environ for provider access
        environ[ENVIRON_USER_KEY] = user
        logger.info('User authenticated successfully: %s', user_name)

        return True

    def supports_http_digest_auth(self) -> bool:
        """Check if HTTP Digest authentication is supported.

        We only support Basic Auth for simplicity.

        Returns:
            False - only Basic Auth is supported.
        """
        return False
