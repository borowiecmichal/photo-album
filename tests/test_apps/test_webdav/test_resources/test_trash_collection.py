"""Tests for TrashCollection WebDAV resource."""

import pytest
from wsgidav.dav_error import DAVError

from server.apps.files.logic.trash_operations import soft_delete_file
from server.apps.files.models import File, UserQuota
from server.apps.webdav.path_mapper import PathMapper
from server.apps.webdav.resources.trash_collection import TrashCollection


@pytest.mark.django_db
class TestTrashCollection:
    """Tests for TrashCollection WebDAV resource."""

    def test_get_display_name(self, user, webdav_environ, path_mapper):
        """Test display name is .Trash."""
        collection = TrashCollection(
            '/.Trash/',
            webdav_environ,
            user,
            path_mapper,
        )

        assert collection.get_display_name() == '.Trash'

    def test_get_member_names_returns_original_filenames(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test PROPFIND shows original filenames, not trash_names."""
        # Create and delete files
        file1 = File.objects.create(
            user=user,
            file=f'{user.id}/docs/report.pdf',
            size_bytes=100,
            mime_type='application/pdf',
            checksum_sha256='a' * 64,
        )
        file2 = File.objects.create(
            user=user,
            file=f'{user.id}/photos/image.jpg',
            size_bytes=200,
            mime_type='image/jpeg',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(file1.id)
        soft_delete_file(file2.id)

        collection = TrashCollection(
            '/.Trash/',
            webdav_environ,
            user,
            path_mapper,
        )

        members = collection.get_member_names()

        assert 'report.pdf' in members
        assert 'image.jpg' in members

    def test_get_member_returns_trash_file_resource(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test get_member returns TrashFileResource."""
        from server.apps.webdav.resources.trash_file_resource import (
            TrashFileResource,
        )

        file_instance = File.objects.create(
            user=user,
            file=f'{user.id}/test.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(file_instance.id)

        collection = TrashCollection(
            '/.Trash/',
            webdav_environ,
            user,
            path_mapper,
        )

        member = collection.get_member('test.txt')

        assert isinstance(member, TrashFileResource)

    def test_get_member_not_found(
        self,
        user,
        webdav_environ,
        path_mapper,
    ):
        """Test get_member raises for non-existent file."""
        collection = TrashCollection(
            '/.Trash/',
            webdav_environ,
            user,
            path_mapper,
        )

        with pytest.raises(DAVError):
            collection.get_member('nonexistent.txt')

    def test_create_empty_resource_forbidden(
        self,
        user,
        webdav_environ,
        path_mapper,
    ):
        """Test PUT to trash is forbidden."""
        collection = TrashCollection(
            '/.Trash/',
            webdav_environ,
            user,
            path_mapper,
        )

        with pytest.raises(DAVError):
            collection.create_empty_resource('new_file.txt')

    def test_create_collection_forbidden(
        self,
        user,
        webdav_environ,
        path_mapper,
    ):
        """Test MKCOL in trash is forbidden."""
        collection = TrashCollection(
            '/.Trash/',
            webdav_environ,
            user,
            path_mapper,
        )

        with pytest.raises(DAVError):
            collection.create_collection('subfolder')

    def test_delete_empties_trash(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test DELETE on /.Trash/ empties all trash files."""
        quota = UserQuota.objects.create(
            user=user,
            quota_bytes=10 * 1024 * 1024,
            used_bytes=300,
        )

        file1 = File.objects.create(
            user=user,
            file=f'{user.id}/file1.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        file2 = File.objects.create(
            user=user,
            file=f'{user.id}/file2.txt',
            size_bytes=200,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )
        soft_delete_file(file1.id)
        soft_delete_file(file2.id)

        collection = TrashCollection(
            '/.Trash/',
            webdav_environ,
            user,
            path_mapper,
        )

        collection.delete()

        # All files should be permanently deleted
        assert not File.all_objects.filter(user=user).exists()

        # Quota should be decremented
        quota.refresh_from_db()
        assert quota.used_bytes == 0

    def test_support_recursive_delete(
        self,
        user,
        webdav_environ,
        path_mapper,
    ):
        """Test trash supports recursive delete."""
        collection = TrashCollection(
            '/.Trash/',
            webdav_environ,
            user,
            path_mapper,
        )

        assert collection.support_recursive_delete() is True

    def test_get_last_modified_uses_most_recent_deletion(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test get_last_modified returns most recent deleted_at."""
        file1 = File.objects.create(
            user=user,
            file=f'{user.id}/file1.txt',
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        soft_delete_file(file1.id)

        collection = TrashCollection(
            '/.Trash/',
            webdav_environ,
            user,
            path_mapper,
        )

        # Should return a valid timestamp
        timestamp = collection.get_last_modified()
        assert timestamp > 0
