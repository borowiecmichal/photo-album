"""Shared fixtures for files app tests."""

import boto3
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from moto import mock_aws

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
def sample_file_content():
    """Sample file content for testing.

    Returns:
        ContentFile with test data.
    """
    return ContentFile(b'test file content', name='test.txt')
