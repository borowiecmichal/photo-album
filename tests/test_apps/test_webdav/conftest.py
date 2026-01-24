"""Shared fixtures for WebDAV app tests."""

import boto3
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from moto import mock_aws

from server.apps.files.models import File
from server.apps.webdav.dav_provider import DjangoDAVProvider
from server.apps.webdav.domain_controller import ENVIRON_USER_KEY
from server.apps.webdav.path_mapper import PathMapper

User = get_user_model()


@pytest.fixture
def user(db):
    """Create test user.

    Returns:
        User instance for testing.
    """
    return User.objects.create_user(
        username='testuser',
        password='testpass123',
        email='test@example.com',
    )


@pytest.fixture
def other_user(db):
    """Create second test user for isolation tests.

    Returns:
        Second user instance.
    """
    return User.objects.create_user(
        username='otheruser',
        password='testpass123',
        email='other@example.com',
    )


@pytest.fixture
def mock_s3():
    """Mock S3 service with photo-album bucket.

    Yields:
        boto3 S3 resource with photo-album bucket created.
    """
    with mock_aws():
        # Create S3 resource
        conn = boto3.resource('s3', region_name='us-east-1')

        # Create bucket
        conn.create_bucket(Bucket='photo-album')

        yield conn


@pytest.fixture
def path_mapper(user):
    """Create PathMapper for test user.

    Args:
        user: Test user fixture.

    Returns:
        PathMapper instance.
    """
    return PathMapper(user.id)


@pytest.fixture
def dav_provider():
    """Create DAV provider instance.

    Returns:
        DjangoDAVProvider instance.
    """
    return DjangoDAVProvider()


@pytest.fixture
def webdav_environ(user, dav_provider):
    """Create WSGI environ with authenticated user.

    Args:
        user: Test user fixture.
        dav_provider: DAV provider fixture.

    Returns:
        WSGI environ dictionary with user.
    """
    return {
        ENVIRON_USER_KEY: user,
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/',
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '8080',
        'wsgi.input': None,
        'wsgidav.provider': dav_provider,
    }


@pytest.fixture
def sample_file(user, mock_s3, db):
    """Create sample file in database and S3.

    Args:
        user: Test user fixture.
        mock_s3: Mock S3 fixture.
        db: Database fixture.

    Returns:
        File instance.
    """
    storage_path = '{user_id}/documents/test.txt'.format(user_id=user.id)

    # Upload to mock S3
    mock_s3.Bucket('photo-album').put_object(
        Key=storage_path,
        Body=b'test file content',
    )

    # Create DB record
    return File.objects.create(
        user=user,
        file=storage_path,
        size_bytes=17,
        mime_type='text/plain',
        checksum_sha256='a' * 64,
    )


@pytest.fixture
def sample_file_content():
    """Sample file content for testing.

    Returns:
        ContentFile with test data.
    """
    return ContentFile(b'test file content', name='test.txt')
