"""Tests for WebDAV file resource."""

import pytest

from server.apps.files.models import File
from server.apps.webdav.path_mapper import PathMapper
from server.apps.webdav.resources.file_resource import (
    FileResource,
    NewFileResource,
)


class TestFileResource:
    """Tests for FileResource."""

    @pytest.mark.django_db
    def test_get_content_length(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
    ):
        """Test getting content length."""
        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        assert resource.get_content_length() == 17

    @pytest.mark.django_db
    def test_get_content_type(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
    ):
        """Test getting content type."""
        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        assert resource.get_content_type() == 'text/plain'

    @pytest.mark.django_db
    def test_get_etag(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
    ):
        """Test getting ETag from checksum."""
        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        etag = resource.get_etag()

        # ETag is returned without quotes - WsgiDAV adds them
        assert etag == 'a' * 64

    @pytest.mark.django_db
    def test_support_etag(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
    ):
        """Test ETag support."""
        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        assert resource.support_etag() is True

    @pytest.mark.django_db
    def test_support_ranges(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
    ):
        """Test range request support."""
        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        assert resource.support_ranges() is True

    @pytest.mark.django_db
    def test_get_creation_date(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
    ):
        """Test getting creation date."""
        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        creation_date = resource.get_creation_date()

        assert creation_date > 0
        assert creation_date == sample_file.uploaded_at.timestamp()

    @pytest.mark.django_db
    def test_get_last_modified(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
    ):
        """Test getting last modified date."""
        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        last_modified = resource.get_last_modified()

        assert last_modified > 0
        assert last_modified == sample_file.modified_at.timestamp()

    @pytest.mark.django_db
    def test_get_file_instance(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
    ):
        """Test getting underlying File model."""
        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        file_instance = resource.get_file_instance()

        assert file_instance == sample_file

    @pytest.mark.django_db
    def test_delete(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
        mock_s3,
    ):
        """Test deleting file."""
        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        file_id = sample_file.id

        resource.delete()

        assert not File.objects.filter(id=file_id).exists()


class TestNewFileResource:
    """Tests for NewFileResource."""

    @pytest.mark.django_db
    def test_get_content_length(self, user, webdav_environ, path_mapper):
        """Test content length for new file."""
        resource = NewFileResource(
            '/newfile.txt',
            webdav_environ,
            user,
            path_mapper,
        )

        assert resource.get_content_length() == 0

    @pytest.mark.django_db
    def test_get_content_type(self, user, webdav_environ, path_mapper):
        """Test content type for new file."""
        resource = NewFileResource(
            '/newfile.txt',
            webdav_environ,
            user,
            path_mapper,
        )

        assert resource.get_content_type() == 'application/octet-stream'
