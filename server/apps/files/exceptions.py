"""Exceptions for files app."""


class QuotaExceededError(Exception):
    """Raised when upload would exceed user's storage quota."""

    def __init__(
        self,
        quota_bytes: int,
        used_bytes: int,
        required_bytes: int,
    ) -> None:
        """Initialize QuotaExceededError.

        Args:
            quota_bytes: Total quota limit in bytes.
            used_bytes: Currently used bytes.
            required_bytes: Bytes needed for the operation.
        """
        self.quota_bytes = quota_bytes
        self.used_bytes = used_bytes
        self.required_bytes = required_bytes

        available = quota_bytes - used_bytes
        super().__init__(
            f'Quota exceeded: need {required_bytes} bytes, '
            f'only {available} bytes available '
            f'(quota: {quota_bytes}, used: {used_bytes})',
        )
