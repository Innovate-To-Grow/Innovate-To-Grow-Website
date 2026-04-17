import json

from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, reverse
from django.utils.html import format_html

from cms.models import CMSBlock, CMSEmbedWidget
from core.admin import BaseModelAdmin


class CMSEmbedWidgetAdminForm(forms.ModelForm):
    class Meta:
        model = CMSEmbedWidget
        fields = ("page", "slug", "admin_label", "block_sort_orders")
        widgets = {
            "block_sort_orders": forms.HiddenInput(),
        }


@admin.register(CMSEmbedWidget)
class CMSEmbedWidgetAdmin(BaseModelAdmin):
    form = CMSEmbedWidgetAdminForm
    change_form_template = "admin/cms/cmsembedwidget/change_form.html"
    list_display = ("slug", "page_link", "admin_label", "block_count", "updated_at")
    list_filter = ("page",)
    search_fields = ("slug", "admin_label", "page__title", "page__route")
    autocomplete_fields = ("page",)
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Page")
    def page_link(self, obj):
        url = reverse("admin:cms_cmspage_change", args=[obj.page_id])
        return format_html('<a href="{}">{}</a>', url, obj.page.title)

    @admin.display(description="Blocks")
    def block_count(self, obj):
        return len(obj.block_sort_orders or [])

    def get_urls(self):
        custom = [
            path(
                "page-blocks/",
                self.admin_site.admin_view(self.page_blocks_view),
                name="cms_cmsembedwidget_page_blocks",
            ),
        ]
        return custom + super().get_urls()

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

    def _extra_context(self, obj=None):
        from django.conf import settings as ds

        return {
            "frontend_url": (getattr(ds, "FRONTEND_URL", "") or "").rstrip("/"),
            "page_blocks_url": reverse("admin:cms_cmsembedwidget_page_blocks"),
            "initial_block_sort_orders_json": json.dumps(obj.block_sort_orders if obj else []),
            "initial_slug": obj.slug if obj else "",
            "initial_page_id": str(obj.page_id) if obj and obj.page_id else "",
        }

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id) if object_id else None
        extra = {**(extra_context or {}), **self._extra_context(obj)}
        return super().change_view(request, object_id, form_url, extra)

    def add_view(self, request, form_url="", extra_context=None):
        extra = {**(extra_context or {}), **self._extra_context()}
        return super().add_view(request, form_url, extra)
