"""
Frontend app routes available for the admin menu editor.

Only includes routes backed by dedicated React components (not CMS pages).
CMS pages are loaded dynamically from the database in the menu editor.

`embeddable=False` marks routes that exist in the React router but cannot be
rendered standalone inside `/_embed/:embedSlug` — they have no entry in the
frontend `EMBED_APP_ROUTE_COMPONENTS` registry. Embed-widget admin and
validation use `EMBEDDABLE_APP_ROUTES`; the menu editor and login redirects
use the full `APP_ROUTES`.
"""

APP_ROUTES = [
    {"url": "/news", "title": "News", "embeddable": True},
    {"url": "/current-projects", "title": "Current Projects", "embeddable": True},
    {"url": "/presenting-teams", "title": "Presenting Teams", "embeddable": True},
    {"url": "/past-projects", "title": "Past Projects", "embeddable": True},
    {"url": "/event", "title": "Event", "embeddable": False},
    {"url": "/schedule", "title": "Event Schedule", "embeddable": True},
    {"url": "/acknowledgement", "title": "Partners & Sponsors", "embeddable": True},
    {"url": "/event-registration", "title": "Event Registration", "embeddable": True},
    {"url": "/subscribe", "title": "Subscribe", "embeddable": True},
]

EMBEDDABLE_APP_ROUTES = [r for r in APP_ROUTES if r.get("embeddable")]


# Browser routes owned by dedicated React components.  This registry is kept
# separate from ``APP_ROUTES`` because that list is intentionally limited to
# routes that are useful in menu/login pickers and still contains ``/event``,
# which is CMS-backed in the current React router.
PUBLIC_APP_ROUTES = [
    {"url": "/membership/events", "title": "Membership Events"},
    {"url": "/news", "title": "News"},
    {"url": "/current-projects", "title": "Current Projects"},
    {"url": "/presenting-teams", "title": "Presenting Teams"},
    {"url": "/past-projects", "title": "Past Projects"},
    {"url": "/event-registration", "title": "Event Registration"},
    {"url": "/schedule", "title": "Event Schedule"},
    {"url": "/acknowledgement", "title": "Partners & Sponsors"},
    {"url": "/subscribe", "title": "Subscribe"},
    {"url": "/login-link", "title": "Login Link"},
    {"url": "/magic-login", "title": "Legacy Magic Login"},
    {"url": "/ticket-login", "title": "Legacy Ticket Login"},
    {"url": "/unsubscribe-login", "title": "Unsubscribe Login"},
    {"url": "/email-auth-link", "title": "Email Authentication Link"},
    {"url": "/impersonate-login", "title": "Impersonation Login"},
    {"url": "/profile", "title": "Profile Redirect"},
    {"url": "/login", "title": "Login"},
    {"url": "/register", "title": "Register"},
    {"url": "/forgot-password", "title": "Forgot Password"},
    {"url": "/verify-email", "title": "Verify Email"},
    {"url": "/verify-phone", "title": "Verify Phone"},
    {"url": "/complete-profile", "title": "Complete Profile"},
    {"url": "/account", "title": "Account"},
]

# React-router dynamic patterns.  ``:name`` represents one non-empty path
# segment.  Concrete paths matching these patterns are application-owned and
# cannot be claimed as CMS pages or redirect sources.
PUBLIC_APP_ROUTE_PATTERNS = [
    "/news/:id",
    "/past-projects/project/:id",
    "/projects/:id",
    "/events/:eventSlug",
    "/_embed/:embedSlug",
]

# React-only utility routes that must never be claimed as CMS pages or legacy
# redirect sources, but are not valid public redirect destinations.
PROTECTED_APP_ROUTES = ["/_block-preview"]
