"""WebDAV server settings."""

from server.settings.components import config

# WebDAV server host and port
WEBDAV_HOST = config('WEBDAV_HOST', default='0.0.0.0')
WEBDAV_PORT = config('WEBDAV_PORT', cast=int, default=8080)

# Session management
WEBDAV_SESSION_LIMIT = config('WEBDAV_SESSION_LIMIT', cast=int, default=5)
WEBDAV_SESSION_TIMEOUT = config('WEBDAV_SESSION_TIMEOUT', cast=int, default=1800)
