"""CMS seed data for past-events."""

PAGE = {
    "slug": "past-events",
    "route": "/past-events",
    "title": "Past Events",
    "page_css_class": "past-events-page",
    "blocks": [
        {
            "block_type": "rich_text",
            "sort_order": 0,
            "admin_label": "Intro text",
            "data": {
                "heading": "Past Events",
                "heading_level": 1,
                "body_html": '<p class="past-events-page-text">The Innovate to Grow event has been held every semester since Fall 2012, showcasing UC Merced student innovation in engineering and computer science. Browse the archive of past events below to see the teams, projects, and schedules from previous semesters.</p>',
            },
        },
        {
            "block_type": "link_list",
            "sort_order": 1,
            "admin_label": "Event archive links",
            "data": {
                "heading": "Event Archive",
                "style": "list",
                "items": [
                    {"label": "Fall 2025", "url": "/events/2025-fall", "is_external": False},
                    {"label": "Spring 2025", "url": "/events/2025-spring", "is_external": False},
                    {"label": "Fall 2024", "url": "/events/2024-fall", "is_external": False},
                    {"label": "Spring 2024", "url": "/events/2024-spring", "is_external": False},
                    {"label": "Fall 2023", "url": "/events/2023-fall", "is_external": False},
                    {"label": "Spring 2023", "url": "/events/2023-spring", "is_external": False},
                    {"label": "Fall 2022", "url": "/events/2022-fall", "is_external": False},
                    {"label": "Spring 2022", "url": "/events/2022-spring", "is_external": False},
                    {"label": "Fall 2021", "url": "/events/2021-fall", "is_external": False},
                    {"label": "Spring 2021", "url": "/events/2021-spring", "is_external": False},
                    {"label": "Fall 2020", "url": "/events/2020-fall", "is_external": False},
                ],
            },
        },
    ],
}
