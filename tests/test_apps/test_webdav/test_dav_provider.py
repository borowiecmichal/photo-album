"""Tests for WebDAV DAV provider."""

import pytest

from server.apps.files.models import File
from server.apps.webdav.domain_controller import ENVIRON_USER_KEY
from server.apps.webdav.resources.collection import FolderCollection
from server.apps.webdav.resources.file_resource import FileResource


class TestDjangoDAVProvider:
    """Tests for DjangoDAVProvider."""

    def test_is_readonly(self, dav_provider):
        """Test that provider is not read-only."""
        assert dav_provider.is_readonly() is False

    @pytest.mark.django_db
    def test_get_resource_inst_root(
        self,
        dav_provider,
        user,
        webdav_environ,
        mock_s3,
    ):
        """Test getting root folder resource."""
        resource = dav_provider.get_resource_inst('/', webdav_environ)

        assert resource is not None
        assert isinstance(resource, FolderCollection)

    @pytest.mark.django_db
    def test_get_resource_inst_file(
        self,
        dav_provider,
        user,
        webdav_environ,
        sample_file,
        mock_s3,
    ):
        """Test getting file resource."""
        resource = dav_provider.get_resource_inst(
            '/documents/test.txt',
            webdav_environ,
        )

        assert resource is not None
        assert isinstance(resource, FileResource)

    @pytest.mark.django_db
    def test_get_resource_inst_folder(
        self,
        dav_provider,
        user,
        webdav_environ,
        sample_file,
        mock_s3,
    ):
        """Test getting folder resource."""
        resource = dav_provider.get_resource_inst('/documents', webdav_environ)

        assert resource is not None
        assert isinstance(resource, FolderCollection)

    @pytest.mark.django_db
    def test_get_resource_inst_not_found(
        self,
        dav_provider,
        user,
        webdav_environ,
        mock_s3,
    ):
        """Test getting nonexistent resource."""
        resource = dav_provider.get_resource_inst(
            '/nonexistent/path.txt',
            webdav_environ,
        )

        assert resource is None

    @pytest.mark.django_db
    def test_get_resource_inst_invalid_path(
        self,
        dav_provider,
        user,
        webdav_environ,
        mock_s3,
    ):
        """Test that invalid paths are rejected."""
        resource = dav_provider.get_resource_inst(
            '/documents/../../../etc/passwd',
            webdav_environ,
        )

        assert resource is None

    @pytest.mark.django_db
    def test_user_isolation(
        self,
        dav_provider,
        user,
        other_user,
        mock_s3,
    ):
        """Test that users can only see their own files."""
        # Create file for other user
        storage_path = '{id}/secret.txt'.format(id=other_user.id)
        mock_s3.Bucket('photo-album').put_object(
            Key=storage_path,
            Body=b'secret content',
        )
        File.objects.create(
            user=other_user,
            file=storage_path,
            size_bytes=14,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )

        # Try to access with first user's environ
        environ = {
            ENVIRON_USER_KEY: user,
            'REQUEST_METHOD': 'GET',
            'PATH_INFO': '/secret.txt',
            'SERVER_NAME': 'localhost',
            'SERVER_PORT': '8080',
            'wsgidav.provider': dav_provider,
        }

        resource = dav_provider.get_resource_inst('/secret.txt', environ)

        # First user should not see other user's file
        assert resource is None
