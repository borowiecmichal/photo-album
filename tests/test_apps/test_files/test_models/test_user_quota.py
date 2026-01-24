"""Tests for UserQuota model."""

import pytest
from django.db import IntegrityError

from server.apps.files.models import UserQuota


@pytest.mark.django_db
def test_create_user_quota(user):
    """Test creating a UserQuota instance."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1024 * 1024 * 1024,  # 1 GB
        used_bytes=0,
    )

    assert quota.user == user
    assert quota.quota_bytes == 1024 * 1024 * 1024
    assert quota.used_bytes == 0


@pytest.mark.django_db
def test_user_quota_default_values(user):
    """Test UserQuota default values."""
    quota = UserQuota.objects.create(user=user)

    # Default quota is 10 GB
    assert quota.quota_bytes == 10 * 1024 * 1024 * 1024
    assert quota.used_bytes == 0


@pytest.mark.django_db
def test_user_quota_one_to_one_constraint(user):
    """Test that a user can only have one quota record."""
    UserQuota.objects.create(user=user)

    with pytest.raises(IntegrityError):
        UserQuota.objects.create(user=user)


@pytest.mark.django_db
def test_user_quota_str_representation(user):
    """Test UserQuota string representation."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1024,
        used_bytes=512,
    )

    assert str(quota) == f'{user.username}: 512/1024'


@pytest.mark.django_db
def test_has_space_for_with_enough_space(user):
    """Test has_space_for when there's enough space."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=400,
    )

    assert quota.has_space_for(500) is True
    assert quota.has_space_for(600) is True


@pytest.mark.django_db
def test_has_space_for_without_enough_space(user):
    """Test has_space_for when there's not enough space."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=400,
    )

    assert quota.has_space_for(601) is False
    assert quota.has_space_for(1000) is False


@pytest.mark.django_db
def test_has_space_for_exactly_at_limit(user):
    """Test has_space_for when usage would exactly meet quota."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=400,
    )

    # Exactly at limit is allowed
    assert quota.has_space_for(600) is True


@pytest.mark.django_db
def test_has_space_for_zero_bytes(user):
    """Test has_space_for with zero bytes."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=1000,
    )

    # Zero bytes should always have space
    assert quota.has_space_for(0) is True


@pytest.mark.django_db
def test_available_bytes(user):
    """Test available_bytes calculation."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=400,
    )

    assert quota.available_bytes() == 600


@pytest.mark.django_db
def test_available_bytes_when_over_quota(user):
    """Test available_bytes when over quota returns 0."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=1200,
    )

    assert quota.available_bytes() == 0


@pytest.mark.django_db
def test_available_bytes_when_exactly_at_quota(user):
    """Test available_bytes when exactly at quota."""
    quota = UserQuota.objects.create(
        user=user,
        quota_bytes=1000,
        used_bytes=1000,
    )

    assert quota.available_bytes() == 0


@pytest.mark.django_db
def test_quota_bytes_non_negative_constraint(user):
    """Test that quota_bytes must be non-negative."""
    quota = UserQuota(
        user=user,
        quota_bytes=-100,
        used_bytes=0,
    )

    with pytest.raises(IntegrityError):
        quota.save()


@pytest.mark.django_db
def test_used_bytes_non_negative_constraint(user):
    """Test that used_bytes must be non-negative."""
    quota = UserQuota(
        user=user,
        quota_bytes=1000,
        used_bytes=-100,
    )

    with pytest.raises(IntegrityError):
        quota.save()


@pytest.mark.django_db
def test_user_quota_cascade_delete(user):
    """Test that UserQuota is deleted when user is deleted."""
    quota = UserQuota.objects.create(user=user)
    quota_pk = quota.pk

    user.delete()

    assert not UserQuota.objects.filter(pk=quota_pk).exists()


@pytest.mark.django_db
def test_user_quota_related_name(user):
    """Test that quota can be accessed via user.quota."""
    quota = UserQuota.objects.create(user=user)

    assert user.quota == quota
