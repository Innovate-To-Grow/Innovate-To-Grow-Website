"""Seed phase-1 CMS pages."""

from django.core.management.base import BaseCommand

from pages.cms_seed.common import add_seed_arguments, handle_seed_pages
from pages.cms_seed.phase1 import SEED_PAGES


class Command(BaseCommand):
    help = "Seed CMS pages with initial content from hardcoded React pages."

    # noinspection PyMethodMayBeStatic
    def add_arguments(self, parser):
        add_seed_arguments(self, parser)

    # noinspection PyUnusedLocal
    def handle(self, *args, **options):
        handle_seed_pages(
            self,
            SEED_PAGES,
            target_slug=options.get("page"),
            force=options.get("force", False),
        )
