from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from apps.cms.admin.cms.page_admin.import_export import export_pages_response
from apps.cms.services.pages import duplicate_page


class CMSPageActionsMixin:
    """CMSPageAdmin's bulk actions: duplicate as drafts, export as JSON."""

    @admin.action(description="Duplicate selected pages as drafts", permissions=["add"])
    def duplicate_pages(self, request, queryset):
        pages = list(queryset.prefetch_related("blocks"))
        copies = []
        for page in pages:
            try:
                copies.append(duplicate_page(page))
            except ValidationError as exc:
                messages.error(request, f'Could not duplicate "{page.title}": {" ".join(exc.messages)}')
        if not copies:
            return None

        links = format_html_join(
            ", ",
            '<a href="{}">{}</a>',
            ((reverse("admin:cms_cmspage_change", args=[copy.pk]), f"{copy.title} ({copy.route})") for copy in copies),
        )
        if len(pages) == 1:
            # A single page was duplicated: land on the copy so it can be renamed straight away.
            messages.success(request, format_html("Created draft copy {}.", links))
            return HttpResponseRedirect(reverse("admin:cms_cmspage_change", args=[copies[0].pk]))
        noun = "copy" if len(copies) == 1 else "copies"
        messages.success(request, format_html("Created {} draft {}: {}.", len(copies), noun, links))
        return None

    @admin.action(description="Export selected pages as JSON")
    def export_pages(self, request, queryset):
        return export_pages_response(queryset)
