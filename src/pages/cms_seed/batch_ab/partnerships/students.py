"""CMS seed data for students."""

PAGE = {
    "slug": "students",
    "route": "/students",
    "title": "Students & Teams",
    "page_css_class": "student-page",
    "blocks": [
        {
            "block_type": "rich_text",
            "sort_order": 0,
            "admin_label": "Students intro",
            "data": {
                "heading": "Students & Teams - Resources for I2G Projects and Events",
                "heading_level": 1,
                "body_html": '<p class="student-text">This section contains information and guidelines for students and teams participating in:</p><ul class="student-list"><li>An I2G project, such as Eng. Capstone and Software Engineering</li><li>The I2G event and showcase</li></ul>',
            },
        },
        {
            "block_type": "navigation_grid",
            "sort_order": 1,
            "admin_label": "Student resource links",
            "data": {
                "items": [
                    {
                        "title": "I2G Project - Student Agreement",
                        "description": "The template of the agreement that a student must sign to participate in any project provided and sponsored by partner organizations. The agreement is digitally signed by acceptance in the survey to view and participate in projects at the beginning of the semester.",
                        "url": "/student-agreement",
                        "is_external": False,
                    },
                    {
                        "title": "FERPA Agreement",
                        "description": "The template of the agreement that a student must sign to participate in the Innovate to Grow event, allowing to record and distribute presentations and videos (media waiver).",
                        "url": "/ferpa",
                        "is_external": False,
                    },
                    {
                        "title": "Video Presentations",
                        "description": "Guidelines and instructions to prepare video presentations. Contains several general guidelines useful for any professional video presentation, particularly in engineering, with some details specific to Capstone and I2G.",
                        "url": "/video-preparation",
                        "is_external": False,
                    },
                    {
                        "title": "I2G Event Preparation",
                        "description": "Information on I2G and instructions for students and teams to plan for it pre- during- and post-event.",
                        "url": "/event-preparation",
                        "is_external": False,
                    },
                    {
                        "title": "Purchasing / Travel / Expense Reimbursements",
                        "description": "Guidelines and forms for purchasing and travel reimbursement.",
                        "url": "/purchasing-reimbursement",
                        "is_external": False,
                    },
                    {
                        "title": "Student Experience Survey",
                        "description": "Fill this survey for feedback and comments on the Capstone - I2G project, and event experience.",
                        "url": "https://ucmerced.az1.qualtrics.com/jfe/form/SV_e4L1PyHidYuThEW",
                        "is_external": True,
                    },
                ]
            },
        },
    ],
}
