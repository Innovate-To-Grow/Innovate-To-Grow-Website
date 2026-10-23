"""Saved versions of the Site Settings custom CSS."""

from apps.cms.models import CustomCssRevision, SiteSettings

KEEP_REVISIONS = 20


def record_custom_css(site_settings, user=None):
    """Keep the custom CSS ``site_settings`` now has, and drop all but the newest revisions."""
    CustomCssRevision.objects.create(
        site_settings=site_settings,
        css=site_settings.custom_css,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    stale = list(CustomCssRevision.objects.values_list("pk", flat=True)[KEEP_REVISIONS:])
    CustomCssRevision.objects.filter(pk__in=stale).delete()


def restore_custom_css(revision, user=None):
    """Make ``revision`` the live custom CSS again (recorded as a new revision)."""
    site_settings = SiteSettings.load()
    site_settings.custom_css = revision.css
    site_settings.save(update_fields=["custom_css"])
    record_custom_css(site_settings, user)
    return site_settings
