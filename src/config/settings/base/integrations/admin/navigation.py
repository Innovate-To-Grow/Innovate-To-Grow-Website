"""Unfold sidebar navigation and request-dependent visibility callbacks."""

from apps.core.utils.access import user_can_access_app

from .tabs import SERVICE_CREDENTIAL_MODELS

# Broadcast Delivery → Email Sending Method: its page, each method's test page and the switch. Not under
# /admin/mail/settings/, so no Delivery Operations tab (and with it that sidebar entry) claims them too.
_SENDING_METHOD_PATH = "/admin/mail/sending-method/"


def _can(app_label):
    """Sidebar visibility callback: show only if the member can access ``app_label``."""
    return lambda request: user_can_access_app(request.user, app_label)


def _can_any(*app_labels):
    """Sidebar visibility callback: show if the member can access any of ``app_labels``."""
    return lambda request: any(user_can_access_app(request.user, label) for label in app_labels)


def _can_open_legacy_viewer(request):
    # Read the flag at request time: settings modules cannot import the
    # legacy_access service (it loads models before the app registry is ready).
    from django.conf import settings

    return getattr(settings, "LEGACY_VIEW_ENABLED", False) is True and user_can_access_app(request.user, "core")


def _is_system_intelligence_chat(request):
    path = request.path
    return path.startswith("/admin/system-intelligence/") and not path.startswith("/admin/system-intelligence/usage/")


def _is_service_credentials(request):
    # One sidebar entry for the whole Service Credentials tab group, highlighted on every tab's pages.
    return any(request.path.startswith(f"/admin/{model.replace('.', '/')}/") for model in SERVICE_CREDENTIAL_MODELS)


def _is_mail_delivery_operations(request):
    return request.path.startswith(
        ("/admin/mail/delivery-dashboard/", "/admin/mail/email-monitoring/", "/admin/mail/settings/")
    )


def _is_email_sending_method(request):
    return request.path.startswith(_SENDING_METHOD_PATH)


SIDEBAR = {
    "show_search": True,
    "navigation": [
        {
            "title": "Content Management System",
            "permission": _can("cms"),
            "items": [
                {"title": "Page Content", "link": "/admin/cms/cmspage/", "permission": _can("cms")},
                {
                    "title": "Route Redirects",
                    "link": "/admin/cms/routeredirect/",
                    "permission": _can("cms"),
                },
                {"title": "News Management", "link": "/admin/cms/newsarticle/", "permission": _can("cms")},
                {"title": "Page Analytics", "link": "/admin/cms/pageview/", "permission": _can("cms")},
            ],
        },
        {
            "title": "Events",
            "permission": _can("event"),
            "items": [
                {"title": "Events & Registrations", "link": "/admin/event/event/", "permission": _can("event")},
                {
                    "title": "Current Projects & Schedule",
                    "link": "/admin/event/currentprojectschedule/",
                    "permission": _can("event"),
                },
            ],
        },
        {
            "title": "Projects",
            "permission": _can("projects"),
            "items": [
                {"title": "Projects", "link": "/admin/projects/project/", "permission": _can("projects")},
                {
                    "title": "Project Resources",
                    "link": "/admin/projects/pastprojectssheetconfig/",
                    "permission": _can("projects"),
                },
            ],
        },
        {
            "title": "Members & Authentication",
            "permission": _can("authn"),
            "items": [
                {"title": "Members", "link": "/admin/authn/member/", "permission": _can("authn")},
                {"title": "Emails & Phones", "link": "/admin/authn/contactemail/", "permission": _can("authn")},
                {
                    "title": "Admin Invitations",
                    "link": "/admin/authn/admininvitation/",
                    "permission": _can("authn"),
                },
            ],
        },
        {
            "title": "Broadcast Delivery",
            "permission": _can("mail"),
            "items": [
                {
                    "title": "Delivery Operations",
                    "link": "/admin/mail/delivery-dashboard/",
                    "permission": _can("mail"),
                    "active": _is_mail_delivery_operations,
                },
                {
                    "title": "Email Sending Method",
                    "link": _SENDING_METHOD_PATH,
                    "permission": _can("mail"),
                    "active": _is_email_sending_method,
                },
                {"title": "Broadcast Campaigns", "link": "/admin/mail/emailcampaign/", "permission": _can("mail")},
                {"title": "Gmail Inbox", "link": "/admin/mail/inbox/", "permission": _can("mail")},
            ],
        },
        {
            "title": "System Intelligence",
            "permission": _can("system_intelligence"),
            "items": [
                {
                    "title": "Chat",
                    "link": "/admin/system-intelligence/",
                    "permission": _can("system_intelligence"),
                    "active": _is_system_intelligence_chat,
                },
                {
                    "title": "Assistant Tools",
                    "link": "/admin/system_intelligence/systemintelligenceconfig/",
                    "permission": _can("system_intelligence"),
                },
            ],
        },
        {
            "title": "Site Settings",
            "permission": _can_any("core", "admin"),
            "items": [
                {
                    "title": "Site Maintenance Control",
                    "link": "/admin/core/sitemaintenancecontrol/",
                    "permission": _can("core"),
                },
                {
                    "title": "Service Credentials",
                    "link": "/admin/core/awscredentialconfig/",
                    "permission": _can("core"),
                    "active": _is_service_credentials,
                },
                {"title": "Request Limits", "link": "/admin/core/request-limits/", "permission": _can("core")},
                {
                    "title": "Legacy Viewer",
                    "link": "/admin/legacy-view/",
                    "permission": _can_open_legacy_viewer,
                },
                {"title": "Admin Log", "link": "/admin/admin/logentry/", "permission": _can("admin")},
            ],
        },
        {
            "title": "CLI Admin",
            "permission": _can("cli_admin"),
            "items": [
                {
                    "title": "CLI Access & Audit",
                    "link": "/admin/cli_admin/cliaccesstoken/",
                    "permission": _can("cli_admin"),
                },
            ],
        },
    ],
}
