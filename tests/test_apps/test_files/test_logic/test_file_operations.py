"""Tests for file operations business logic."""

from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from server.apps.files.exceptions import QuotaExceededError
from server.apps.files.logic.file_operations import (
    copy_file,
    delete_file,
    list_directory,
    update_file_content,
    upload_file,
)
from server.apps.files.models import File, UserQuota


@pytest.mark.django_db
def test_upload_file_success(user, mock_s3, sample_file_content):
    """Test successful file upload (S3 + DB)."""
    storage_path = f'{user.id}/test.txt'

    file_instance = upload_file(user, storage_path, sample_file_content)

    # Check file was created in DB
    assert file_instance.id is not None
    assert file_instance.user == user
    # Storage may add suffix for uniqueness (file_overwrite=False)
    assert file_instance.file.name.startswith(f'{user.id}/test')
    assert file_instance.size_bytes > 0
    assert file_instance.mime_type == 'text/plain'
    assert len(file_instance.checksum_sha256) == 64

    # Check file exists in DB
    assert File.objects.filter(id=file_instance.id).exists()


@pytest.mark.django_db
def test_upload_file_invalid_path(user, mock_s3, sample_file_content):
    """Test upload with invalid storage path (wrong user ID)."""
    wrong_user_id = user.id + 100
    storage_path = f'{wrong_user_id}/test.txt'

    with pytest.raises(ValidationError):
        upload_file(user, storage_path, sample_file_content)

    # No file should be created
    assert File.objects.count() == 0


@pytest.mark.django_db
def test_delete_file_success(user, mock_s3):
    """Test successful file deletion (DB + S3)."""
    # Create file
    file_instance = File.objects.create(
        user=user,
        file=f'{user.id}/test.txt',
        size_bytes=100,
        mime_type='text/plain',
        checksum_sha256='abcd' * 16,
    )

    file_id = file_instance.id

    # Delete file
    delete_file(file_id)

    # File should be deleted from DB
    assert not File.objects.filter(id=file_id).exists()


@pytest.mark.django_db
def test_delete_file_not_found(user):
    """Test deleting non-existent file."""
    with pytest.raises(File.DoesNotExist):
        delete_file(99999)


@pytest.mark.django_db
def test_list_directory_root(user, mock_s3):
    """Test listing files in user's root directory."""
    # Create files in different folders
    File.objects.create(
        user=user,
        file=f'{user.id}/file1.txt',
        size_bytes=100,
        mime_type='text/plain',
        checksum_sha256='abcd' * 16,
    )
    File.objects.create(
        user=user,
        file=f'{user.id}/documents/file2.txt',
        size_bytes=200,
        mime_type='text/plain',
        checksum_sha256='efgh' * 16,
    )

    # List root directory
    files = list_directory(user, '')

    # Should return all files for user
    assert files.count() == 2


@pytest.mark.django_db
def test_list_directory_subfolder(user, mock_s3):
    """Test listing files in specific subfolder."""
    # Create files
    File.objects.create(
        user=user,
        file=f'{user.id}/file1.txt',
        size_bytes=100,
        mime_type='text/plain',
        checksum_sha256='abcd' * 16,
    )
    File.objects.create(
        user=user,
        file=f'{user.id}/documents/file2.txt',
        size_bytes=200,
        mime_type='text/plain',
        checksum_sha256='efgh' * 16,
    )
    File.objects.create(
        user=user,
        file=f'{user.id}/documents/reports/file3.txt',
        size_bytes=300,
        mime_type='text/plain',
        checksum_sha256='ijkl' * 16,
    )

    # List documents folder
    files = list_directory(user, 'documents')

    # Should return files in documents and subdirectories
    assert files.count() == 2
    assert all(
        'documents' in file_instance.file.name
        for file_instance in files
    )


@pytest.mark.django_db
def test_list_directory_user_isolation(user, other_user, mock_s3):
    """Test that list_directory only returns user's files."""
    # Create file for first user
    File.objects.create(
        user=user,
        file=f'{user.id}/file1.txt',
        size_bytes=100,
        mime_type='text/plain',
        checksum_sha256='abcd' * 16,
    )

    # Create file for other user
    File.objects.create(
        user=other_user,
        file=f'{other_user.id}/file2.txt',
        size_bytes=200,
        mime_type='text/plain',
        checksum_sha256='efgh' * 16,
    )

    # List first user's files
    files = list_directory(user, '')

    # Should only return first user's file
    assert files.count() == 1
    assert files.first().user == user


@pytest.mark.django_db
def test_update_file_content_success(user, mock_s3, sample_file_content):
    """Test atomic file content update."""
    storage_path = f'{user.id}/test.txt'

    # Create initial file
    file_instance = upload_file(user, storage_path, sample_file_content)
    original_checksum = file_instance.checksum_sha256

    # Update with new content
    new_content = ContentFile(b'updated content here', name='test.txt')
    updated_file = update_file_content(file_instance.id, new_content)

    # Check file was updated
    assert updated_file.id == file_instance.id
    assert updated_file.checksum_sha256 != original_checksum
    assert updated_file.size_bytes == 20

    # File should still exist in DB
    assert File.objects.filter(id=file_instance.id).exists()


@pytest.mark.django_db
def test_update_file_content_not_found():
    """Test updating non-existent file."""
    new_content = ContentFile(b'new content', name='test.txt')

    with pytest.raises(File.DoesNotExist):
        update_file_content(99999, new_content)


@pytest.mark.django_db
def test_update_file_content_with_bytesio(user, mock_s3, sample_file_content):
    """Test update with BytesIO object (no .size attribute)."""
    storage_path = f'{user.id}/test.txt'

    # Create initial file
    file_instance = upload_file(user, storage_path, sample_file_content)

    # Update with BytesIO (doesn't have .size attribute)
    new_content = BytesIO(b'bytesio content here')
    updated_file = update_file_content(file_instance.id, new_content)

    # Check file was updated
    assert updated_file.size_bytes == 20


