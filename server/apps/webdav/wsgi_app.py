"""WSGI application factory for WebDAV server.

Creates a configured WsgiDAV application that integrates with Django.
"""

import logging
from typing import Any

from wsgidav import wsgidav_app

from server.apps.webdav.dav_provider import DjangoDAVProvider
from server.apps.webdav.domain_controller import DjangoDomainController

logger = logging.getLogger(__name__)


def create_webdav_app(
    verbose: int = 3,
) -> wsgidav_app.WsgiDAVApp:
    """Create configured WsgiDAV WSGI application.

    Creates and configures a WsgiDAV application with:
    - DjangoDAVProvider for file operations
    - DjangoDomainController for authentication
    - HTTP Basic authentication

    Args:
        verbose: Logging verbosity level (0-5).

    Returns:
        Configured WsgiDAV WSGI application.
    """
    config: dict[str, Any] = {
        'provider_mapping': {
            '/': DjangoDAVProvider(),
        },
        'http_authenticator': {
            'domain_controller': DjangoDomainController,
            'accept_basic': True,
            'accept_digest': False,
            'default_to_digest': False,
        },
        'verbose': verbose,
        'logging': {
            'enable': True,
            'enable_loggers': ['wsgidav'],
        },
        # Disable directory browsing HTML interface
        'dir_browser': {
            'enable': False,
        },
        # Enable lock manager for DAV Class 2 compliance
        # Required for macOS Finder write support
        'lock_storage': True,
        # Property manager (in-memory)
        'property_manager': True,
    }

    logger.info('Creating WsgiDAV application with Django integration')

    return wsgidav_app.WsgiDAVApp(config)


def get_webdav_app() -> wsgidav_app.WsgiDAVApp:
    """Get or create the WebDAV WSGI application.

    This is a convenience function for getting the application instance.

    Returns:
        WsgiDAV WSGI application.
    """
    return create_webdav_app()
