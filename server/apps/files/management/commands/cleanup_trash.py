"""Management command to clean up old files from trash."""

import logging
from datetime import timedelta
from typing import Any, Final

from django.core.management.base import BaseCommand
from django.utils import timezone

from server.apps.files.logic.trash_operations import permanent_delete_file
from server.apps.files.models import File

_RETENTION_DAYS: Final = 30
_DEFAULT_BATCH_SIZE: Final = 1000

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Permanently delete files that have been in trash for 30+ days."""

    help = 'Clean up old files from trash (30+ days)'

    def add_arguments(self, parser: Any) -> None:
        """Add command line arguments.

        Args:
            parser: Argument parser.
        """
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without deleting',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=_DEFAULT_BATCH_SIZE,
            help=f'Max files to process (default: {_DEFAULT_BATCH_SIZE})',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the cleanup command.

        Args:
            args: Positional arguments (unused).
            options: Command options.
        """
        dry_run = options['dry_run']
        batch_size = options['batch_size']

        cutoff = timezone.now() - timedelta(days=_RETENTION_DAYS)

        self.stdout.write(
            f'Looking for files deleted before {cutoff} '
            f'(older than {_RETENTION_DAYS} days)',
        )

        old_files = File.all_objects.filter(
            is_deleted=True,
            deleted_at__lte=cutoff,
        ).order_by('deleted_at')[:batch_size]

        count = 0
        failed = 0

        for file_instance in old_files:
            if dry_run:
                self.stdout.write(
                    f'Would delete: {file_instance.trash_name} '
                    f'(user: {file_instance.user.username}, '
                    f'deleted: {file_instance.deleted_at})',
                )
                count += 1
                continue

            try:
                permanent_delete_file(file_instance.id)
                count += 1
                logger.info(
                    'Purged file from trash: %s (ID: %d)',
                    file_instance.trash_name,
                    file_instance.id,
                )
            except Exception as exc:
                self.stderr.write(
                    f'Failed to delete {file_instance.id}: {exc}',
                )
                logger.exception(
                    'Failed to purge file from trash: %d',
                    file_instance.id,
                )
                failed += 1

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'Would purge {count} files from trash'),
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Purged {count} files from trash, {failed} failed',
                ),
            )
