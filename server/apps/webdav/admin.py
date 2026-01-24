"""Django admin configuration for webdav app."""

from typing import override

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from server.apps.webdav.models import WebDAVSession


@admin.register(WebDAVSession)
class WebDAVSessionAdmin(admin.ModelAdmin[WebDAVSession]):
    """Admin interface for WebDAVSession model."""

    list_display = [
        'session_id_short',
        'user',
        'ip_address',
        'user_agent_short',
        'started_at',
        'last_activity',
    ]

    list_filter = [
        'user',
        'started_at',
        'last_activity',
    ]

    search_fields = [
        'session_id',
        'user__username',
        'ip_address',
        'user_agent',
    ]

    readonly_fields = [
        'session_id',
        'ip_address',
        'user_agent',
        'started_at',
        'last_activity',
    ]

    fieldsets = (
        ('Session Information', {
            'fields': ('session_id', 'user', 'ip_address', 'user_agent'),
        }),
        ('Timestamps', {
            'fields': ('started_at', 'last_activity'),
        }),
    )

    def session_id_short(self, obj: WebDAVSession) -> str:
        """Display truncated session ID.

        Args:
            obj: WebDAVSession instance.

        Returns:
            First 8 characters of session ID.
        """
        return obj.session_id[:8]
    session_id_short.short_description = 'Session ID'  # type: ignore[attr-defined]

    def user_agent_short(self, obj: WebDAVSession) -> str:
        """Display truncated user agent.

        Args:
            obj: WebDAVSession instance.

        Returns:
            First 50 characters of user agent or dash if empty.
        """
        if obj.user_agent:
            if len(obj.user_agent) > 50:
                return f'{obj.user_agent[:50]}...'
            return obj.user_agent
        return '-'
    user_agent_short.short_description = 'User Agent'  # type: ignore[attr-defined]

    @override
    def get_queryset(self, request: HttpRequest) -> QuerySet[WebDAVSession]:
        """Optimize queryset with select_related.

        Args:
            request: HTTP request.

        Returns:
            Optimized QuerySet.
        """
        return super().get_queryset(request).select_related('user')

    @override
    def has_add_permission(self, request: HttpRequest) -> bool:
        """Disable adding sessions via admin.

        Sessions should only be created via WebDAV connections.

        Args:
            request: HTTP request.

        Returns:
            False - sessions cannot be added manually.
        """
        return False

    @override
    def has_change_permission(
        self,
        request: HttpRequest,
        obj: WebDAVSession | None = None,
    ) -> bool:
        """Disable editing sessions via admin.

        Sessions are managed automatically.

        Args:
            request: HTTP request.
            obj: Optional WebDAVSession instance.

        Returns:
            False - sessions cannot be edited.
        """
        return False
