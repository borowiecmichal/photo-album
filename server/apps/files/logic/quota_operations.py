"""Business logic for storage quota operations."""

import logging
from typing import Any

from django.db import transaction
from django.db.models import F, Sum  # noqa: WPS347

from server.apps.files.exceptions import QuotaExceededError
from server.apps.files.models import File, UserQuota

# User type for Django's dynamic user model
_User = Any

# Field name constant to avoid string literal over-use
_USED_BYTES_FIELD = 'used_bytes'  # noqa: WPS226

logger = logging.getLogger(__name__)


def get_or_create_quota(user: _User) -> UserQuota:
    """Get or create quota for user (on-demand creation).

    Args:
        user: User to get quota for.

    Returns:
        UserQuota instance for the user.
    """
    quota, created = UserQuota.objects.get_or_create(user=user)
    if created:
        logger.info(
            'Created quota for user %s: %d bytes',
            user.username,
            quota.quota_bytes,
        )
    return quota


def check_quota(user: _User, size_bytes: int) -> None:
    """Check if user has enough quota for an upload.

    Creates quota on-demand if it doesn't exist.

    Args:
        user: User to check quota for.
        size_bytes: Size of the upload in bytes.

    Raises:
        QuotaExceededError: If upload would exceed quota.
    """
    quota = get_or_create_quota(user)

    if not quota.has_space_for(size_bytes):
        logger.warning(
            'Quota exceeded for user %s: need %d, have %d available',
            user.username,
            size_bytes,
            quota.available_bytes(),
        )
        raise QuotaExceededError(
            quota_bytes=quota.quota_bytes,
            used_bytes=quota.used_bytes,
            required_bytes=size_bytes,
        )


def increment_usage(user: _User, size_bytes: int) -> None:
    """Atomically increment user's storage usage.

    Args:
        user: User to increment usage for.
        size_bytes: Bytes to add to usage.
    """
    with transaction.atomic():
        updated = UserQuota.objects.filter(user=user).update(
            used_bytes=F(_USED_BYTES_FIELD) + size_bytes,
        )

        if updated == 0:
            # Quota doesn't exist yet, create it
            quota = get_or_create_quota(user)
            quota.used_bytes = size_bytes
            quota.save(update_fields=[_USED_BYTES_FIELD])

    logger.debug(
        'Incremented usage for user %s by %d bytes',
        user.username,
        size_bytes,
    )


def decrement_usage(user: _User, size_bytes: int) -> None:
    """Atomically decrement user's storage usage.

    Prevents negative values by clamping to 0.

    Args:
        user: User to decrement usage for.
        size_bytes: Bytes to subtract from usage.
    """
    with transaction.atomic():
        # Get current quota to check if decrement would go negative
        try:
            quota = UserQuota.objects.select_for_update().get(user=user)
        except UserQuota.DoesNotExist:
            # No quota exists, nothing to decrement
            logger.debug(
                'No quota exists for user %s, skipping decrement',
                user.username,
            )
            return

        # Calculate new usage, clamping to 0
        new_usage = max(0, quota.used_bytes - size_bytes)
        quota.used_bytes = new_usage
        quota.save(update_fields=[_USED_BYTES_FIELD])

    logger.debug(
        'Decremented usage for user %s by %d bytes (new: %d)',
        user.username,
        size_bytes,
        new_usage,
    )


def adjust_usage(user: _User, old_size: int, new_size: int) -> None:
    """Adjust user's storage usage for content updates.

    Args:
        user: User to adjust usage for.
        old_size: Previous file size in bytes.
        new_size: New file size in bytes.
    """
    size_diff = new_size - old_size

    if size_diff > 0:
        increment_usage(user, size_diff)
    elif size_diff < 0:
        decrement_usage(user, -size_diff)
    # If size_diff == 0, no adjustment needed


def recalculate_usage(user: _User) -> int:
    """Recalculate user's storage usage from actual files.

    This is useful for fixing inconsistencies or after bulk operations.
    Includes files in trash since they still count against quota.

    Args:
        user: User to recalculate usage for.

    Returns:
        New calculated usage in bytes.
    """
    # Sum all file sizes for this user (including trash)
    total = File.all_objects.filter(user=user).aggregate(
        total=Sum('size_bytes'),
    )['total'] or 0

    # Update quota
    with transaction.atomic():
        quota = get_or_create_quota(user)
        old_usage = quota.used_bytes
        quota.used_bytes = total
        quota.save(update_fields=[_USED_BYTES_FIELD])

    logger.info(
        'Recalculated usage for user %s: %d -> %d bytes',
        user.username,
        old_usage,
        total,
    )

    return total
