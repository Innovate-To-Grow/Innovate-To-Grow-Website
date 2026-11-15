"""Unfold sidebar navigation. Its request-dependent visibility callbacks are in ``visibility``."""

from .visibility import (
    _HELPDESK_TICKETS_PATH,
    _SENDING_METHOD_PATH,
    _can,
    _can_any,
    _can_open_legacy_viewer,
    _helpdesk_queue_view,
    _is_email_sending_method,
    _is_mail_delivery_operations,
    _is_service_credentials,
    _is_system_intelligence_chat,
)

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
                    "link": "/admin/mail/email-monitoring/",
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
            "title": "Helpdesk",
            "permission": _can("helpdesk"),
            "items": [
                {
                    "title": "Queue",
                    "link": _HELPDESK_TICKETS_PATH,
                    "permission": _can("helpdesk"),
                    "active": _helpdesk_queue_view("queue"),
                },
                {
                    "title": "My Tickets",
                    "link": f"{_HELPDESK_TICKETS_PATH}?assignee=me",
                    "permission": _can("helpdesk"),
                    "active": _helpdesk_queue_view("mine"),
                },
                {
                    "title": "Unassigned",
                    "link": f"{_HELPDESK_TICKETS_PATH}?assignee=none",
                    "permission": _can("helpdesk"),
                    "active": _helpdesk_queue_view("unassigned"),
                },
                {
                    "title": "Automated & Spam",
                    "link": f"{_HELPDESK_TICKETS_PATH}?mail=automated&status=any",
                    "permission": _can("helpdesk"),
                    "active": _helpdesk_queue_view("automated"),
                },
                {"title": "Ingest Problems", "link": "/admin/helpdesk/ingestrecord/", "permission": _can("helpdesk")},
                {"title": "Categories", "link": "/admin/helpdesk/ticketcategory/", "permission": _can("helpdesk")},
                {"title": "Settings", "link": "/admin/helpdesk/helpdesksettings/", "permission": _can("helpdesk")},
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
