"""The access check every Notification Delivery view runs."""

from django.core.exceptions import PermissionDenied

from apps.core.utils.access import user_can_access_app


def _require_mail_access(request):
    # A plain Admin check, in case one of these URLs is ever mounted without ``admin_view``.
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access mail settings.")
