"""Tests for WebDAV quota integration."""

import pytest
from wsgidav.dav_error import DAVError, HTTP_INSUFFICIENT_STORAGE

from server.apps.files.models import File, UserQuota
from server.apps.webdav.resources.file_resource import (
    FileResource,
    NewFileResource,
)


@pytest.fixture
def small_quota(user, db):
    """Create a small quota for testing quota exceeded errors.

    Returns:
        UserQuota instance with small quota.
    """
    return UserQuota.objects.create(
        user=user,
        quota_bytes=100,
        used_bytes=90,  # Only 10 bytes available
    )


class TestNewFileResourceQuota:
    """Tests for quota enforcement on new file creation."""

    @pytest.mark.django_db
    def test_create_file_quota_exceeded(
        self,
        user,
        webdav_environ,
        path_mapper,
        mock_s3,
        small_quota,
    ):
        """Test creating new file raises HTTP 507 when quota exceeded."""
        resource = NewFileResource(
            '/bigfile.txt',
            webdav_environ,
            user,
            path_mapper,
        )

        # Start write session
        buffer = resource.begin_write()

        # Write content that exceeds quota (50 bytes, only 10 available)
        buffer.write(b'a' * 50)

        # Close should raise DAVError with HTTP 507
        with pytest.raises(DAVError) as exc_info:
            buffer.close()

        assert exc_info.value.value == HTTP_INSUFFICIENT_STORAGE

        # File should not be created
        assert File.objects.count() == 0

    @pytest.mark.django_db(transaction=True)
    def test_create_file_within_quota(
        self,
        user,
        webdav_environ,
        path_mapper,
        mock_s3,
        small_quota,
    ):
        """Test creating file succeeds when within quota."""
        resource = NewFileResource(
            '/smallfile.txt',
            webdav_environ,
            user,
            path_mapper,
        )

        # Start write session
        buffer = resource.begin_write()

        # Write content that fits in quota (5 bytes, 10 available)
        buffer.write(b'small')

        # Close should succeed
        buffer.close()

        # File should be created
        assert File.objects.filter(user=user).count() == 1


class TestFileResourceQuota:
    """Tests for quota enforcement on file updates."""

    @pytest.mark.django_db(transaction=True)
    def test_update_file_quota_exceeded(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
        mock_s3,
    ):
        """Test updating file raises HTTP 507 when quota exceeded."""
        # Set quota so update would exceed it
        UserQuota.objects.create(
            user=user,
            quota_bytes=sample_file.size_bytes + 5,  # Only 5 extra bytes
            used_bytes=sample_file.size_bytes,
        )

        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        # Start write session
        buffer = resource.begin_write()

        # Write larger content (100 bytes, only 5 extra available)
        buffer.write(b'a' * 100)

        # Close should raise DAVError with HTTP 507
        with pytest.raises(DAVError) as exc_info:
            buffer.close()

        assert exc_info.value.value == HTTP_INSUFFICIENT_STORAGE

    @pytest.mark.django_db(transaction=True)
    def test_update_file_smaller_content_over_quota(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
        mock_s3,
    ):
        """Test updating to smaller content works even when over quota."""
        # Set quota lower than current usage (over quota)
        UserQuota.objects.create(
            user=user,
            quota_bytes=10,  # Less than current 17 bytes
            used_bytes=sample_file.size_bytes,
        )

        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        # Start write session
        buffer = resource.begin_write()

        # Write smaller content (5 bytes)
        buffer.write(b'small')

        # Close should succeed (size decrease is allowed)
        buffer.close()

        # File should be updated
        sample_file.refresh_from_db()
        assert sample_file.size_bytes == 5


class TestCopyMoveQuota:
    """Tests for quota enforcement on copy/move operations."""

    @pytest.mark.django_db(transaction=True)
    def test_copy_file_quota_exceeded(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
        mock_s3,
    ):
        """Test copying file raises HTTP 507 when quota exceeded."""
        # Set quota so copy would exceed it
        UserQuota.objects.create(
            user=user,
            quota_bytes=sample_file.size_bytes + 5,  # Only 5 extra bytes
            used_bytes=sample_file.size_bytes,
        )

        resource = FileResource(
            '/documents/test.txt',
            webdav_environ,
            sample_file,
            path_mapper,
        )

        # Copy should raise DAVError with HTTP 507
        with pytest.raises(DAVError) as exc_info:
            resource.copy_move_single('/documents/copy.txt', is_move=False)

        assert exc_info.value.value == HTTP_INSUFFICIENT_STORAGE

        # Only original file should exist
        assert File.objects.filter(user=user).count() == 1
