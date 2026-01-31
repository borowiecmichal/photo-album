"""Tests for cleanup_trash management command."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from server.apps.files.logic.trash_operations import soft_delete_file
from server.apps.files.models import File, UserQuota


@pytest.mark.django_db
class TestCleanupTrashCommand:
    """Tests for cleanup_trash management command."""

    def test_cleanup_deletes_old_files(self, user, mock_s3):
        """Test cleanup deletes files older than 30 days."""
        # Create quota
        quota = UserQuota.objects.create(
            user=user,
            quota_bytes=10 * 1024 * 1024,
            used_bytes=100,
        )

        # Create and delete a file
        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/old_file.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(file_instance.id)
        file_id = file_instance.id

        # Set deleted_at to 31 days ago
        File.all_objects.filter(id=file_id).update(
            deleted_at=timezone.now() - timedelta(days=31),
        )

        out = StringIO()
        call_command('cleanup_trash', stdout=out)

        # File should be permanently deleted
        assert not File.all_objects.filter(id=file_id).exists()

        # Quota should be decremented
        quota.refresh_from_db()
        assert quota.used_bytes == 0

        assert 'Purged 1 files' in out.getvalue()

    def test_cleanup_preserves_recent_files(self, user, mock_s3):
        """Test cleanup preserves files deleted less than 30 days ago."""
        # Create and delete a file
        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/recent_file.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(file_instance.id)
        file_id = file_instance.id

        # Set deleted_at to 29 days ago (recent)
        File.all_objects.filter(id=file_id).update(
            deleted_at=timezone.now() - timedelta(days=29),
        )

        out = StringIO()
        call_command('cleanup_trash', stdout=out)

        # File should still exist
        assert File.all_objects.filter(id=file_id).exists()

        assert 'Purged 0 files' in out.getvalue()

    def test_cleanup_batch_limit(self, user, mock_s3):
        """Test cleanup respects --batch-size option."""
        # Create multiple old files
        for i in range(5):
            file_instance = File.objects.create(
                user=user,
                file=f'{user.id}/file{i}.txt',
                size_bytes=10,
                mime_type='text/plain',
                checksum_sha256=f'{i}' * 64,
            )
            soft_delete_file(file_instance.id)

        # Set all to 31 days ago
        File.all_objects.filter(user=user).update(
            deleted_at=timezone.now() - timedelta(days=31),
        )

        out = StringIO()
        call_command('cleanup_trash', '--batch-size=2', stdout=out)

        # Only 2 should be deleted
        assert File.all_objects.filter(user=user).count() == 3

        assert 'Purged 2 files' in out.getvalue()

    def test_cleanup_dry_run(self, user, mock_s3):
        """Test cleanup --dry-run doesn't delete."""
        # Create and delete a file
        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(file_instance.id)
        file_id = file_instance.id

        # Set deleted_at to 31 days ago
        File.all_objects.filter(id=file_id).update(
            deleted_at=timezone.now() - timedelta(days=31),
        )

        out = StringIO()
        call_command('cleanup_trash', '--dry-run', stdout=out)

        # File should still exist
        assert File.all_objects.filter(id=file_id).exists()

        assert 'Would purge 1 files' in out.getvalue()

    def test_cleanup_handles_multiple_users(self, user, other_user, mock_s3):
        """Test cleanup handles files from multiple users."""
        # Create quotas for both users
        quota1 = UserQuota.objects.create(
            user=user,
            quota_bytes=10 * 1024 * 1024,
            used_bytes=100,
        )
        quota2 = UserQuota.objects.create(
            user=other_user,
            quota_bytes=10 * 1024 * 1024,
            used_bytes=200,
        )

        # Create old files for both users
        file1 = File.objects.create(
            user=user,
            file=f'{user.id}/file1.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        file2 = File.objects.create(
            user=other_user,
            file=f'{other_user.id}/file2.txt',
            size_bytes=200,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(file1.id)
        soft_delete_file(file2.id)

        # Set both to 31 days ago
        File.all_objects.update(
            deleted_at=timezone.now() - timedelta(days=31),
        )

        out = StringIO()
        call_command('cleanup_trash', stdout=out)

        # Both files should be deleted
        assert not File.all_objects.filter(user=user).exists()
        assert not File.all_objects.filter(user=other_user).exists()

        # Both quotas should be decremented
        quota1.refresh_from_db()
        quota2.refresh_from_db()
        assert quota1.used_bytes == 0
        assert quota2.used_bytes == 0

        assert 'Purged 2 files' in out.getvalue()

    def test_cleanup_processes_oldest_first(self, user, mock_s3):
        """Test cleanup processes files by deleted_at (oldest first)."""
        # Create files with different ages
        older = File.objects.create(
            user=user,
            file=f'{user.id}/older.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(older.id)
        File.all_objects.filter(id=older.id).update(
            deleted_at=timezone.now() - timedelta(days=40),
        )

        newer = File.objects.create(
            user=user,
            file=f'{user.id}/newer.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(newer.id)
        File.all_objects.filter(id=newer.id).update(
            deleted_at=timezone.now() - timedelta(days=31),
        )

        out = StringIO()
        call_command('cleanup_trash', '--batch-size=1', stdout=out)

        # Older file should be deleted, newer should remain
        assert not File.all_objects.filter(id=older.id).exists()
        assert File.all_objects.filter(id=newer.id).exists()
