"""Seed CMS pages with initial content extracted from hardcoded React pages."""

from django.core.management.base import BaseCommand

from cms.models import CMSBlock, CMSPage

# Phase 1 seed data: 3 simplest pages
SEED_PAGES = [
    {
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
                        {
                            "label": "Email",
                            "value": "i2g@ucmerced.edu",
                            "type": "email",
                        },
                        {
                            "label": "Program",
                            "value": "Innovate to Grow, School of Engineering, University of California, Merced",
                            "type": "text",
                        },
                    ],
                },
            },
        ],
    },
    {
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
                    "body_html": (
                        "<p>The judging form is available in the respective track:</p>"
                        "<ul>"
                        "<li>Via QR code in the Room.</li>"
                        "<li>Via URL in the chat of the Zoom Room.</li>"
                        "<li>The judge form depends on the class (e.g. Engineering versus Software).</li>"
                        "<li>You may preview the judge forms, but make sure to use the correct form "
                        "of your track when judging.</li>"
                        "</ul>"
                    ),
                },
            },
        ],
    },
    {
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
                            "description": ("Searchable database of Innovate to Grow projects since 2012."),
                            "url": "/past-projects",
                            "is_external": False,
                        },
                        {
                            "title": "Current Projects",
                            "description": (
                                "Projects summaries, teams and students that are working on an "
                                "Innovate to Grow project in the current Semester, showcasing "
                                "in the upcoming I2G event."
                            ),
                            "url": "/current-projects",
                            "is_external": False,
                        },
                        {
                            "title": "Project Submission",
                            "description": (
                                "Form to submit your project proposal, which will be evaluated "
                                "for fit in Engineering Capstone, Software Capstone, or Service "
                                "Learning, or an internship, or potentially collaborative research "
                                "with Faculty at UC Merced. It starts with an idea that can be "
                                "interactively refined."
                            ),
                            "url": "/project-submission",
                            "is_external": False,
                        },
                        {
                            "title": "Samples of project proposals",
                            "description": (
                                "Examples of project proposals, as submitted in previous semesters "
                                "by other organizations, for Engineering or Software problems, to "
                                "give you an idea of how to prepare for your project submission."
                            ),
                            "url": "/sample-proposals",
                            "is_external": False,
                        },
                    ],
                },
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Seed CMS pages with initial content from hardcoded React pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--page",
            type=str,
            help="Seed a specific page by slug (e.g. 'contact-us'). Omit to seed all.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing pages (deletes and recreates).",
        )

    def handle(self, *args, **options):
        target_slug = options.get("page")
        force = options.get("force", False)

        pages_to_seed = SEED_PAGES
        if target_slug:
            pages_to_seed = [p for p in SEED_PAGES if p["slug"] == target_slug]
            if not pages_to_seed:
                self.stderr.write(f"No seed data found for slug '{target_slug}'.")
                return

        for page_data in pages_to_seed:
            slug = page_data["slug"]
            existing = CMSPage.objects.filter(slug=slug).first()

            if existing and not force:
                self.stdout.write(f"  Skipping '{slug}' — already exists. Use --force to overwrite.")
                continue

            if existing and force:
                existing.hard_delete()
                self.stdout.write(f"  Deleted existing '{slug}'.")

            page = CMSPage.objects.create(
                slug=page_data["slug"],
                route=page_data["route"],
                title=page_data["title"],
                page_css_class=page_data.get("page_css_class", ""),
                status="published",
            )

            for block_data in page_data.get("blocks", []):
                CMSBlock.objects.create(
                    page=page,
                    block_type=block_data["block_type"],
                    sort_order=block_data["sort_order"],
                    admin_label=block_data.get("admin_label", ""),
                    data=block_data["data"],
                )

            self.stdout.write(self.style.SUCCESS(f"  Created '{slug}' with {len(page_data['blocks'])} block(s)."))

        self.stdout.write(self.style.SUCCESS("Done."))
