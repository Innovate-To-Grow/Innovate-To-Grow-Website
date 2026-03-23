from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import NewsArticle


@receiver(post_save, sender=NewsArticle)
@receiver(post_delete, sender=NewsArticle)
# noinspection PyUnusedLocal
def invalidate_news_cache(sender, instance, **kwargs):
    cache.delete("news:list")
