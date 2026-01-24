"""Django app configuration for WebDAV app."""

from django.apps import AppConfig


class WebDAVConfig(AppConfig):
    """Configuration for WebDAV app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'server.apps.webdav'
    verbose_name = 'WebDAV'
