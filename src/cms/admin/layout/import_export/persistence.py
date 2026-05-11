"""Stylesheet import persistence helpers."""

from django.core.cache import cache
from django.db import transaction

from cms.models import StyleSheet
from cms.views.views import LAYOUT_CACHE_KEY, LAYOUT_STYLESHEET_CACHE_KEY


def sync_stylesheets(normalized_rows):
    import_names = [row["name"] for row in normalized_rows]

    with transaction.atomic():
        existing_by_name = {sheet.name: sheet for sheet in StyleSheet.objects.filter(name__in=import_names)}
        for row in normalized_rows:
            stylesheet = existing_by_name.get(row["name"])
            if stylesheet is None:
                StyleSheet.objects.create(**row)
                continue

            for field, value in row.items():
                setattr(stylesheet, field, value)
            stylesheet.save()

        StyleSheet.objects.exclude(name__in=import_names).delete()
        transaction.on_commit(clear_layout_caches)


def clear_layout_caches():
    cache.delete(LAYOUT_CACHE_KEY)
    cache.delete(LAYOUT_STYLESHEET_CACHE_KEY)
