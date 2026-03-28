"""CMS seed data for projects-hub."""

PAGE = {
    "slug": "projects-hub",
    "route": "/projects",
    "title": "Projects",
    "page_css_class": "projects-hub-page",
    "blocks": [
        {
            "block_type": "navigation_grid",
            "sort_order": 0,
            "admin_label": "Project links",
            "data": {
                "heading": "Projects",
                "items": [
                    {
                        "title": "Past Projects",
                        "description": "Searchable database of Innovate to Grow projects since 2012.",
                        "url": "/past-projects",
                        "is_external": False,
                    },
                    {
                        "title": "Current Projects",
                        "description": "Projects summaries, teams and students that are working on an Innovate to Grow project in the current Semester, showcasing in the upcoming I2G event.",
                        "url": "/current-projects",
                        "is_external": False,
                    },
                    {
                        "title": "Project Submission",
                        "description": "Form to submit your project proposal, which will be evaluated for fit in Engineering Capstone, Software Capstone, or Service Learning, or an internship, or potentially collaborative research with Faculty at UC Merced. It starts with an idea that can be interactively refined.",
                        "url": "/project-submission",
                        "is_external": False,
                    },
                    {
                        "title": "Samples of project proposals",
                        "description": "Examples of project proposals, as submitted in previous semesters by other organizations, for Engineering or Software problems, to give you an idea of how to prepare for your project submission.",
                        "url": "/sample-proposals",
                        "is_external": False,
                    },
                ],
            },
        }
    ],
}
