"""Tests for trash operations business logic."""

from datetime import timedelta

import pytest
from django.utils import timezone

from server.apps.files.logic.trash_operations import (
    _generate_trash_name,
    empty_trash,
    get_trash_file_by_name,
    list_trash,
    permanent_delete_file,
    restore_file,
    soft_delete_file,
)
from server.apps.files.models import File, UserQuota


@pytest.mark.django_db
class TestSoftDeleteFile:
    """Tests for soft_delete_file function."""

    def test_soft_delete_sets_flags(self, user, mock_s3):
        """Test soft delete sets is_deleted, deleted_at, original_path."""
        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/documents/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        original_path = file_instance.file.name

        result = soft_delete_file(file_instance.id)

        assert result.is_deleted is True
        assert result.deleted_at is not None
        assert result.original_path == original_path
        assert result.trash_name != ''

    def test_soft_delete_preserves_storage(self, user, mock_s3):
        """Test soft delete doesn't remove file from S3."""
        storage_path = f'{user.id}/documents/test.txt'

        # Upload to mock S3
        mock_s3.Bucket('photo-album').put_object(
            Key=storage_path,
            Body=b'test content',
        )

        file_instance = File.objects.create(
            user=user,
            file=storage_path,
            size_bytes=12,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )

        soft_delete_file(file_instance.id)

        # S3 file should still exist
        objs = list(mock_s3.Bucket('photo-album').objects.filter(
            Prefix=storage_path,
        ))
        assert len(objs) == 1

    def test_soft_delete_quota_unchanged(self, user, mock_s3):
        """Test soft delete does not decrement quota."""
        quota = UserQuota.objects.create(
            user=user,
            quota_bytes=10 * 1024 * 1024,
            used_bytes=100,
        )

        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )

        soft_delete_file(file_instance.id)

        quota.refresh_from_db()
        assert quota.used_bytes == 100  # Unchanged

    def test_soft_delete_file_not_found(self, user, mock_s3):
        """Test soft delete raises for non-existent file."""
        with pytest.raises(File.DoesNotExist):
            soft_delete_file(99999)


@pytest.mark.django_db
class TestTrashNameGeneration:
    """Tests for _generate_trash_name function."""

    def test_trash_name_includes_timestamp(self):
        """Test trash name has timestamp format."""
        name = _generate_trash_name('123/docs/report.pdf')
        assert '__' in name
        assert name.endswith('.pdf')
        assert name.startswith('report__')

    def test_trash_name_unique_same_second(self):
        """Test two calls don't produce identical names (microseconds)."""
        name1 = _generate_trash_name('test.txt')
        name2 = _generate_trash_name('test.txt')
        # Microseconds should make them different
        assert name1 != name2


@pytest.mark.django_db
class TestRestoreFile:
    """Tests for restore_file function."""

    def test_restore_clears_flags(self, user, mock_s3):
        """Test restore clears is_deleted, deleted_at."""
        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(file_instance.id)

        result = restore_file(file_instance.id)

        assert result.is_deleted is False
        assert result.deleted_at is None
        assert result.original_path == ''
        assert result.trash_name == ''

    def test_restore_to_original_path(self, user, mock_s3):
        """Test restore uses original path by default."""
        from django.core.files.base import ContentFile
        from server.apps.files.logic.file_operations import upload_file

        original_path = f'{user.id}/docs/test.txt'
        content = ContentFile(b'test content', name='test.txt')
        file_instance = upload_file(user, original_path, content)
        actual_path = file_instance.file.name  # May have suffix

        soft_delete_file(file_instance.id)

        result = restore_file(file_instance.id)

        assert result.file.name == actual_path
        assert result.is_deleted is False

    def test_restore_to_custom_path(self, user, mock_s3):
        """Test restore to custom destination path."""
        from django.core.files.base import ContentFile
        from server.apps.files.logic.file_operations import upload_file

        original_path = f'{user.id}/test.txt'
        dest_path = f'{user.id}/restored/new_test.txt'

        content = ContentFile(b'test content', name='test.txt')
        file_instance = upload_file(user, original_path, content)

        soft_delete_file(file_instance.id)

        result = restore_file(file_instance.id, dest_path)

        # Should be at destination path (may have suffix for uniqueness)
        assert result.file.name.startswith(f'{user.id}/restored/new_test')
        assert result.is_deleted is False

    def test_restore_auto_rename_conflict(self, user, mock_s3):
        """Test restore auto-renames when restoring to occupied path.

        Scenario: File A and B exist. Delete A. Try to restore A but specify
        B's path as destination. Should rename to avoid conflict.
        """
        from django.core.files.base import ContentFile
        from server.apps.files.logic.file_operations import upload_file

        path_a = f'{user.id}/file_a.txt'
        path_b = f'{user.id}/file_b.txt'

        # Create files using upload_file (properly goes through storage)
        content_a = ContentFile(b'content A', name='file_a.txt')
        content_b = ContentFile(b'content B', name='file_b.txt')

        file_a = upload_file(user, path_a, content_a)
        file_b = upload_file(user, path_b, content_b)

        # Soft delete file A
        soft_delete_file(file_a.id)

        # Try to restore file A to file B's path (which exists)
        result = restore_file(file_a.id, path_b)

        # Should auto-rename with (restored) suffix
        assert '(restored)' in result.file.name
        assert 'file_b' in result.file.name  # Based on dest path
        assert result.is_deleted is False

    def test_restore_preserves_tags(self, user, mock_s3):
        """Test restore keeps tags attached to file."""
        from server.apps.files.models import Tag

        tag = Tag.objects.create(user=user, name='important')

        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        file_instance.tags.add(tag)

        soft_delete_file(file_instance.id)
        result = restore_file(file_instance.id)

        assert tag in result.tags.all()

    def test_restore_file_not_in_trash(self, user, mock_s3):
        """Test restore raises for file not in trash."""
        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )

        with pytest.raises(File.DoesNotExist):
            restore_file(file_instance.id)


