"""Django app configuration for files app."""

from typing import override

from django.apps import AppConfig


class FilesConfig(AppConfig):
    """Configuration for files app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'server.apps.files'
    verbose_name = 'Files'

    @override
    def ready(self) -> None:
        """Import signal handlers when app is ready."""
        from server.apps.files import signals  # noqa: F401
