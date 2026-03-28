"""CMS seed data for judging."""

PAGE = {
    "slug": "judging",
    "route": "/judging",
    "title": "Judging Forms",
    "page_css_class": "judging-page",
    "blocks": [
        {
            "block_type": "rich_text",
            "sort_order": 0,
            "admin_label": "Judging info",
            "data": {
                "heading": "Judging Forms",
                "heading_level": 1,
                "body_html": "<p>The judging form is available in the respective track:</p><ul><li>Via QR code in the Room.</li><li>Via URL in the chat of the Zoom Room.</li><li>The judge form depends on the class (e.g. Engineering versus Software).</li><li>You may preview the judge forms, but make sure to use the correct form of your track when judging.</li></ul>",
            },
        }
    ],
}
