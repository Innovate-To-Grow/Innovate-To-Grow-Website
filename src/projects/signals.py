from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Project, Semester


def _clear_project_caches():
    cache.delete("projects:current")
    cache.delete("projects:past-all")


@receiver([post_save, post_delete], sender=Project)
@receiver([post_save, post_delete], sender=Semester)
# noinspection PyUnusedLocal
def invalidate_project_cache(sender, instance, **kwargs):
    transaction.on_commit(_clear_project_caches)
