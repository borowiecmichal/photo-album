"""Django storage configuration for S3-compatible backends.

This module configures django-storages to work with:
- MinIO for local development
- Cloudflare R2 for production

Both are S3-compatible and use the same S3Storage backend.
"""

from typing import Any, Final

from server.settings.components import config

# Storage configuration dictionary
# Uses S3-compatible storage for user files, local storage for static files
STORAGES: Final[dict[str, dict[str, Any]]] = {
    'default': {
        'BACKEND': 'server.apps.files.infrastructure.storage.FileStorage',
        'OPTIONS': {
            'bucket_name': config('AWS_STORAGE_BUCKET_NAME'),
            'access_key': config('AWS_ACCESS_KEY_ID'),
            'secret_key': config('AWS_SECRET_ACCESS_KEY'),
            'endpoint_url': config(
                'AWS_S3_ENDPOINT_URL',
                default=None,
            ),
            'region_name': config(
                'AWS_S3_REGION_NAME',
                default='auto',
            ),
            'file_overwrite': False,  # Prevent accidental overwrites
            'default_acl': None,  # Inherit bucket ACL
        },
    },
    'staticfiles': {
        # Keep static files separate from user files
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}
