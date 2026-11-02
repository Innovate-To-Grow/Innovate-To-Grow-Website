"""The access check every Notification Delivery view runs."""

from django.core.exceptions import PermissionDenied

from apps.core.utils.access import user_can_access_app


def _require_mail_access(request):
    # ``admin_view`` only enforces is_staff, so these custom URLs must re-check
    # per-app access themselves — Django never runs the per-app model permissions
    # for a standalone admin view.
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access mail settings.")
