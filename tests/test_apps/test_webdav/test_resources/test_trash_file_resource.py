"""Tests for TrashFileResource WebDAV resource."""

import pytest
from django.core.files.base import ContentFile
from wsgidav.dav_error import DAVError

from server.apps.files.logic.file_operations import upload_file
from server.apps.files.logic.trash_operations import soft_delete_file
from server.apps.files.models import File, UserQuota
from server.apps.webdav.path_mapper import PathMapper
from server.apps.webdav.resources.trash_file_resource import TrashFileResource


@pytest.mark.django_db
class TestTrashFileResource:
    """Tests for TrashFileResource WebDAV resource."""

    def _create_trash_file(self, user, mock_s3):
        """Helper to create a trashed file using upload_file."""
        storage_path = f'{user.id}/documents/test.txt'
        content = ContentFile(b'test file content', name='test.txt')
        file_instance = upload_file(user, storage_path, content)
        return soft_delete_file(file_instance.id)

    def test_get_display_name_shows_original_filename(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test display name shows original filename, not trash_name."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        # Should show original filename (may have storage suffix)
        display_name = resource.get_display_name()
        assert display_name.startswith('test')
        assert display_name.endswith('.txt')

    def test_get_content_length(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test get_content_length returns file size."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        assert resource.get_content_length() == 17

    def test_get_content_type(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test get_content_type returns MIME type."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        assert resource.get_content_type() == 'text/plain'

    def test_get_content_streams_from_s3(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test GET streams file content from S3."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        content = resource.get_content()
        try:
            data = content.read()
            assert data == b'test file content'
        finally:
            content.close()

    def test_delete_permanently_deletes(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test DELETE permanently removes file."""
        file_instance = self._create_trash_file(user, mock_s3)
        file_id = file_instance.id
        file_size = file_instance.size_bytes

        # Get quota (created by upload_file)
        quota = UserQuota.objects.get(user=user)
        initial_used = quota.used_bytes

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        resource.delete()

        # File should be gone from DB
        assert not File.all_objects.filter(id=file_id).exists()

        # Quota should be decremented
        quota.refresh_from_db()
        assert quota.used_bytes == initial_used - file_size

    def test_move_out_of_trash_restores(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test MOVE out of trash restores file."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        # MOVE to regular path
        resource.copy_move_single('/restored/test.txt', is_move=True)

        # File should be restored
        file_instance.refresh_from_db()
        assert file_instance.is_deleted is False

    def test_copy_from_trash_forbidden(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test COPY from trash is forbidden."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        with pytest.raises(DAVError):
            resource.copy_move_single('/copy.txt', is_move=False)

    def test_move_within_trash_forbidden(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test MOVE within trash is forbidden."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        with pytest.raises(DAVError):
            resource.copy_move_single('/.Trash/renamed.txt', is_move=True)

    def test_begin_write_forbidden(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test PUT to trash file is forbidden."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        with pytest.raises(DAVError):
            resource.begin_write()

    def test_get_property_value_original_path(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test custom property exposes original path."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        original_path = resource.get_property_value('{DAV:}original-path')

        # Path may have storage suffix for uniqueness
        assert original_path.startswith(f'{user.id}/documents/test')
        assert original_path.endswith('.txt')

    def test_support_ranges(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test trash files support range requests."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        assert resource.support_ranges() is True

    def test_get_etag(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test get_etag returns checksum."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        # ETag should be the SHA256 checksum (computed by upload_file)
        assert resource.get_etag() == file_instance.checksum_sha256
        assert len(resource.get_etag()) == 64

    def test_get_last_modified_uses_deleted_at(
        self,
        user,
        mock_s3,
        webdav_environ,
        path_mapper,
    ):
        """Test get_last_modified uses deletion time."""
        file_instance = self._create_trash_file(user, mock_s3)

        resource = TrashFileResource(
            '/.Trash/test.txt',
            webdav_environ,
            file_instance,
            path_mapper,
        )

        timestamp = resource.get_last_modified()
        assert timestamp == file_instance.deleted_at.timestamp()
