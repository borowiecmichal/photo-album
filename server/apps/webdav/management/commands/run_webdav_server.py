"""Django management command to run the WebDAV server."""

import logging
import os
import sys
from typing import Any, final, override

from cheroot.wsgi import Server as WSGIServer
from django.conf import settings
from django.core.management.base import BaseCommand

from server.apps.webdav.wsgi_app import create_webdav_app

logger = logging.getLogger(__name__)

# Environment variable to indicate we're in a reload subprocess
_RELOAD_ENV_VAR = 'WEBDAV_RELOAD_SUBPROCESS'


@final
class Command(BaseCommand):
    """Run the WebDAV server using cheroot WSGI server."""

    help = 'Run the WebDAV server for native file browser access'

    @override
    def add_arguments(self, parser: Any) -> None:
        """Add command arguments.

        Args:
            parser: Argument parser.
        """
        parser.add_argument(
            '--host',
            type=str,
            default=None,
            help='Host to bind to (default: from settings)',
        )
        parser.add_argument(
            '--port',
            type=int,
            default=None,
            help='Port to bind to (default: from settings)',
        )
        parser.add_argument(
            '--verbose',
            type=int,
            default=1,
            choices=range(6),
            help='Verbosity level 0-5 (default: 1)',
        )
        parser.add_argument(
            '--reload',
            action='store_true',
            default=False,
            help='Enable auto-reload on code changes (development only)',
        )

    @override
    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command.

        Args:
            args: Positional arguments.
            options: Keyword arguments from command line.
        """
        use_reload = options['reload']
        is_subprocess = os.environ.get(_RELOAD_ENV_VAR) == 'true'

        if use_reload and not is_subprocess:
            # Parent process: run file watcher
            self._run_with_reload(options)
        else:
            # Child process or no reload: run server directly
            self._run_server(options)

    def _run_server(self, options: dict[str, Any]) -> None:
        """Run the WebDAV server directly.

        Args:
            options: Command options.
        """
        host = options['host'] or getattr(
            settings,
            'WEBDAV_HOST',
            '0.0.0.0',  # noqa: S104
        )
        port = options['port'] or getattr(settings, 'WEBDAV_PORT', 8080)
        verbose = options['verbose']

        self.stdout.write(
            self.style.SUCCESS(
                f'Starting WebDAV server on {host}:{port}',
            ),
        )

        # Create the WebDAV WSGI application
        app = create_webdav_app(verbose=verbose)

        # Create and configure the cheroot server
        server = WSGIServer(
            bind_addr=(host, port),
            wsgi_app=app,
        )

        # Set server name for HTTP headers
        server.server_name = 'PhotoAlbum-WebDAV'

        try:
            logger.info(
                'WebDAV server starting on %s:%d',
                host,
                port,
            )
            server.start()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nShutting down...'))
        finally:
            server.stop()
            self.stdout.write(self.style.SUCCESS('WebDAV server stopped'))

    def _run_with_reload(self, options: dict[str, Any]) -> None:
        """Run server with auto-reload on file changes.

        Uses watchfiles to monitor Python files and restart the server
        when changes are detected.

        Args:
            options: Command options.
        """
        try:
            import watchfiles  # noqa: PLC0415
        except ImportError:
            self.stderr.write(
                self.style.ERROR(
                    'watchfiles is required for --reload. '
                    'Install with: poetry add -G dev watchfiles',
                ),
            )
            sys.exit(1)

        self.stdout.write(
            self.style.SUCCESS(
                'Starting WebDAV server with auto-reload enabled...',
            ),
        )

        # Build command to run in subprocess (as string for watchfiles)
        cmd_parts = [sys.executable, '-m', 'django', 'run_webdav_server']
        if options['host']:
            cmd_parts.extend(['--host', options['host']])
        if options['port']:
            cmd_parts.extend(['--port', str(options['port'])])
        if options['verbose']:
            cmd_parts.extend(['--verbose', str(options['verbose'])])
        # Don't pass --reload to subprocess
        cmd = ' '.join(cmd_parts)

        # Directories to watch
        watch_dirs = [
            str(settings.BASE_DIR / 'server'),
        ]

        # Filter for Python files only
        def watch_filter(  # noqa: WPS430
            change: watchfiles.Change,
            path: str,
        ) -> bool:
            """Filter to only watch Python files."""
            return path.endswith('.py')

        # Set env var so subprocess knows it's being managed by reloader
        os.environ[_RELOAD_ENV_VAR] = 'true'

        # Run with file watching
        watchfiles.run_process(
            *watch_dirs,
            target=cmd,
            target_type='command',
            watch_filter=watch_filter,
            callback=self._on_reload,
        )

    def _on_reload(self, changes: set[tuple[Any, str]]) -> None:
        """Callback when files change and reload is triggered.

        Args:
            changes: Set of (change_type, path) tuples.
        """
        for change_type, path in changes:
            self.stdout.write(
                self.style.WARNING(
                    f'Detected {change_type.name}: {path}',
                ),
            )
        self.stdout.write(
            self.style.SUCCESS('Reloading WebDAV server...'),
        )
