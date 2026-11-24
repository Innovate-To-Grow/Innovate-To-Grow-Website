"""Who sees each sidebar entry and when it is marked active: the request-dependent callbacks ``navigation`` uses."""

from apps.core.utils.access import user_is_admin

from .tabs import SERVICE_CREDENTIAL_MODELS

# Broadcast Delivery → Email Sending Method: its page, each method's test page and the switch. Not under
# /admin/mail/settings/, so no Delivery Operations tab (and with it that sidebar entry) claims them too.
_SENDING_METHOD_PATH = "/admin/mail/sending-method/"
_HELPDESK_TICKETS_PATH = "/admin/helpdesk/ticket/"


def _is_admin(request):
    """Sidebar visibility callback: every entry is shown to every Admin (and nobody else reaches the admin)."""
    return user_is_admin(request.user)


def _can_open_legacy_viewer(request):
    # Read the flag at request time: settings modules cannot import the
    # legacy_access service (it loads models before the app registry is ready).
    from django.conf import settings

    return getattr(settings, "LEGACY_VIEW_ENABLED", False) is True and user_is_admin(request.user)


def _is_system_intelligence_chat(request):
    path = request.path
    return path.startswith("/admin/system-intelligence/") and not path.startswith("/admin/system-intelligence/usage/")


def _is_service_credentials(request):
    # One sidebar entry for the whole Service Credentials tab group, highlighted on every tab's pages.
    return any(request.path.startswith(f"/admin/{model.replace('.', '/')}/") for model in SERVICE_CREDENTIAL_MODELS)


def _is_mail_delivery_operations(request):
    # Every page of the Delivery Operations tabs: Email Monitoring (all its tabs and drill-downs), Notification Delivery
    # and Delivery Rates. The old /admin/mail/delivery-dashboard/ only redirects to Email Monitoring → Amazon SES.
    return request.path.startswith(("/admin/mail/email-monitoring/", "/admin/mail/settings/"))


def _is_email_sending_method(request):
    return request.path.startswith(_SENDING_METHOD_PATH)


def _helpdesk_queue_view(name):
    """Sidebar "active" callback for one view of the ticket list (the four views share one path)."""

    def active(request):
        if not request.path.startswith(_HELPDESK_TICKETS_PATH):
            return False
        mail, assignee = request.GET.get("mail", ""), request.GET.get("assignee", "")
        if mail in ("automated", "all"):
            return name == "automated"
        return {"me": "mine", "none": "unassigned"}.get(assignee, "queue") == name

    return active
