"""
Frontend app routes available for the admin menu editor.

Only includes routes backed by dedicated React components (not CMS pages).
CMS pages are loaded dynamically from the database in the menu editor.
"""

APP_ROUTES = [
    {"url": "/news", "title": "News"},
    {"url": "/current-projects", "title": "Current Projects"},
    {"url": "/past-projects", "title": "Past Projects"},
    {"url": "/event", "title": "Event"},
    {"url": "/schedule", "title": "Event Schedule"},
    {"url": "/projects-teams", "title": "Projects & Teams"},
    {"url": "/acknowledgement", "title": "Partners & Sponsors"},
    {"url": "/event-registration", "title": "Event Registration"},
    {"url": "/subscribe", "title": "Subscribe"},
]
