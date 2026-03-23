"""Seed CMS pages with initial content extracted from hardcoded React pages."""

from django.core.management.base import BaseCommand

from pages.models import CMSBlock, CMSPage

# Phase 1 seed data
SEED_PAGES = [
    {
        "slug": "home",
        "route": "/",
        "title": "Home",
        "page_css_class": "home-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Homepage content",
                "data": {
                    "heading": "Innovate to Grow",
                    "heading_level": 1,
                    "body_html": (
                        '<div class="home-hero">'
                        '<p class="home-hero-subtitle">'
                        "UC Merced School of Engineering's Experiential Learning Program"
                        "</p>"
                        "</div>"
                        '<div class="home-quick-links">'
                        '<a href="/project-submission" class="home-btn home-btn-gold">Submit a Project</a>'
                        '<a href="/about" class="home-btn home-btn-blue">Learn More</a>'
                        '<a href="/news" class="home-btn home-btn-gold">News</a>'
                        "</div>"
                        '<div class="home-about">'
                        '<h2 class="home-section-title">Engineering Solutions for Innovative Organizations</h2>'
                        '<p class="home-text">'
                        "Innovate to Grow (I2G) is a unique &quot;experiential learning&quot; program that engages external "
                        "partner organizations with teams of students who design systems to solve complex, real-world "
                        "problems. At the end of each semester, the work completed by the student teams culminates in the "
                        "Innovate to Grow event."
                        "</p>"
                        '<div class="home-cta-row">'
                        '<a href="/partnership" class="home-link">Partnership Opportunities</a>'
                        '<a href="/sponsorship" class="home-link">Sponsorship</a>'
                        '<a href="/faqs" class="home-link">FAQs</a>'
                        "</div>"
                        "</div>"
                        '<div class="home-event-info">'
                        '<h2 class="home-section-title">Event</h2>'
                        '<div class="home-event-links">'
                        '<a href="/event">Event Details</a>'
                        '<a href="/schedule">Full Schedule</a>'
                        '<a href="/projects-teams">All Projects &amp; Teams</a>'
                        '<a href="/judges">Judge Info</a>'
                        '<a href="/attendees">Attendee Info</a>'
                        "</div>"
                        "</div>"
                    ),
                },
            },
        ],
    },
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
                            "description": "Searchable database of Innovate to Grow projects since 2012.",
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

    # noinspection PyMethodMayBeStatic
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

    # noinspection PyUnusedLocal,DuplicatedCode
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
