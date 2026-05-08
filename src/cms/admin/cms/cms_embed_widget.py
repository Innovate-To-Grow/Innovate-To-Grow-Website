from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.widgets import UnfoldAdminSelectWidget

from cms.admin.cms.page_admin.editor import _safe_json
from cms.app_routes import EMBEDDABLE_APP_ROUTES
from cms.embed_sections import (
    hidden_section_choices,
    hidden_section_presets_payload,
    normalize_hidden_sections,
)
from cms.models import CMSBlock, CMSEmbedWidget, CMSPage
from core.admin import BaseModelAdmin


class CMSEmbedWidgetAdminForm(forms.ModelForm):
    app_route = forms.ChoiceField(
        required=False,
        choices=[("", "— select an app route —")]
        + [(r["url"], f"{r['title']} ({r['url']})") for r in EMBEDDABLE_APP_ROUTES],
        label="App route",
        help_text="The interactive app page to embed.",
        widget=UnfoldAdminSelectWidget,
    )
    hidden_sections = forms.MultipleChoiceField(
        required=False,
        choices=hidden_section_choices(),
        label="Sections to hide",
        help_text="Choose safe sections to hide when this widget renders inside the embed iframe.",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = CMSEmbedWidget
        fields = (
            "widget_type",
            "page",
            "app_route",
            "slug",
            "admin_label",
            "hidden_sections",
            "block_sort_orders",
        )
        widgets = {
            "block_sort_orders": forms.HiddenInput(),
            "widget_type": UnfoldAdminSelectWidget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].widget.attrs["placeholder"] = "e.g. homepage-hero-banner"
        if self.instance and self.instance.app_route:
            self.fields["app_route"].initial = self.instance.app_route
        if self.instance and self.instance.pk:
            self.fields["hidden_sections"].initial = self.instance.get_effective_hidden_sections()

    def clean(self):
        cleaned = super().clean()
        widget_type = cleaned.get("widget_type")
        app_route = cleaned.get("app_route")
        hidden_sections = cleaned.get("hidden_sections")

        if widget_type is None:
            return cleaned

        try:
            cleaned["hidden_sections"] = normalize_hidden_sections(
                hidden_sections or [],
                widget_type,
                app_route or "",
            )
        except ValidationError as exc:
            self.add_error("hidden_sections", exc.messages)

        return cleaned


@admin.register(CMSEmbedWidget)
class CMSEmbedWidgetAdmin(BaseModelAdmin):
    form = CMSEmbedWidgetAdminForm
    change_form_template = "admin/cms/cmsembedwidget/change_form.html"
    list_display = ("slug", "widget_type", "target_label", "admin_label", "block_count", "updated_at")
    list_filter = ("widget_type", "page")
    search_fields = ("slug", "admin_label", "app_route", "page__title", "page__route")
    autocomplete_fields = ("page",)
    readonly_fields = ("created_at", "updated_at")

    def get_ordering(self, request):
        return ["widget_type", "slug"]

    @admin.display(description="Target")
    def target_label(self, obj):
        if obj.widget_type == "app_route":
            return format_html("<code>{}</code>", obj.app_route or "—")
        if obj.page_id:
            url = reverse("admin:cms_cmspage_change", args=[obj.page_id])
            return format_html('<a href="{}">{}</a>', url, obj.page.title)
        return "—"

    @admin.display(description="Blocks")
    def block_count(self, obj):
        if obj.widget_type == "app_route":
            return "—"
        return len(obj.block_sort_orders or [])

    def get_urls(self):
        custom = [
            path(
                "page-blocks/",
                self.admin_site.admin_view(self.page_blocks_view),
                name="cms_cmsembedwidget_page_blocks",
            ),
            path(
                "page-info/",
                self.admin_site.admin_view(self.page_info_view),
                name="cms_cmsembedwidget_page_info",
            ),
            path(
                "app-routes/",
                self.admin_site.admin_view(self.app_routes_view),
                name="cms_cmsembedwidget_app_routes",
            ),
        ]
        return custom + super().get_urls()

    # noinspection PyMethodMayBeStatic
    def app_routes_view(self, request):
        return JsonResponse({"routes": list(EMBEDDABLE_APP_ROUTES)})

    def page_blocks_view(self, request):
        page_id = request.GET.get("page_id") or ""
        if not page_id:
            return JsonResponse({"blocks": []})
        blocks = (
            CMSBlock.objects.filter(page_id=page_id)
            .order_by("sort_order")
            .values("sort_order", "block_type", "admin_label")
        )
        return JsonResponse({"blocks": list(blocks)})

    def page_info_view(self, request):
        page_id = request.GET.get("page_id") or ""
        if not page_id:
            return JsonResponse({"title": "", "route": ""})
        try:
            page = CMSPage.objects.values("title", "route").get(pk=page_id)
        except CMSPage.DoesNotExist:
            return JsonResponse({"title": "", "route": ""})
        return JsonResponse({"title": page["title"], "route": page["route"]})

    def _extra_context(self, obj=None):
        from django.conf import settings as ds

        return {
            "frontend_url": (getattr(ds, "FRONTEND_URL", "") or "").rstrip("/"),
            "page_blocks_url": reverse("admin:cms_cmsembedwidget_page_blocks"),
            "page_info_url": reverse("admin:cms_cmsembedwidget_page_info"),
            "app_routes_url": reverse("admin:cms_cmsembedwidget_app_routes"),
            "hidden_section_presets_json": _safe_json(hidden_section_presets_payload()),
            "initial_block_sort_orders_json": _safe_json(obj.block_sort_orders if obj else []),
            "initial_slug": obj.slug if obj else "",
            "initial_page_id": str(obj.page_id) if obj and obj.page_id else "",
            "initial_widget_type": obj.widget_type if obj else "blocks",
            "initial_app_route": obj.app_route if obj else "",
        }

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id) if object_id else None
        extra = {**(extra_context or {}), **self._extra_context(obj)}
        return super().change_view(request, object_id, form_url, extra)

    def add_view(self, request, form_url="", extra_context=None):
        extra = {**(extra_context or {}), **self._extra_context()}
        return super().add_view(request, form_url, extra)
