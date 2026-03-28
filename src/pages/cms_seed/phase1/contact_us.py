"""CMS seed data for contact-us."""

PAGE = {
    "slug": "contact-us",
    "route": "/contact-us",
    "title": "Contact Us",
    "page_css_class": "contact-page",
    "blocks": [
        {
            "block_type": "contact_info",
            "sort_order": 0,
            "admin_label": "Contact details",
            "data": {
                "heading": "Contact Us",
                "items": [
                    {"label": "Email", "value": "i2g@ucmerced.edu", "type": "email"},
                    {
                        "label": "Program",
                        "value": "Innovate to Grow, School of Engineering, University of California, Merced",
                        "type": "text",
                    },
                ],
            },
        }
    ],
}
