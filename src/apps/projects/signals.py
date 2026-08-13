from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Project, Semester

PROJECT_ARCHIVE_VERSION_KEY = "projects:archive-version"


def _clear_project_caches():
    cache.delete("event:current-projects")
    cache.delete("projects:past-all")
    current_version = cache.get(PROJECT_ARCHIVE_VERSION_KEY, 1)
    cache.set(PROJECT_ARCHIVE_VERSION_KEY, current_version + 1, timeout=None)


@receiver([post_save, post_delete], sender=Project)
@receiver([post_save, post_delete], sender=Semester)
# noinspection PyUnusedLocal
def invalidate_project_cache(sender, instance, **kwargs):
    transaction.on_commit(_clear_project_caches)
