"""
Permanent (301) redirects from legacy Flask routes to their new Django equivalents.

Each entry maps the old Flask path (no leading slash, exactly as defined in
project/views/home.py) to the new /pages/legacy/<slug>/ URL.

Included at the root level in core/urls.py so these paths are reachable
directly (e.g. /about → /pages/legacy/about/).
"""

from django.urls import path, re_path
from django.views.generic import RedirectView

# ---------------------------------------------------------------------------
# Old Flask path  →  new URL
# Paths are matched exactly as the Flask routes were defined (case-sensitive).
# ---------------------------------------------------------------------------
_REDIRECTS = [
    # About
    ("about",                               "/pages/legacy/about/"),
    ("about_EngSL",                         "/pages/legacy/about-engsl/"),
    ("engineering-capstone",                "/pages/legacy/engineering-capstone/"),
    ("software-capstone",                   "/pages/legacy/software-capstone/"),
    # Privacy / legal
    ("privacy",                             "/pages/legacy/privacy/"),
    ("ferpa",                               "/pages/legacy/ferpa/"),
    ("I2G-student-agreement",               "/pages/legacy/i2g-student-agreement/"),
    ("I2G-project-sponsor-acknowledgement", "/pages/legacy/i2g-project-sponsor-acknowledgement/"),
    # Events
    ("event",                               "/pages/legacy/event/"),
    ("schedule",                            "/pages/legacy/schedule/"),
    ("projects-teams",                      "/pages/legacy/projects-teams/"),
    ("judges",                              "/pages/legacy/judges/"),
    ("attendees",                           "/pages/legacy/attendees/"),
    ("acknowledgement",                     "/pages/legacy/acknowledgement/"),
    ("past-events",                         "/pages/legacy/past-events/"),
    ("judging",                             "/pages/legacy/judging/"),
    # Event archive pages
    ("home-during-event",                   "/pages/legacy/home-during-event/"),
    ("home-post-event",                     "/pages/legacy/home-post-event/"),
    ("2025-fall-event",                     "/pages/legacy/2025-fall-event/"),
    ("2025-spring-event",                   "/pages/legacy/2025-spring-event/"),
    ("2024-fall-event",                     "/pages/legacy/2024-fall-event/"),
    ("2024-spring-event",                   "/pages/legacy/2024-spring-event/"),
    ("2023-fall-event",                     "/pages/legacy/2023-fall-event/"),
    ("2023-spring-event",                   "/pages/legacy/2023-spring-event/"),
    ("2022-fall-event",                     "/pages/legacy/2022-fall-event/"),
    ("2022-spring-event",                   "/pages/legacy/2022-spring-event/"),
    ("2021-fall-event",                     "/pages/legacy/2021-fall-event/"),
    ("2021-spring-event",                   "/pages/legacy/2021-spring-event/"),
    ("2020-fall-post-event",                "/pages/legacy/2020-fall-post-event/"),
    ("2014-sponsors",                       "/pages/legacy/2014-sponsors/"),
    ("2015-sponsors",                       "/pages/legacy/2015-sponsors/"),
    # Projects
    ("projects",                            "/pages/legacy/projects/"),
    ("current-projects",                    "/pages/legacy/current-projects/"),
    ("project-submission",                  "/pages/legacy/project-submission/"),
    ("sample-proposals",                    "/pages/legacy/sample-proposals/"),
    ("past-projects",                       "/pages/legacy/past-projects/"),
    # Partnership / sponsorship
    ("partnership",                         "/pages/legacy/partnership/"),
    ("sponsorship",                         "/pages/legacy/sponsorship/"),
    ("FAQs",                                "/pages/legacy/faqs/"),
    ("contact-us",                          "/pages/legacy/contact-us/"),
    # Students
    ("students",                            "/pages/legacy/students/"),
    ("i2g-students-preparation",            "/pages/legacy/i2g-students-preparation/"),
    ("video-preparation",                   "/pages/legacy/video-preparation/"),
    ("capstone-purchasing-reimbursement",   "/pages/legacy/capstone-purchasing-reimbursement/"),
    # Misc
    ("template",                            "/pages/legacy/template/"),
    ("template-email-team-students",        "/pages/legacy/template-email-team-students/"),
]

urlpatterns = [
    path(old_path, RedirectView.as_view(url=new_url, permanent=True))
    for old_path, new_url in _REDIRECTS
]

# past-projects/<uuid> — drop the UUID for now; proper Sheets sync comes later
urlpatterns += [
    re_path(
        r"^past-projects/(?P<uuid_string>[^/]+)$",
        RedirectView.as_view(url="/pages/legacy/past-projects/", permanent=True),
    ),
]
