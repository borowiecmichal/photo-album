"""Django management command to run the WebDAV server."""

import logging
from typing import Any, final, override

from cheroot.wsgi import Server as WSGIServer
from django.conf import settings
from django.core.management.base import BaseCommand

from server.apps.webdav.wsgi_app import create_webdav_app

logger = logging.getLogger(__name__)


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

    @override
    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command.

        Args:
            args: Positional arguments.
            options: Keyword arguments from command line.
        """
        host = options['host'] or getattr(settings, 'WEBDAV_HOST', '0.0.0.0')  # noqa: S104
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
