"""Tests for File model."""

import pytest

from server.apps.files.models import File


@pytest.mark.django_db
def test_file_model_str(user, mock_s3):
    """Test File __str__ method."""
    file_instance = File.objects.create(
        user=user,
        file='1/test.txt',
        size_bytes=100,
        mime_type='text/plain',
        checksum_sha256='abcd' * 16,
    )

    expected = f'{user.username}:1/test.txt'
    assert str(file_instance) == expected


@pytest.mark.django_db
def test_file_get_filename(user, mock_s3):
    """Test get_filename method extracts filename correctly."""
    file_instance = File.objects.create(
        user=user,
        file='1/documents/reports/test.pdf',
        size_bytes=1000,
        mime_type='application/pdf',
        checksum_sha256='abcd' * 16,
    )

    assert file_instance.get_filename() == 'test.pdf'


@pytest.mark.django_db
def test_file_get_folder_path(user, mock_s3):
    """Test get_folder_path method extracts folder correctly."""
    file_instance = File.objects.create(
        user=user,
        file='1/documents/reports/test.pdf',
        size_bytes=1000,
        mime_type='application/pdf',
        checksum_sha256='abcd' * 16,
    )

    assert file_instance.get_folder_path() == '1/documents/reports'


@pytest.mark.django_db
def test_file_get_extension(user, mock_s3):
    """Test get_extension method extracts extension correctly."""
    file_instance = File.objects.create(
        user=user,
        file='1/test.PDF',
        size_bytes=100,
        mime_type='application/pdf',
        checksum_sha256='abcd' * 16,
    )

    # Should return lowercase without dot
    assert file_instance.get_extension() == 'pdf'


@pytest.mark.django_db
def test_file_cascade_delete_with_user(user, mock_s3):
    """Test files are deleted when user is deleted."""
    File.objects.create(
        user=user,
        file='1/test.txt',
        size_bytes=100,
        mime_type='text/plain',
        checksum_sha256='abcd' * 16,
    )

    assert File.objects.count() == 1

    user.delete()

    # File should be cascade deleted
    assert File.objects.count() == 0