# Quota integration tests


@pytest.mark.django_db
def test_upload_file_increments_usage(user, mock_s3, sample_file_content):
    """Test upload_file increments user's quota usage."""
    storage_path = f'{user.id}/test.txt'

    file_instance = upload_file(user, storage_path, sample_file_content)

    # Check quota was updated
    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == file_instance.size_bytes


@pytest.mark.django_db
def test_upload_file_raises_quota_exceeded(user, mock_s3):
    """Test upload_file raises QuotaExceededError when over quota."""
    # Set a small quota
    UserQuota.objects.create(
        user=user,
        quota_bytes=100,
        used_bytes=90,
    )

    storage_path = f'{user.id}/test.txt'
    content = ContentFile(b'a' * 50, name='test.txt')  # 50 bytes

    with pytest.raises(QuotaExceededError) as exc_info:
        upload_file(user, storage_path, content)

    assert exc_info.value.quota_bytes == 100
    assert exc_info.value.used_bytes == 90
    assert exc_info.value.required_bytes == 50

    # File should not be created
    assert File.objects.count() == 0


@pytest.mark.django_db
def test_delete_file_decrements_usage(user, mock_s3, sample_file_content):
    """Test delete_file decrements user's quota usage."""
    storage_path = f'{user.id}/test.txt'

    # Upload file
    file_instance = upload_file(user, storage_path, sample_file_content)
    file_size = file_instance.size_bytes
    file_id = file_instance.id

    # Verify usage was incremented
    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == file_size

    # Delete file
    delete_file(file_id)

    # Check quota was decremented
    quota.refresh_from_db()
    assert quota.used_bytes == 0


@pytest.mark.django_db
def test_copy_file_checks_quota(user, mock_s3, sample_file_content):
    """Test copy_file raises QuotaExceededError when over quota."""
    storage_path = f'{user.id}/original.txt'

    # Create initial file with plenty of quota
    file_instance = upload_file(user, storage_path, sample_file_content)

    # Now reduce quota so copy would exceed it
    quota = UserQuota.objects.get(user=user)
    quota.quota_bytes = file_instance.size_bytes + 5  # Only 5 bytes left
    quota.save()

    dest_path = f'{user.id}/copy.txt'

    with pytest.raises(QuotaExceededError):
        copy_file(user, storage_path, dest_path)


@pytest.mark.django_db
def test_copy_file_increments_usage(user, mock_s3, sample_file_content):
    """Test copy_file increments user's quota usage."""
    storage_path = f'{user.id}/original.txt'

    # Create initial file
    file_instance = upload_file(user, storage_path, sample_file_content)
    original_size = file_instance.size_bytes

    # Copy file
    dest_path = f'{user.id}/copy.txt'
    copy_file(user, storage_path, dest_path)

    # Check quota was updated (should be double now)
    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == original_size * 2


@pytest.mark.django_db
def test_update_file_content_adjusts_usage_increase(
    user,
    mock_s3,
    sample_file_content,
):
    """Test update_file_content adjusts quota for size increase."""
    storage_path = f'{user.id}/test.txt'

    # Create initial file
    file_instance = upload_file(user, storage_path, sample_file_content)
    original_size = file_instance.size_bytes

    # Update with larger content
    new_content = ContentFile(b'a' * 100, name='test.txt')  # 100 bytes
    update_file_content(file_instance.id, new_content)

    # Check quota was adjusted
    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 100  # New size, not original


@pytest.mark.django_db
def test_update_file_content_adjusts_usage_decrease(
    user,
    mock_s3,
):
    """Test update_file_content adjusts quota for size decrease."""
    # Create initial file with larger content
    storage_path = f'{user.id}/test.txt'
    large_content = ContentFile(b'a' * 100, name='test.txt')
    file_instance = upload_file(user, storage_path, large_content)

    # Update with smaller content
    small_content = ContentFile(b'small', name='test.txt')  # 5 bytes
    update_file_content(file_instance.id, small_content)

    # Check quota was adjusted down
    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 5


@pytest.mark.django_db
def test_update_file_content_raises_quota_exceeded(user, mock_s3):
    """Test update_file_content raises QuotaExceededError for size increase."""
    storage_path = f'{user.id}/test.txt'
    small_content = ContentFile(b'small', name='test.txt')  # 5 bytes

    # Create initial small file
    file_instance = upload_file(user, storage_path, small_content)

    # Set quota that would be exceeded by larger update
    quota = UserQuota.objects.get(user=user)
    quota.quota_bytes = 10  # Only 10 bytes total
    quota.save()

    # Try to update with larger content
    large_content = ContentFile(b'a' * 100, name='test.txt')

    with pytest.raises(QuotaExceededError):
        update_file_content(file_instance.id, large_content)


@pytest.mark.django_db
def test_update_file_content_size_decrease_no_quota_check(user, mock_s3):
    """Test update with smaller content doesn't check quota."""
    storage_path = f'{user.id}/test.txt'
    large_content = ContentFile(b'a' * 100, name='test.txt')

    # Create initial large file
    file_instance = upload_file(user, storage_path, large_content)

    # Set quota to 0 (over quota)
    quota = UserQuota.objects.get(user=user)
    quota.quota_bytes = 50  # Now technically over quota
    quota.save()

    # Updating to smaller content should still work
    small_content = ContentFile(b'small', name='test.txt')
    update_file_content(file_instance.id, small_content)

    # File should be updated
    file_instance.refresh_from_db()
    assert file_instance.size_bytes == 5
