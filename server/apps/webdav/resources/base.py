"""Base utilities for WebDAV resources."""

from typing import TYPE_CHECKING

from server.apps.webdav.domain_controller import ENVIRON_USER_KEY

if TYPE_CHECKING:
    from django.contrib.auth.models import User


def get_user_from_environ(environ: dict) -> 'User':
    """Get authenticated Django user from WSGI environ.

    Args:
        environ: WSGI environ dictionary.

    Returns:
        Authenticated Django User object.

    Raises:
        KeyError: If user is not in environ (should not happen
                  if domain controller is working correctly).
    """
    return environ[ENVIRON_USER_KEY]