@pytest.mark.django_db
class TestPermanentDeleteFile:
    """Tests for permanent_delete_file function."""

    def test_permanent_delete_removes_from_db(self, user, mock_s3):
        """Test permanent delete removes file from database."""
        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(file_instance.id)
        file_id = file_instance.id

        permanent_delete_file(file_id)

        assert not File.all_objects.filter(id=file_id).exists()

    def test_permanent_delete_updates_quota(self, user, mock_s3):
        """Test permanent delete decrements quota."""
        quota = UserQuota.objects.create(
            user=user,
            quota_bytes=10 * 1024 * 1024,
            used_bytes=100,
        )

        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(file_instance.id)

        permanent_delete_file(file_instance.id)

        quota.refresh_from_db()
        assert quota.used_bytes == 0

    def test_permanent_delete_requires_is_deleted(self, user, mock_s3):
        """Test permanent delete raises for non-deleted file."""
        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )

        with pytest.raises(File.DoesNotExist):
            permanent_delete_file(file_instance.id)


@pytest.mark.django_db
class TestListTrash:
    """Tests for list_trash function."""

    def test_list_trash_returns_deleted_only(self, user, mock_s3):
        """Test list_trash only returns deleted files."""
        # Create non-deleted file
        File.objects.create(
            user=user,
            file=f'{user.id}/active.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )

        # Create and delete another file
        file2 = File.objects.create(
            user=user,
            file=f'{user.id}/deleted.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(file2.id)

        trash_files = list(list_trash(user))

        assert len(trash_files) == 1
        assert trash_files[0].id == file2.id

    def test_list_trash_sorted_by_deleted_at(self, user, mock_s3):
        """Test list_trash returns newest first."""
        file1 = File.objects.create(
            user=user,
            file=f'{user.id}/old.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(file1.id)
        # Set older deleted_at time
        File.all_objects.filter(id=file1.id).update(
            deleted_at=timezone.now() - timedelta(days=1),
        )

        file2 = File.objects.create(
            user=user,
            file=f'{user.id}/new.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(file2.id)

        trash_files = list(list_trash(user))

        assert len(trash_files) == 2
        assert trash_files[0].id == file2.id  # Newer first
        assert trash_files[1].id == file1.id


@pytest.mark.django_db
class TestEmptyTrash:
    """Tests for empty_trash function."""

    def test_empty_trash_deletes_all(self, user, mock_s3):
        """Test empty_trash permanently deletes all trashed files."""
        file1 = File.objects.create(
            user=user,
            file=f'{user.id}/file1.txt',
            size_bytes=50,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        file2 = File.objects.create(
            user=user,
            file=f'{user.id}/file2.txt',
            size_bytes=50,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(file1.id)
        soft_delete_file(file2.id)

        count = empty_trash(user)

        assert count == 2
        assert not File.all_objects.filter(user=user).exists()

    def test_empty_trash_updates_quota(self, user, mock_s3):
        """Test empty_trash decrements quota for all files."""
        quota = UserQuota.objects.create(
            user=user,
            quota_bytes=10 * 1024 * 1024,
            used_bytes=100,
        )

        file1 = File.objects.create(
            user=user,
            file=f'{user.id}/file1.txt',
            size_bytes=50,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        file2 = File.objects.create(
            user=user,
            file=f'{user.id}/file2.txt',
            size_bytes=50,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(file1.id)
        soft_delete_file(file2.id)

        empty_trash(user)

        quota.refresh_from_db()
        assert quota.used_bytes == 0


@pytest.mark.django_db
class TestGetTrashFileByName:
    """Tests for get_trash_file_by_name function."""

    def test_get_by_trash_name(self, user, mock_s3):
        """Test get_trash_file_by_name finds file by trash_name."""
        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        deleted_file = soft_delete_file(file_instance.id)

        result = get_trash_file_by_name(user, deleted_file.trash_name)

        assert result.id == file_instance.id

    def test_get_by_trash_name_not_found(self, user, mock_s3):
        """Test get_trash_file_by_name raises for unknown name."""
        with pytest.raises(File.DoesNotExist):
            get_trash_file_by_name(user, 'nonexistent.txt')


@pytest.mark.django_db
class TestModelManagers:
    """Tests for custom model managers."""

    def test_default_manager_excludes_deleted(self, user, mock_s3):
        """Test File.objects excludes soft-deleted files."""
        file1 = File.objects.create(
            user=user,
            file=f'{user.id}/active.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        file2 = File.objects.create(
            user=user,
            file=f'{user.id}/deleted.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(file2.id)

        # Default manager should only return active files
        files = list(File.objects.filter(user=user))
        assert len(files) == 1
        assert files[0].id == file1.id

    def test_all_objects_includes_deleted(self, user, mock_s3):
        """Test File.all_objects includes soft-deleted files."""
        file1 = File.objects.create(
            user=user,
            file=f'{user.id}/active.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        file2 = File.objects.create(
            user=user,
            file=f'{user.id}/deleted.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(file2.id)

        # all_objects should return both
        files = list(File.all_objects.filter(user=user))
        assert len(files) == 2
