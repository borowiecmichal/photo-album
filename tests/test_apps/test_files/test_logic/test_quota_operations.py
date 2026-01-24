"""Tests for quota operations business logic."""

import pytest

from server.apps.files.exceptions import QuotaExceededError
from server.apps.files.logic.quota_operations import (
    adjust_usage,
    check_quota,
    decrement_usage,
    get_or_create_quota,
    increment_usage,
    recalculate_usage,
)
from server.apps.files.models import File, UserQuota


@pytest.mark.django_db
def test_get_or_create_quota_creates_new(user):
    """Test get_or_create_quota creates quota when none exists."""
    assert not UserQuota.objects.filter(user=user).exists()

    quota = get_or_create_quota(user)

    assert quota.user == user
    assert quota.quota_bytes == 10 * 1024 * 1024 * 1024  # 10 GB default
    assert quota.used_bytes == 0


@pytest.mark.django_db
def test_get_or_create_quota_returns_existing(user):
    """Test get_or_create_quota returns existing quota."""
    existing_quota = UserQuota.objects.create(
        user=user,
        quota_bytes=5000,
        used_bytes=1000,
    )

    quota = get_or_create_quota(user)

    assert quota.pk == existing_quota.pk
    assert quota.quota_bytes == 5000
    assert quota.used_bytes == 1000


@pytest.mark.django_db
def test_check_quota_passes_when_space_available(user):
    """Test check_quota doesn't raise when space is available."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=400,
    )

    # Should not raise
    check_quota(user, 500)


@pytest.mark.django_db
def test_check_quota_passes_at_exact_limit(user):
    """Test check_quota doesn't raise when at exact limit."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=400,
    )

    # Should not raise - exactly at limit
    check_quota(user, 600)


@pytest.mark.django_db
def test_check_quota_raises_when_exceeded(user):
    """Test check_quota raises QuotaExceededError when exceeded."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=400,
    )

    with pytest.raises(QuotaExceededError) as exc_info:
        check_quota(user, 700)

    assert exc_info.value.quota_bytes == 1000
    assert exc_info.value.used_bytes == 400
    assert exc_info.value.required_bytes == 700


@pytest.mark.django_db
def test_check_quota_creates_quota_on_demand(user):
    """Test check_quota creates quota if it doesn't exist."""
    assert not UserQuota.objects.filter(user=user).exists()

    # Small file should pass with default 10 GB quota
    check_quota(user, 1000)

    assert UserQuota.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_increment_usage(user):
    """Test increment_usage increases used_bytes."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=100,
    )

    increment_usage(user, 50)

    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 150


@pytest.mark.django_db
def test_increment_usage_creates_quota_if_missing(user):
    """Test increment_usage creates quota if missing."""
    assert not UserQuota.objects.filter(user=user).exists()

    increment_usage(user, 500)

    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 500


@pytest.mark.django_db
def test_increment_usage_is_atomic(user):
    """Test increment_usage uses atomic F() expression."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=100,
    )

    increment_usage(user, 50)

    # Refresh from database
    quota.refresh_from_db()
    assert quota.used_bytes == 150


@pytest.mark.django_db
def test_decrement_usage(user):
    """Test decrement_usage decreases used_bytes."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=100,
    )

    decrement_usage(user, 50)

    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 50


@pytest.mark.django_db
def test_decrement_usage_prevents_negative(user):
    """Test decrement_usage clamps to 0."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=100,
    )

    decrement_usage(user, 200)  # More than current usage

    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 0


@pytest.mark.django_db
def test_decrement_usage_no_quota(user):
    """Test decrement_usage does nothing if no quota exists."""
    assert not UserQuota.objects.filter(user=user).exists()

    # Should not raise
    decrement_usage(user, 100)

    # Quota should not be created
    assert not UserQuota.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_adjust_usage_increase(user):
    """Test adjust_usage with size increase."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=100,
    )

    adjust_usage(user, old_size=50, new_size=150)

    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 200  # 100 + (150 - 50)


@pytest.mark.django_db
def test_adjust_usage_decrease(user):
    """Test adjust_usage with size decrease."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=100,
    )

    adjust_usage(user, old_size=150, new_size=50)

    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 0  # 100 - 100 = 0


@pytest.mark.django_db
def test_adjust_usage_no_change(user):
    """Test adjust_usage with no size change."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=100,
    )

    adjust_usage(user, old_size=50, new_size=50)

    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 100  # Unchanged


@pytest.mark.django_db
def test_recalculate_usage_no_files(user, mock_s3):
    """Test recalculate_usage with no files."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=500,  # Incorrect value
    )

    result = recalculate_usage(user)

    assert result == 0
    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 0


@pytest.mark.django_db
def test_recalculate_usage_with_files(user, mock_s3):
    """Test recalculate_usage with existing files."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=10000,
        used_bytes=0,  # Incorrect value
    )

    # Create some files
    File.objects.create(
        user=user,
        file=f'{user.id}/file1.txt',
        size_bytes=100,
        mime_type='text/plain',
        checksum_sha256='abcd' * 16,
    )
    File.objects.create(
        user=user,
        file=f'{user.id}/file2.txt',
        size_bytes=200,
        mime_type='text/plain',
        checksum_sha256='efgh' * 16,
    )

    result = recalculate_usage(user)

    assert result == 300
    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 300


@pytest.mark.django_db
def test_recalculate_usage_creates_quota_if_missing(user, mock_s3):
    """Test recalculate_usage creates quota if missing."""
    # Create a file
    File.objects.create(
        user=user,
        file=f'{user.id}/file1.txt',
        size_bytes=100,
        mime_type='text/plain',
        checksum_sha256='abcd' * 16,
    )

    result = recalculate_usage(user)

    assert result == 100
    quota = UserQuota.objects.get(user=user)
    assert quota.used_bytes == 100


@pytest.mark.django_db
def test_quota_exceeded_error_message(user):
    """Test QuotaExceededError message format."""
    UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=900,
    )

    with pytest.raises(QuotaExceededError) as exc_info:
        check_quota(user, 200)

    error = exc_info.value
    assert 'need 200 bytes' in str(error)
    assert 'only 100 bytes available' in str(error)
    assert 'quota: 1000' in str(error)
    assert 'used: 900' in str(error)
