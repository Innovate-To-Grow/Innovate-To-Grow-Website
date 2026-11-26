"""Unfold sidebar navigation. Its request-dependent visibility callbacks are in ``visibility``."""

from .system_intelligence import SYSTEM_INTELLIGENCE_SECTION
from .visibility import (
    _SENDING_METHOD_PATH,
    _can_open_legacy_viewer,
    _helpdesk_link,
    _helpdesk_view_item,
    _is_admin,
    _is_email_sending_method,
    _is_mail_delivery_operations,
    _is_service_credentials,
)

SIDEBAR = {
    "show_search": True,
    "navigation": [
        {
            "title": "Content Management System",
            "permission": _is_admin,
            "items": [
                {"title": "Page Content", "link": "/admin/cms/cmspage/", "permission": _is_admin},
                {
                    "title": "Route Redirects",
                    "link": "/admin/cms/routeredirect/",
                    "permission": _is_admin,
                },
                {"title": "News Management", "link": "/admin/cms/newsarticle/", "permission": _is_admin},
                {"title": "Page Analytics", "link": "/admin/cms/pageview/", "permission": _is_admin},
            ],
        },
        {
            "title": "Events",
            "permission": _is_admin,
            "items": [
                {"title": "Events & Registrations", "link": "/admin/event/event/", "permission": _is_admin},
                {
                    "title": "Current Projects & Schedule",
                    "link": "/admin/event/currentprojectschedule/",
                    "permission": _is_admin,
                },
            ],
        },
        {
            "title": "Projects",
            "permission": _is_admin,
            "items": [
                {"title": "Projects", "link": "/admin/projects/project/", "permission": _is_admin},
                {
                    "title": "Project Resources",
                    "link": "/admin/projects/pastprojectssheetconfig/",
                    "permission": _is_admin,
                },
            ],
        },
        {
            "title": "Members & Authentication",
            "permission": _is_admin,
            "items": [
                {"title": "Members", "link": "/admin/authn/member/", "permission": _is_admin},
                {"title": "Emails & Phones", "link": "/admin/authn/contactemail/", "permission": _is_admin},
                {
                    "title": "Admin Invitations",
                    "link": "/admin/authn/admininvitation/",
                    "permission": _is_admin,
                },
            ],
        },
        {
            "title": "Broadcast Delivery",
            "permission": _is_admin,
            "items": [
                {
                    "title": "Delivery Operations",
                    "link": "/admin/mail/email-monitoring/",
                    "permission": _is_admin,
                    "active": _is_mail_delivery_operations,
                },
                {
                    "title": "Email Sending Method",
                    "link": _SENDING_METHOD_PATH,
                    "permission": _is_admin,
                    "active": _is_email_sending_method,
                },
                {"title": "Broadcast Campaigns", "link": "/admin/mail/emailcampaign/", "permission": _is_admin},
                {
                    "title": "Inbox",
                    "link": "/admin/mail/inbox/",
                    "permission": _is_admin,
                    # Unread mail across every connected inbox account, from the background poller.
                    "badge": "apps.mail.admin.inbox.badge.inbox_unread_badge",
                },
            ],
        },
        {
            "title": "Helpdesk",
            "permission": _is_admin,
            "items": [
                _helpdesk_view_item("Queue", "", "queue"),
                _helpdesk_view_item("My Tickets", "?assignee=me", "mine"),
                _helpdesk_view_item("My Groups", "?group=mine", "groups"),
                _helpdesk_view_item("Unassigned", "?assignee=none", "unassigned"),
                _helpdesk_view_item("SLA Breached", "?sla=breached", "breached"),
                _helpdesk_view_item("Automated & Spam", "?mail=automated&status=any", "automated"),
                _helpdesk_link("Ingest Problems", "ingestrecord"),
                _helpdesk_link("Categories", "ticketcategory"),
                _helpdesk_link("Assignment Groups", "assignmentgroup"),
                _helpdesk_link("SLA Targets", "slatarget"),
                _helpdesk_link("Response Templates", "responsetemplate"),
                _helpdesk_link("Settings", "helpdesksettings"),
            ],
        },
        SYSTEM_INTELLIGENCE_SECTION,
        {
            "title": "Site Settings",
            "permission": _is_admin,
            "items": [
                {
                    "title": "Site Maintenance Control",
                    "link": "/admin/core/sitemaintenancecontrol/",
                    "permission": _is_admin,
                },
                {
                    "title": "Service Credentials",
                    "link": "/admin/core/awscredentialconfig/",
                    "permission": _is_admin,
                    "active": _is_service_credentials,
                },
                {"title": "Request Limits", "link": "/admin/core/request-limits/", "permission": _is_admin},
                {
                    "title": "Legacy Viewer",
                    "link": "/admin/legacy-view/",
                    "permission": _can_open_legacy_viewer,
                },
                {"title": "Admin Log", "link": "/admin/admin/logentry/", "permission": _is_admin},
            ],
        },
        {
            "title": "CLI Admin",
            "permission": _is_admin,
            "items": [
                {
                    "title": "CLI Access & Audit",
                    "link": "/admin/cli_admin/cliaccesstoken/",
                    "permission": _is_admin,
                },
            ],
        },
    ],
}
