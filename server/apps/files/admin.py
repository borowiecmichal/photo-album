"""Django admin configuration for files app."""


from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html

from server.apps.files.models import File, Tag, UserQuota


@admin.register(File)
class FileAdmin(admin.ModelAdmin[File]):
    """Admin interface for File model."""

    list_display = [
        'filename_display',
        'user',
        'folder_path_display',
        'size_display',
        'mime_type',
        'uploaded_at',
    ]

    list_filter = [
        'mime_type',
        'uploaded_at',
        'user',
    ]

    search_fields = [
        'file',  # Searches file.name field
        'checksum_sha256',
    ]

    readonly_fields = [
        'file',
        'size_bytes',
        'mime_type',
        'checksum_sha256',
        'uploaded_at',
        'modified_at',
    ]

    filter_horizontal = ['tags']  # Better UX for M2M relationship

    fieldsets = (
        ('File Information', {
            'fields': ('file', 'user'),
        }),
        ('Metadata', {
            'fields': (
                'size_bytes',
                'mime_type',
                'checksum_sha256',
            ),
        }),
        ('Tags', {
            'fields': ('tags',),
        }),
        ('Timestamps', {
            'fields': ('uploaded_at', 'modified_at'),
        }),
    )

    def filename_display(self, obj: File) -> str:
        """Display filename extracted from file.name.

        Args:
            obj: File instance.

        Returns:
            Filename without path.
        """
        return obj.get_filename()
    filename_display.short_description = 'Filename'  # type: ignore[attr-defined]

    def folder_path_display(self, obj: File) -> str:
        """Display folder path extracted from file.name.

        Args:
            obj: File instance.

        Returns:
            Folder path without filename.
        """
        return obj.get_folder_path()
    folder_path_display.short_description = 'Folder'  # type: ignore[attr-defined]

    def size_display(self, obj: File) -> str:
        """Display file size in human-readable format.

        Args:
            obj: File instance.

        Returns:
            Formatted size string (e.g., '1.5 MB', '234 KB').
        """
        size_bytes = obj.size_bytes

        # Convert to appropriate unit
        if size_bytes < 1024:
            return f'{size_bytes} B'
        if size_bytes < 1024 * 1024:  # noqa: WPS531
            return f'{size_bytes / 1024:.1f} KB'
        if size_bytes < 1024 * 1024 * 1024:  # noqa: WPS531
            return f'{size_bytes / (1024 * 1024):.1f} MB'
        return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'
    size_display.short_description = 'Size'  # type: ignore[attr-defined]

    def get_queryset(self, request: HttpRequest) -> QuerySet[File]:
        """Optimize queryset with select_related.

        Args:
            request: HTTP request.

        Returns:
            Optimized QuerySet.
        """
        return super().get_queryset(request).select_related('user')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin[Tag]):
    """Admin interface for Tag model."""

    list_display = [
        'name',
        'user',
        'color_display',
        'file_count',
        'created_at',
    ]

    list_filter = [
        'user',
        'created_at',
    ]

    search_fields = [
        'name',
    ]

    fieldsets = (
        ('Tag Information', {
            'fields': ('name', 'user', 'color'),
        }),
        ('Metadata', {
            'fields': ('created_at',),
        }),
    )

    readonly_fields = ['created_at']

    def color_display(self, obj: Tag) -> str:
        """Display color swatch with hex code.

        Args:
            obj: Tag instance.

        Returns:
            HTML formatted color swatch and code.
        """
        if obj.color:
            return format_html(
                '<span style="background-color: {color}; '
                'padding: 2px 10px; border: 1px solid #ccc;">'
                '&nbsp;</span> {color}',
                color=obj.color,
            )
        return '-'
    color_display.short_description = 'Color'  # type: ignore[attr-defined]

    def file_count(self, obj: Tag) -> int:
        """Count of files with this tag.

        Args:
            obj: Tag instance.

        Returns:
            Number of files tagged with this tag.
        """
        return obj.files.count()
    file_count.short_description = 'Files'  # type: ignore[attr-defined]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Tag]:
        """Optimize queryset with select_related.

        Args:
            request: HTTP request.

        Returns:
            Optimized QuerySet.
        """
        return super().get_queryset(request).select_related('user')


def _format_bytes(size_bytes: int) -> str:
    """Format bytes in human-readable format.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted size string (e.g., '1.5 MB', '234 KB').
    """
    if size_bytes < 1024:
        return f'{size_bytes} B'
    if size_bytes < 1024 * 1024:  # noqa: WPS531
        return f'{size_bytes / 1024:.1f} KB'
    if size_bytes < 1024 * 1024 * 1024:  # noqa: WPS531
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'


@admin.register(UserQuota)
class UserQuotaAdmin(admin.ModelAdmin[UserQuota]):
    """Admin interface for UserQuota model."""

    list_display = [
        'user',
        'quota_display',
        'used_display',
        'percentage_display',
        'status_display',
    ]

    list_filter = [
        'user',
    ]

    search_fields = [
        'user__username',
        'user__email',
    ]

    readonly_fields = [
        'user',
        'used_bytes',
    ]

    fieldsets = (
        ('User', {
            'fields': ('user',),
        }),
        ('Quota Settings', {
            'fields': ('quota_bytes',),
        }),
        ('Current Usage', {
            'fields': ('used_bytes',),
        }),
    )

    def quota_display(self, obj: UserQuota) -> str:
        """Display quota in human-readable format.

        Args:
            obj: UserQuota instance.

        Returns:
            Formatted quota string.
        """
        return _format_bytes(obj.quota_bytes)
    quota_display.short_description = 'Quota'  # type: ignore[attr-defined]

    def used_display(self, obj: UserQuota) -> str:
        """Display used bytes in human-readable format.

        Args:
            obj: UserQuota instance.

        Returns:
            Formatted used bytes string.
        """
        return _format_bytes(obj.used_bytes)
    used_display.short_description = 'Used'  # type: ignore[attr-defined]

    def percentage_display(self, obj: UserQuota) -> str:
        """Display percentage of quota used.

        Args:
            obj: UserQuota instance.

        Returns:
            Percentage string.
        """
        if obj.quota_bytes == 0:
            return '0%'
        percentage = (obj.used_bytes / obj.quota_bytes) * 100
        return f'{percentage:.1f}%'
    percentage_display.short_description = '%'  # type: ignore[attr-defined]

    def status_display(self, obj: UserQuota) -> str:
        """Display status indicator based on usage.

        Args:
            obj: UserQuota instance.

        Returns:
            HTML formatted status indicator.
        """
        if obj.quota_bytes == 0:
            percentage = 0.0
        else:
            percentage = (obj.used_bytes / obj.quota_bytes) * 100

        if percentage >= 100:
            color = '#dc3545'  # Red - over quota
            status = 'Over Quota'
        elif percentage >= 90:
            color = '#ffc107'  # Yellow - warning
            status = 'Warning'
        else:
            color = '#28a745'  # Green - ok
            status = 'OK'

        return format_html(
            '<span style="color: {color}; font-weight: bold;">'
            '{status}</span>',
            color=color,
            status=status,
        )
    status_display.short_description = 'Status'  # type: ignore[attr-defined]

    def get_queryset(self, request: HttpRequest) -> QuerySet[UserQuota]:
        """Optimize queryset with select_related.

        Args:
            request: HTTP request.

        Returns:
            Optimized QuerySet.
        """
        return super().get_queryset(request).select_related('user')
