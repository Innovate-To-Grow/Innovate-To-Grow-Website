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
