"""
Unfold admin theme configuration.

Defines branding (logo, title, colors) and the admin sidebar navigation
structure.  Sidebar items are organized by domain to match the Django app
layout.
"""

from django.templatetags.static import static

from apps.core.access import user_can_access_app


def _can(app_label):
    """Sidebar visibility callback: show only if the member can access ``app_label``."""
    return lambda request: user_can_access_app(request.user, app_label)


def _can_any(*app_labels):
    """Sidebar visibility callback: show if the member can access any of ``app_labels``."""
    return lambda request: any(user_can_access_app(request.user, label) for label in app_labels)


def _is_system_intelligence_chat(request):
    path = request.path
    return path.startswith("/admin/system-intelligence/") and not path.startswith("/admin/system-intelligence/usage/")


def _is_system_intelligence_usage(request):
    return request.path.startswith("/admin/system-intelligence/usage/")


UNFOLD = {
    "SITE_TITLE": "I2G Admin",
    "SITE_HEADER": "Innovate To Grow",
    "SITE_ICON": lambda request: static("images/i2glogo.png"),
    "SITE_LOGO": lambda request: static("images/i2glogo.png"),
    "COLORS": {
        "primary": {
            "50": "#f9f9ff",
            "100": "#ebf1ff",
            "200": "#d5e3ff",
            "300": "#a7c8ff",
            "400": "#82adf0",
            "500": "#6792d4",
            "600": "#305f9d",
            "700": "#0f4784",
            "800": "#003061",
            "900": "#001b3c",
            "950": "#001026",
        },
    },
    "STYLES": [
        lambda request: static("admin/css/google-material-admin.css"),
        lambda request: static("admin/css/tabs.css"),
        lambda request: static("admin/css/file-input.css"),
    ],
    "TABS": [
        {
            "models": [
                "core.awscredentialconfig",
                "core.gmailaccessaccount",
                "core.googlecredentialconfig",
            ],
            "items": [
                {"title": "AWS Credentials", "link": "/admin/core/awscredentialconfig/"},
                {"title": "Gmail Access Account", "link": "/admin/core/gmailaccessaccount/"},
                {"title": "Google Credentials", "link": "/admin/core/googlecredentialconfig/"},
            ],
        },
        {
            "models": ["event.event", "event.eventregistration", "event.checkin", "event.registrationsheetsynclog"],
            "items": [
                {"title": "Events", "link": "/admin/event/event/"},
                {"title": "Registrations", "link": "/admin/event/eventregistration/"},
                {"title": "Check-ins", "link": "/admin/event/checkin/"},
                {"title": "Registration Sync Logs", "link": "/admin/event/registrationsheetsynclog/"},
            ],
        },
        {
            "models": [
                "event.currentprojectschedule",
                "event.currentproject",
                "event.schedulesynclog",
            ],
            "items": [
                {"title": "Current Projects & Schedule", "link": "/admin/event/currentprojectschedule/"},
                {"title": "Current Projects (synced)", "link": "/admin/event/currentproject/"},
                {"title": "Schedule Sync Logs", "link": "/admin/event/schedulesynclog/"},
            ],
        },
        {
            "models": ["authn.contactemail", "authn.contactphone"],
            "items": [
                {"title": "Emails", "link": "/admin/authn/contactemail/"},
                {"title": "Phones", "link": "/admin/authn/contactphone/"},
            ],
        },
        {
            "models": ["cms.newsarticle", "cms.newsfeedsource", "cms.newssynclog"],
            "items": [
                {"title": "Articles", "link": "/admin/cms/newsarticle/"},
                {"title": "Feed Sources", "link": "/admin/cms/newsfeedsource/"},
                {"title": "Sync Logs", "link": "/admin/cms/newssynclog/"},
            ],
        },
        # projects.semester / projects.project are intentionally omitted from TABS.
        # Duplicating the same links in TABS and SIDEBAR triggers Unfold's
        # _get_is_tab_active(), which marks both sidebar rows active when either
        # changelist is open (peer tabs, not parent/child).
        # The sync-log is safe in TABS because it is NOT in the SIDEBAR (only the
        # config is), mirroring the event.currentprojectschedule grouping above.
        {
            "models": [
                "projects.pastprojectssheetconfig",
                "projects.pastprojectsynclog",
            ],
            "items": [
                {"title": "Past Projects Sheet", "link": "/admin/projects/pastprojectssheetconfig/"},
                {"title": "Past Project Sync Logs", "link": "/admin/projects/pastprojectsynclog/"},
            ],
        },
        {
            "models": [
                "cms.sitesettings",
                "cms.cmspage",
                "cms.cmsembedwidget",
                "cms.cmsembedallowedhost",
                "cms.menu",
                "cms.footercontent",
                "cms.stylesheet",
            ],
            "items": [
                {"title": "Home Page", "link": "/admin/cms/sitesettings/"},
                {"title": "Pages", "link": "/admin/cms/cmspage/"},
                {"title": "Embed Widgets", "link": "/admin/cms/cmsembedwidget/"},
                {"title": "Embed Allowed Hosts", "link": "/admin/cms/cmsembedallowedhost/"},
                {"title": "Menus", "link": "/admin/cms/menu/"},
                {"title": "Footer", "link": "/admin/cms/footercontent/"},
                {"title": "Style Sheets", "link": "/admin/cms/stylesheet/"},
            ],
        },
        {
            "models": ["mail.emailcampaign", "mail.recipientlog", "mail.smscampaign", "mail.smsrecipientlog"],
            "items": [
                {"title": "Broadcast Email", "link": "/admin/mail/emailcampaign/"},
                {"title": "Email Log", "link": "/admin/mail/recipientlog/"},
                {"title": "Broadcast SMS", "link": "/admin/mail/smscampaign/"},
                {"title": "SMS Log", "link": "/admin/mail/smsrecipientlog/"},
            ],
        },
        {
            "models": ["authn.membersheetsyncconfig", "authn.membersheetsynclog"],
            "items": [
                {"title": "Sync Config", "link": "/admin/authn/membersheetsyncconfig/"},
                {"title": "Sync Logs", "link": "/admin/authn/membersheetsynclog/"},
            ],
        },
    ],
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": "Content Management System",
                "permission": _can("cms"),
                "items": [
                    {"title": "Page Content", "link": "/admin/cms/cmspage/", "permission": _can("cms")},
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
                    {"title": "Semesters", "link": "/admin/projects/semester/", "permission": _can("projects")},
                    {
                        "title": "Past Projects Sheet",
                        "link": "/admin/projects/pastprojectssheetconfig/",
                        "permission": _can("projects"),
                    },
                    {
                        "title": "Shared Links",
                        "link": "/admin/projects/pastprojectshare/",
                        "permission": _can("projects"),
                    },
                ],
            },
            {
                "title": "Members & Authentication",
                "permission": _can("authn"),
                "items": [
                    {"title": "Members", "link": "/admin/authn/member/", "permission": _can("authn")},
                    {"title": "Contact Info", "link": "/admin/authn/contactemail/", "permission": _can("authn")},
                    {
                        "title": "Admin Invitations",
                        "link": "/admin/authn/admininvitation/",
                        "permission": _can("authn"),
                    },
                    {
                        "title": "Member Sheet Sync",
                        "link": "/admin/authn/membersheetsyncconfig/",
                        "permission": _can("authn"),
                    },
                ],
            },
            {
                "title": "Broadcast Delivery",
                "permission": _can("mail"),
                "items": [
                    {"title": "Broadcast Campaigns", "link": "/admin/mail/emailcampaign/", "permission": _can("mail")},
                    {"title": "Gmail Inbox", "link": "/admin/mail/inbox/", "permission": _can("mail")},
                    {"title": "Scam Detection", "link": "/admin/mail/scamdetectorconfig/", "permission": _can("mail")},
                    {"title": "Notification Delivery", "link": "/admin/mail/settings/", "permission": _can("mail")},
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
                        "title": "Assistant Settings",
                        "link": "/admin/system_intelligence/systemintelligenceconfig/",
                        "permission": _can("system_intelligence"),
                    },
                    {
                        "title": "Usage Dashboard",
                        "link": "/admin/system-intelligence/usage/",
                        "permission": _can("system_intelligence"),
                        "active": _is_system_intelligence_usage,
                    },
                    {
                        "title": "Conversation Logs",
                        "link": "/admin/system_intelligence/assistantconversationlog/",
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
                        "title": "Service Configs",
                        "link": "/admin/core/awscredentialconfig/",
                        "permission": _can("core"),
                    },
                    {"title": "Admin Log", "link": "/admin/admin/logentry/", "permission": _can("admin")},
                ],
            },
            {
                "title": "CLI Admin",
                "permission": _can("cli_admin"),
                "items": [
                    {
                        "title": "Access Tokens",
                        "link": "/admin/cli_admin/cliaccesstoken/",
                        "permission": _can("cli_admin"),
                    },
                    {
                        "title": "Authorization Codes",
                        "link": "/admin/cli_admin/cliauthorizationcode/",
                        "permission": _can("cli_admin"),
                    },
                    {"title": "Audit Log", "link": "/admin/cli_admin/cliauditlog/", "permission": _can("cli_admin")},
                ],
            },
        ],
    },
}
