"""Unfold admin theme configuration."""

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
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": "Site Settings",
                "items": [{"title": "Site Maintenance Control", "link": "/admin/core/sitemaintenancecontrol/"}],
            },
            {
                "title": "Content Management System",
                "items": [
                    {"title": "Home Page", "link": "/admin/pages/sitesettings/"},
                    {"title": "Pages", "link": "/admin/pages/cmspage/"},
                    {"title": "Page Analytics", "link": "/admin/analytics/pageview/"},
                    {"title": "Menus", "link": "/admin/pages/menu/"},
                    {"title": "Footer", "link": "/admin/pages/footercontent/"},
                ],
            },
            {
                "title": "Data Sync & Integrations",
                "items": [
                    {"title": "Sheets Accounts", "link": "/admin/sheets/sheetsaccount/"},
                    {"title": "Sheet Links", "link": "/admin/sheets/sheetlink/"},
                    {"title": "Sync Logs", "link": "/admin/sheets/synclog/"},
                ],
            },
            {
                "title": "Events",
                "items": [
                    {"title": "Events", "link": "/admin/event/event/"},
                    {"title": "Registrations", "link": "/admin/event/eventregistration/"},
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
                "title": "Members & Authentication",
                "items": [
                    {"title": "Members", "link": "/admin/authn/member/"},
                    {"title": "Contact Emails", "link": "/admin/authn/contactemail/"},
                    {"title": "Groups", "link": "/admin/authn/i2gmembergroup/"},
                    {"title": "Admin Invitations", "link": "/admin/authn/admininvitation/"},
                ],
            },
            {
                "title": "News",
                "items": [
                    {"title": "News Articles", "link": "/admin/news/newsarticle/"},
                    {"title": "Feed Sources", "link": "/admin/news/newsfeedsource/"},
                    {"title": "Sync Logs", "link": "/admin/news/newssynclog/"},
                ],
            },
            {
                "title": "Amazon Simple Email Service",
                "items": [
                    {"title": "SES Mail Senders", "link": "/admin/mail/sesaccount/"},
                    {"title": "SES Compose", "link": "/admin/mail/sesaccount/compose/"},
                    {"title": "SES Email Logs", "link": "/admin/mail/sesemaillog/"},
                ],
            },
            {
                "title": "Gmail",
                "items": [
                    {"title": "Gmail API Accounts", "link": "/admin/mail/googleaccount/"},
                    {"title": "Inbox", "link": "/admin/mail/googleaccount/inbox/"},
                    {"title": "Sent Mail", "link": "/admin/mail/googleaccount/sent/"},
                    {"title": "Compose", "link": "/admin/mail/googleaccount/compose/"},
                    {"title": "Email Logs", "link": "/admin/mail/emaillog/"},
                ],
            },
        ],
    },
}
