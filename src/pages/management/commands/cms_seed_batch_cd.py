"""Seed CMS pages for Batch C and Batch D."""

from django.core.management.base import BaseCommand

from pages.cms_seed.batch_cd import SEED_PAGES
from pages.cms_seed.common import add_seed_arguments, handle_seed_pages


class Command(BaseCommand):
    help = "Seed CMS pages for Batch C (judges, attendees, submission, proposals, event/video prep) and Batch D (legal, archive)."

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
