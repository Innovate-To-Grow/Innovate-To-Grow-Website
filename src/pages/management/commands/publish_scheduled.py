"""
Management command to publish pages that have reached their scheduled publish time.

Run periodically via cron or celery beat (recommended: every minute).
Usage: python manage.py publish_scheduled
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from pages.models import HomePage, Page

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Publish pages and homepages that have reached their scheduled publish time."

    def handle(self, *args, **options):
        now = timezone.now()
        total_published = 0

        # Process Pages
        scheduled_pages = Page.objects.filter(status="scheduled", scheduled_publish_at__lte=now)
        for page in scheduled_pages:
            try:
                page.publish()
                total_published += 1
                logger.info("Published scheduled page: %s (slug=%s)", page.title, page.slug)
                self.stdout.write(self.style.SUCCESS(f'Published page: "{page.title}"'))
            except Exception as e:
                logger.error("Failed to publish scheduled page %s: %s", page.pk, e)
                self.stderr.write(self.style.ERROR(f'Failed to publish page "{page.title}": {e}'))

        # Process HomePages
        scheduled_homepages = HomePage.objects.filter(status="scheduled", scheduled_publish_at__lte=now)
        for homepage in scheduled_homepages:
            try:
                homepage.publish()
                total_published += 1
                logger.info("Published scheduled homepage: %s", homepage.name)
                self.stdout.write(self.style.SUCCESS(f'Published homepage: "{homepage.name}"'))
            except Exception as e:
                logger.error("Failed to publish scheduled homepage %s: %s", homepage.pk, e)
                self.stderr.write(self.style.ERROR(f'Failed to publish homepage "{homepage.name}": {e}'))

        if total_published == 0:
            self.stdout.write("No scheduled pages ready for publishing.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Published {total_published} item(s)."))
