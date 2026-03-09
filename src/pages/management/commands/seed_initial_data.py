"""
Seed initial data for the I2G website.

Creates:
- Main navigation menu with app routes and external links
- Loads footer fixture if no active footer exists

Idempotent: safe to run multiple times.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from pages.models import FooterContent, Menu

# Menu items matching the site navigation structure
MAIN_NAV_ITEMS = [
    {
        "type": "app",
        "title": "Home",
        "url": "/",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "app",
        "title": "About",
        "url": "/about",
        "icon": "",
        "open_in_new_tab": False,
        "children": [
            {
                "type": "app",
                "title": "Engineering Capstone",
                "url": "/engineering-capstone",
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
                "type": "app",
                "title": "Software Eng. Capstone",
                "url": "/software-capstone",
                "icon": "",
                "open_in_new_tab": False,
                "children": [],
            },
        ],
    },
    {
        "type": "app",
        "title": "Event",
        "url": "/event",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "app",
        "title": "Projects",
        "url": "/projects",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "app",
        "title": "Partnership",
        "url": "/partnership",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "app",
        "title": "Students",
        "url": "/students",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
    {
        "type": "app",
        "title": "Contact Us",
        "url": "/contact-us",
        "icon": "",
        "open_in_new_tab": False,
        "children": [],
    },
]


class Command(BaseCommand):
    help = "Seed initial menu and footer data for the I2G website."

    def handle(self, *args, **options):
        self._seed_menu()
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
