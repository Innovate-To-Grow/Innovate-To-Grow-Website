"""
Seed initial data for the I2G website.

Creates:
- Main navigation menu with legacy page links
- Active home page from the legacy/home page content
- Publishes pages referenced by the menu
- Loads footer fixture if no active footer exists

Idempotent: safe to run multiple times.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from pages.models import FooterContent, HomePage, Menu, Page

# Menu items matching the old Flask site navigation structure
MAIN_NAV_ITEMS = [
    {
        "type": "home",
        "title": "Home",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "page",
        "title": "About",
        "page_slug": "legacy/about",
        "icon": "",
        "open_in_new_tab": False,
        "children": [
            {
                "type": "page",
                "title": "Engineering Capstone",
                "page_slug": "legacy/engineering-capstone",
                "icon": "",
                "open_in_new_tab": False,
                "children": [],
            },
            {
                "type": "external",
                "title": "Eng. Service Learning",
                "url": "https://engineeringservicelearning.ucmerced.edu/",
                "icon": "",
                "open_in_new_tab": True,
                "children": [],
            },
            {
                "type": "page",
                "title": "Software Eng. Capstone",
                "page_slug": "legacy/software-capstone",
                "icon": "",
                "open_in_new_tab": False,
                "children": [],
            },
        ],
    },
    {
        "type": "page",
        "title": "Event",
        "page_slug": "legacy/event",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "page",
        "title": "Projects",
        "page_slug": "legacy/projects",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "page",
        "title": "Partnership",
        "page_slug": "legacy/partnership",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "page",
        "title": "Students",
        "page_slug": "legacy/students",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "page",
        "title": "Contact Us",
        "page_slug": "legacy/contact-us",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
]

# Slugs of pages that must be published for menu links to resolve
MENU_PAGE_SLUGS = [
    "legacy/about",
    "legacy/engineering-capstone",
    "legacy/software-capstone",
    "legacy/event",
    "legacy/projects",
    "legacy/partnership",
    "legacy/students",
    "legacy/contact-us",
]


class Command(BaseCommand):
    help = "Seed initial menu, home page, and footer data for the I2G website."

    def handle(self, *args, **options):
        self._seed_menu()
        self._publish_menu_pages()
        self._seed_homepage()
        self._seed_footer()
        self.stdout.write(self.style.SUCCESS("\nDone."))

    def _seed_menu(self):
        """Create the main navigation menu if it doesn't exist."""
        menu, created = Menu.objects.get_or_create(
            name="main-nav",
            defaults={
                "display_name": "Main Navigation",
                "description": "Primary site navigation",
                "items": MAIN_NAV_ITEMS,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created menu: main-nav"))
        else:
            self.stdout.write("Menu 'main-nav' already exists, skipping.")

    def _publish_menu_pages(self):
        """Publish legacy pages referenced by the menu so titles/URLs resolve."""
        published_count = 0
        for slug in MENU_PAGE_SLUGS:
            try:
                page = Page.objects.get(slug=slug)
                if page.status != "published":
                    page.status = "published"
                    page.save()
                    published_count += 1
                    self.stdout.write(f"  Published: {slug}")
                else:
                    self.stdout.write(f"  Already published: {slug}")
            except Page.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  Page not found: {slug}"))
        self.stdout.write(self.style.SUCCESS(f"Published {published_count} page(s) for menu."))

    def _seed_homepage(self):
        """Create an active home page with default content."""
        home_page = HomePage.objects.filter(name="Legacy Home").first()
        if home_page:
            if home_page.html:
                self.stdout.write("HomePage 'Legacy Home' already exists with content, skipping.")
                return
            self.stdout.write("HomePage 'Legacy Home' exists but has no content, updating...")
            home_page.html = "<h1>Welcome to Innovate To Grow</h1>"
            home_page.css = ""
            home_page.save(update_fields=["html", "css", "updated_at"])
        else:
            # Create the HomePage — must set status=published BEFORE is_active=True
            home_page = HomePage(
                name="Legacy Home",
                status="published",
                is_active=True,
                html="<h1>Welcome to Innovate To Grow</h1>",
                css="",
            )
            home_page.save()
            self.stdout.write("Created HomePage 'Legacy Home' (active, published).")

        self.stdout.write(self.style.SUCCESS("HomePage 'Legacy Home' ready."))

    def _seed_footer(self):
        """Load footer fixture if no active footer exists."""
        if FooterContent.objects.filter(is_active=True).exists():
            self.stdout.write("Active footer already exists, skipping.")
            return

        try:
            call_command("loaddata", "pages/fixtures/footer_content.json", verbosity=0)
            self.stdout.write(self.style.SUCCESS("Loaded footer fixture."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Failed to load footer fixture: {e}"))
