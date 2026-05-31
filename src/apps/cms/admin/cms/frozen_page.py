"""Admin for FrozenPage, including an 'Import from URL' capture flow."""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.text import slugify

from apps.cms.models import FrozenPage
from apps.cms.models.content.cms.frozen_page import STATUS_CHOICES, STATUS_DRAFT
from apps.cms.services.freeze import BlockedURLError, FreezeError
from apps.cms.views.frozen import clear_frozen_page_cache
from apps.core.admin import BaseModelAdmin

_PRESET_FORM_FIELDS = (
    "remove_header",
    "remove_nav",
    "remove_footer",
    "remove_cookie_consent",
    "remove_ads",
)

# Editing any of these on the change form re-captures the page on save (the
# frozen output depends on them), so saved edits actually take effect.
_CAPTURE_FIELDS = ("source_url", *_PRESET_FORM_FIELDS, "extra_remove_selectors")


class FrozenPageImportForm(forms.Form):
    """Capture form for the 'Import from URL' admin view."""

    source_url = forms.URLField(label="Page URL", max_length=2000, assume_scheme="https")
    title = forms.CharField(label="Title", max_length=300, required=False, help_text="Defaults to the page's <title>.")
    slug = forms.SlugField(label="Slug", max_length=200, required=False, help_text="Auto-generated if left blank.")
    status = forms.ChoiceField(choices=STATUS_CHOICES, initial=STATUS_DRAFT)

    remove_header = forms.BooleanField(label="Remove header / banner", required=False)
    remove_nav = forms.BooleanField(label="Remove navigation", required=False)
    remove_footer = forms.BooleanField(label="Remove footer", required=False)
    remove_cookie_consent = forms.BooleanField(label="Remove cookie / consent banners", required=False)
    remove_ads = forms.BooleanField(label="Remove ads", required=False)
    extra_remove_selectors = forms.CharField(
        label="Extra selectors to remove",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": ".newsletter-popup\n#chat-widget"}),
        help_text="One CSS selector per line.",
    )


def _unique_slug(base: str) -> str:
    """Return a unique kebab-case slug derived from ``base``."""
    candidate = slugify(base)[:180] or "frozen-page"
    slug = candidate
    suffix = 2
    while FrozenPage.objects.filter(slug=slug).exists():
        slug = f"{candidate}-{suffix}"
        suffix += 1
    return slug


@admin.register(FrozenPage)
class FrozenPageAdmin(BaseModelAdmin):
    list_display = ("title", "slug", "status", "size_display", "fetched_at", "preview_link")
    list_filter = ("status",)
    search_fields = ("title", "slug", "source_url")
    actions = ["refreeze_selected"]
    change_list_template = "admin/cms/frozenpage/change_list.html"
    # This is a content model with its own capture-on-save semantics; the
    # type-to-confirm gate just makes Save look broken (mirrors CMSPageAdmin).
    require_confirmation = False
    save_on_top = True
    # frozen_html is the captured blob (can be multi-MB) — never edited by hand,
    # so it is omitted from the fieldsets below rather than shown as a textarea.
    readonly_fields = ("size_display", "fetched_at", "preview_link")
    fieldsets = (
        (None, {"fields": ("source_url", "title", "slug", "status")}),
        (
            "Sections to remove on import",
            {
                "fields": (
                    "remove_header",
                    "remove_nav",
                    "remove_footer",
                    "remove_cookie_consent",
                    "remove_ads",
                    "extra_remove_selectors",
                ),
                "description": "Saving re-captures the page from its source URL with these options applied.",
            },
        ),
        ("Capture", {"fields": ("size_display", "fetched_at", "preview_link")}),
    )

    @admin.display(description="Size")
    def size_display(self, obj):
        if not obj.byte_size:
            return "—"
        if obj.byte_size < 1_048_576:
            return f"{obj.byte_size / 1024:.0f} KB"
        return f"{obj.byte_size / 1_048_576:.1f} MB"

    @admin.display(description="Preview")
    def preview_link(self, obj):
        if not obj.pk or not obj.frozen_html:
            return "—"
        url = reverse("cms-frozen-page", args=[obj.pk])
        return format_html('<a href="{}" target="_blank" rel="noopener">Open document ↗</a>', url)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # (Re-)capture whenever the source URL or any removal option changed, or
        # the page was never captured — so edits to those options actually take
        # effect on save instead of silently doing nothing.
        changed = set(getattr(form, "changed_data", None) or [])
        needs_capture = not change or not obj.frozen_html or bool(changed.intersection(_CAPTURE_FIELDS))
        if obj.source_url and needs_capture:
            captured = self._capture(request, obj)
            if captured:
                self.message_user(request, f"Captured {obj.byte_size:,} bytes from {obj.source_url}.", messages.SUCCESS)
        transaction.on_commit(lambda: clear_frozen_page_cache(obj.pk))

    def _capture(self, request, obj) -> bool:
        """(Re-)freeze ``obj`` and persist it. Returns True on success, else messages the error.

        Never raises: a capture failure (bad URL, network, blocked host) must not
        500 the admin save — the row is still saved, just without fresh content.
        """
        try:
            obj.re_freeze()
        except BlockedURLError as exc:
            self.message_user(request, f"Blocked: {exc}", messages.ERROR)
            return False
        except FreezeError as exc:
            self.message_user(request, f"Could not freeze {obj.source_url}: {exc}", messages.ERROR)
            return False
        except Exception as exc:  # noqa: BLE001 - defensive: never let capture break the save
            self.message_user(request, f"Unexpected error freezing {obj.source_url}: {exc}", messages.ERROR)
            return False
        obj.save()  # full save: works for both a new (INSERT) and existing (UPDATE) row
        clear_frozen_page_cache(obj.pk)
        return True

    @admin.action(description="Re-freeze selected pages (re-capture from source)")
    def refreeze_selected(self, request, queryset):
        ok = sum(1 for obj in queryset if self._capture(request, obj))
        if ok:
            self.message_user(request, f"{ok} page(s) re-frozen.", messages.SUCCESS)

    def get_urls(self):
        custom = [
            path("import-url/", self.admin_site.admin_view(self.import_url_view), name="cms_frozenpage_import_url"),
        ]
        return custom + super().get_urls()

    def import_url_view(self, request):
        if request.method == "POST":
            form = FrozenPageImportForm(request.POST)
            if form.is_valid():
                data = form.cleaned_data
                obj = FrozenPage(
                    source_url=data["source_url"],
                    title=data.get("title", ""),
                    slug=_unique_slug(data.get("slug") or data.get("title") or data["source_url"]),
                    status=data["status"],
                    extra_remove_selectors=data.get("extra_remove_selectors", ""),
                    **{field: data.get(field, False) for field in _PRESET_FORM_FIELDS},
                )
                if self._capture(request, obj):
                    self.message_user(request, f"Imported '{obj.title or obj.slug}'.", messages.SUCCESS)
                    return redirect(reverse("admin:cms_frozenpage_change", args=[obj.pk]))
                return redirect(reverse("admin:cms_frozenpage_import_url"))
        else:
            form = FrozenPageImportForm()

        return TemplateResponse(
            request,
            "admin/cms/frozenpage/import_url.html",
            {**self.admin_site.each_context(request), "title": "Import a webpage", "form": form},
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_url"] = reverse("admin:cms_frozenpage_import_url")
        return super().changelist_view(request, extra_context=extra_context)
