"""
Unfold admin theme configuration.

Defines branding (logo, title, colors) and the admin sidebar navigation
structure.  Sidebar items are organized by domain to match the Django app
layout.
"""

from django.templatetags.static import static

UNFOLD = {
    "SITE_TITLE": "I2G Admin",
    "SITE_HEADER": "Innovate To Grow",
    "SITE_ICON": lambda request: static("images/i2glogo.png"),
    "SITE_LOGO": lambda request: static("images/i2glogo.png"),
    "THEME": "light",
    "COLORS": {
        "primary": {
            "50": "oklch(97.7% .014 308.299)",
            "100": "oklch(94.6% .033 307.174)",
            "200": "oklch(90.2% .063 306.703)",
            "300": "oklch(82.7% .119 306.383)",
            "400": "oklch(71.4% .203 305.504)",
            "500": "oklch(62.7% .265 303.9)",
            "600": "oklch(55.8% .288 302.321)",
            "700": "oklch(49.6% .265 301.924)",
            "800": "oklch(43.8% .218 303.724)",
            "900": "oklch(38.1% .176 304.987)",
            "950": "oklch(29.1% .149 302.717)",
        },
    },
    "STYLES": [
        lambda request: static("admin/css/tabs.css"),
        lambda request: static("admin/css/file-input.css"),
    ],
    "TABS": [
        {
            "models": [
                "core.emailserviceconfig",
                "core.gmailimportconfig",
                "core.smsserviceconfig",
                "core.googlecredentialconfig",
                "core.awscredentialconfig",
                "core.systemintelligenceconfig",
            ],
            "items": [
                {"title": "Email Config", "link": "/admin/core/emailserviceconfig/"},
                {"title": "Gmail Import", "link": "/admin/core/gmailimportconfig/"},
                {"title": "SMS Config", "link": "/admin/core/smsserviceconfig/"},
                {"title": "Google Credentials", "link": "/admin/core/googlecredentialconfig/"},
                {"title": "AWS Credentials", "link": "/admin/core/awscredentialconfig/"},
                {"title": "System Intelligence Config", "link": "/admin/core/systemintelligenceconfig/"},
            ],
        },
        {
            "models": ["event.event", "event.eventregistration", "event.checkin"],
            "items": [
                {"title": "Events", "link": "/admin/event/event/"},
                {"title": "Registrations", "link": "/admin/event/eventregistration/"},
                {"title": "Check-ins", "link": "/admin/event/checkin/"},
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
        {
            "models": [
                "cms.sitesettings",
                "cms.cmspage",
                "cms.cmsembedwidget",
                "cms.menu",
                "cms.footercontent",
                "cms.stylesheet",
            ],
            "items": [
                {"title": "Home Page", "link": "/admin/cms/sitesettings/"},
                {"title": "Pages", "link": "/admin/cms/cmspage/"},
                {"title": "Embed Widgets", "link": "/admin/cms/cmsembedwidget/"},
                {"title": "Menus", "link": "/admin/cms/menu/"},
                {"title": "Footer", "link": "/admin/cms/footercontent/"},
                {"title": "Style Sheets", "link": "/admin/cms/stylesheet/"},
            ],
        },
        {
            "models": ["authn.membersheetsyncconfig", "authn.membersheetsynclog"],
            "items": [
                {"title": "Sync Config", "link": "/admin/authn/membersheetsyncconfig/"},
                {"title": "Sync Logs", "link": "/admin/authn/membersheetsynclog/"},
                {"title": "Auto Sync Settings", "link": "/admin/authn/membersheetsyncconfig/sync-settings/"},
            ],
        },
    ],
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": "Site Settings",
                "items": [
                    {"title": "Site Maintenance Control", "link": "/admin/core/sitemaintenancecontrol/"},
                    {"title": "System Intelligence", "link": "/admin/core/system-intelligence/"},
                    {"title": "Service Configs", "link": "/admin/core/emailserviceconfig/"},
                    {"title": "Admin Log", "link": "/admin/admin/logentry/"},
                ],
            },
            {
                "title": "Content Management System",
                "items": [
                    {"title": "Page Analytics", "link": "/admin/cms/pageview/"},
                    {"title": "Page Content", "link": "/admin/cms/cmspage/"},
                    {"title": "News Management", "link": "/admin/cms/newsarticle/"},
                ],
            },
            {
                "title": "Events",
                "items": [
                    {"title": "Events & Registrations", "link": "/admin/event/event/"},
                    {"title": "Current Projects & Schedule", "link": "/admin/event/currentprojectschedule/"},
                    {"title": "Current Projects (synced)", "link": "/admin/event/currentproject/"},
                    {"title": "Sheet Sync Logs", "link": "/admin/event/registrationsheetsynclog/"},
                ],
            },
            {
                "title": "Projects",
                "items": [
                    {"title": "Semesters", "link": "/admin/projects/semester/"},
                    {"title": "Projects", "link": "/admin/projects/project/"},
                ],
            },
            {
                "title": "Amazon SES Email & Gmail",
                "items": [
                    {"title": "Gmail", "link": "/admin/mail/inbox/"},
                    {"title": "Broadcast Email", "link": "/admin/mail/emailcampaign/"},
                    {"title": "Email Log", "link": "/admin/mail/recipientlog/"},
                ],
            },
            {
                "title": "Members & Authentication",
                "items": [
                    {"title": "Members", "link": "/admin/authn/member/"},
                    {"title": "Contact Info", "link": "/admin/authn/contactemail/"},
                    {"title": "Admin Invitations", "link": "/admin/authn/admininvitation/"},
                    {"title": "Member Sheet Sync", "link": "/admin/authn/membersheetsyncconfig/"},
                ],
            },
        ],
    },
}
