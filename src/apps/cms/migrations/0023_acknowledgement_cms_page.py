"""Make /acknowledgement an ordinary CMS page.

The page used to be a React component with its copy written into the code; only the sponsor
list was meant to come from a CMS page at the same route, and that page could not be created
because the route was registered as application-owned. The route is now CMS-owned, and this
migration creates the page with the copy the component showed, so admins edit all of it (and
add "Sponsor Year" blocks) in the CMS.

A page that already uses the route or slug is left alone. The reverse removes the page only
while it still holds exactly the blocks added here.
"""

from django.db import migrations
from django.utils import timezone

ROUTE = "/acknowledgement"
SLUG = "acknowledgement"
TITLE = "Partners & Sponsors"

BLOCKS = [
    {
        "block_type": "rich_text",
        "sort_order": 0,
        "admin_label": "Introduction",
        "data": {
            "heading": "Partners & Sponsors",
            "heading_level": 1,
            "body_html": (
                "<p>The Innovate to Grow program thrives thanks to the generous support of our partners and "
                "sponsors. Their commitment to engineering education and student innovation makes this program "
                "possible.</p>\n"
                "<p>We extend our sincere gratitude to all organizations and individuals who contribute to "
                "Innovate to Grow through project sponsorship, financial support, mentorship, and judging. Your "
                "involvement directly impacts the educational experience of UC Merced students and helps prepare "
                "the next generation of engineers and innovators.</p>"
            ),
        },
    },
    # Sponsor Year blocks go between the introduction and "Become a Sponsor" (sort order 1-9).
    {
        "block_type": "rich_text",
        "sort_order": 10,
        "admin_label": "Become a Sponsor",
        "data": {
            "heading": "Become a Sponsor",
            "heading_level": 2,
            "body_html": (
                "<p>Interested in supporting the Innovate to Grow program? Learn more about sponsorship "
                "opportunities and how your organization can get involved.</p>"
            ),
        },
    },
    {
        "block_type": "cta_group",
        "sort_order": 11,
        "admin_label": "Sponsorship link",
        "data": {"items": [{"label": "View Sponsorship Information", "href": "/sponsorship", "style": "primary"}]},
    },
    {
        "block_type": "rich_text",
        "sort_order": 12,
        "admin_label": "Sponsorship contact",
        "data": {
            "body_html": (
                "<p>For questions about sponsorship, please contact us at "
                '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.</p>'
            ),
        },
    },
]


def create_page(apps, schema_editor):
    CMSPage = apps.get_model("cms", "CMSPage")
    CMSBlock = apps.get_model("cms", "CMSBlock")

    if CMSPage.objects.filter(route__iexact=ROUTE).exists() or CMSPage.objects.filter(slug=SLUG).exists():
        return
    page = CMSPage.objects.create(
        slug=SLUG,
        route=ROUTE,
        title=TITLE,
        status="published",
        published_at=timezone.now(),
    )
    CMSBlock.objects.bulk_create(CMSBlock(page=page, **block) for block in BLOCKS)


def remove_page(apps, schema_editor):
    CMSPage = apps.get_model("cms", "CMSPage")

    page = CMSPage.objects.filter(slug=SLUG, route=ROUTE).first()
    if page is None:
        return
    blocks = [
        {"block_type": b.block_type, "sort_order": b.sort_order, "admin_label": b.admin_label, "data": b.data}
        for b in page.blocks.order_by("sort_order")
    ]
    if blocks == BLOCKS:
        page.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0022_audit_fixes_styles"),
    ]

    operations = [
        migrations.RunPython(create_page, remove_page),
    ]
