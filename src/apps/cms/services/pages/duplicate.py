"""Duplicate a CMS page, blocks included, as a new draft."""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.cms.models import CMSBlock, CMSPage
from apps.cms.services.routing.route_redirects import page_route_conflicts

# Conflicts that a different ``-copy-N`` suffix can resolve. Anything else
# (invalid segment, reserved prefix, application route) would recur for every
# candidate, so give up immediately with the underlying message.
_RETRYABLE_CONFLICT_CODES = frozenset({"cms_page", "redirect_source"})
_MAX_COPY_ATTEMPTS = 1000


def duplicate_page(page: CMSPage) -> CMSPage:
    """Create a draft copy of ``page`` together with all of its content blocks.

    The copy gets a unique ``<slug>-copy[-N]`` slug and a matching route, so it
    never collides with an existing page, redirect, or application route.  It is
    always saved as a draft, regardless of the source status, so a duplicate can
    never go live at a brand-new URL by accident.

    Raises ``ValidationError`` when no valid copy route can be derived.
    """

    with transaction.atomic():
        slug, route, title = _free_copy_identity(page)
        copy = CMSPage(
            slug=slug,
            route=route,
            title=title,
            meta_description=page.meta_description,
            page_css_class=page.page_css_class,
            page_css=page.page_css,
            sort_order=page.sort_order,
            status="draft",
        )
        copy.full_clean()
        copy.save()
        for block in page.blocks.all():
            CMSBlock.objects.create(
                page=copy,
                block_type=block.block_type,
                sort_order=block.sort_order,
                admin_label=block.admin_label,
                data=block.data,
            )
    return copy


def _free_copy_identity(page: CMSPage) -> tuple[str, str, str]:
    """Return the first unused ``(slug, route, title)`` for a copy of ``page``."""

    slug_max = CMSPage._meta.get_field("slug").max_length
    route_max = CMSPage._meta.get_field("route").max_length
    title_max = CMSPage._meta.get_field("title").max_length
    # The site root has no last segment to suffix; fall back to the page's slug.
    base_route = page.route if page.route != "/" else f"/{page.slug}"

    for attempt in range(1, _MAX_COPY_ATTEMPTS + 1):
        suffix = "-copy" if attempt == 1 else f"-copy-{attempt}"
        slug = _append_within(page.slug, suffix, slug_max)
        if CMSPage.objects.filter(slug=slug).exists():
            continue

        route, conflicts = page_route_conflicts(_append_within(base_route, suffix, route_max))
        if any(conflict.code not in _RETRYABLE_CONFLICT_CODES for conflict in conflicts):
            raise ValidationError({"route": [conflict.message for conflict in conflicts]})
        if conflicts:
            continue

        label = " (Copy)" if attempt == 1 else f" (Copy {attempt})"
        return slug, route, _append_within(page.title, label, title_max)

    raise ValidationError({"slug": [f'Could not find an unused copy slug for "{page.slug}".']})


def _append_within(base: str, suffix: str, max_length: int) -> str:
    """Append ``suffix`` to ``base``, trimming ``base`` so the result fits ``max_length``."""

    return f"{base[: max_length - len(suffix)]}{suffix}"
