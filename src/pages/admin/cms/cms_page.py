import json
import logging

from django import forms
from django.contrib import admin, messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from unfold.admin import ModelAdmin

from pages.management.commands.cms_seed import SEED_PAGES as SEED_PAGES_PHASE1
from pages.management.commands.cms_seed_batch_ab import SEED_PAGES as SEED_PAGES_AB
from pages.management.commands.cms_seed_batch_cd import SEED_PAGES as SEED_PAGES_CD
from pages.models import BLOCK_SCHEMAS, BLOCK_TYPE_CHOICES, CMSBlock, CMSPage, validate_block_data
from pages.models.pages.cms.cms_page import normalize_cms_route, validate_cms_route

logger = logging.getLogger(__name__)


class CMSPageAdminForm(forms.ModelForm):
    def clean_route(self):
        route = validate_cms_route(self.cleaned_data.get("route"))
        conflict = CMSPage.all_objects.filter(route=route).exclude(pk=self.instance.pk).first()
        if conflict:
            raise forms.ValidationError(f'Route "{route}" is already used by "{conflict.title}".')
        return route

    class Meta:
        model = CMSPage
        fields = "__all__"
        widgets = {
            # Use a single-line input so styling matches the title field
            "meta_description": forms.TextInput(
                attrs={
                    "class": (
                        "border border-base-200 bg-white font-medium min-w-20 "
                        "placeholder-base-400 rounded-default shadow-xs text-font-default-light text-sm "
                        "focus:outline-2 focus:-outline-offset-2 focus:outline-primary-600 "
                        "h-[38px] w-full max-w-2xl block"
                    )
                }
            ),
            "route": forms.TextInput(
                attrs={
                    "data-role": "cms-route-source",
                    "autocomplete": "off",
                    "spellcheck": "false",
                }
            ),
        }


@admin.register(CMSPage)
class CMSPageAdmin(ModelAdmin):
    form = CMSPageAdminForm
    change_form_template = "admin/pages/cmspage/change_form.html"
    list_display = ("title", "route", "status", "block_count", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "slug", "route")
    readonly_fields = ("created_at", "updated_at", "published_at")
    # Blocks are managed by the visual JS editor, not Django inlines
    inlines = []
    actions = ["export_pages"]

    fieldsets = (
        (
            "Page Info",
            {
                "fields": (
                    "slug",
                    "route",
                    "title",
                    "meta_description",
                    "page_css_class",
                    "status",
                    "sort_order",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("published_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def block_count(self, obj):
        return obj.blocks.filter(is_deleted=False).count()

    block_count.short_description = "Blocks"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.status == "published":
            readonly.append("slug")
        return readonly

    # ===== Custom URLs =====

    def get_urls(self):
        custom_urls = [
            path("preview/", self.admin_site.admin_view(self.preview_store_view), name="pages_cmspage_preview"),
            path(
                "route-conflict/",
                self.admin_site.admin_view(self.route_conflict_view),
                name="pages_cmspage_route_conflict",
            ),
            path("import/", self.admin_site.admin_view(self.import_view), name="pages_cmspage_import"),
            path("import-all/", self.admin_site.admin_view(self.import_all_view), name="pages_cmspage_import_all"),
        ]
        return custom_urls + super().get_urls()

    # ===== Changelist: add import buttons =====

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_import_buttons"] = True
        return super().changelist_view(request, extra_context)

    # ===== Context injection for visual editor =====

    def _get_editor_context(self, obj=None):
        from django.conf import settings as django_settings

        frontend_url = getattr(django_settings, "FRONTEND_URL", "") or ""
        ctx = {
            "block_schemas_json": json.dumps(BLOCK_SCHEMAS),
            "block_type_choices_json": json.dumps(BLOCK_TYPE_CHOICES),
            "route_check_url": reverse("admin:pages_cmspage_route_conflict"),
            "current_page_id": str(obj.pk) if obj else "",
            "current_page_route": obj.route if obj else "",
            "frontend_url": frontend_url.rstrip("/"),
        }
        if obj:
            blocks = obj.blocks.filter(is_deleted=False).order_by("sort_order")
            blocks_data = [
                {
                    "block_type": b.block_type,
                    "sort_order": b.sort_order,
                    "admin_label": b.admin_label,
                    "data": b.data,
                }
                for b in blocks
            ]
            ctx["initial_blocks_json"] = json.dumps(blocks_data, cls=DjangoJSONEncoder)
        else:
            ctx["initial_blocks_json"] = "[]"
        return ctx

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id) if object_id else None
        extra_context.update(self._get_editor_context(obj))
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(self._get_editor_context())
        return super().add_view(request, form_url, extra_context)

    # ===== Save blocks from visual editor JSON =====

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        blocks_json = request.POST.get("blocks_json", "")
        if not blocks_json:
            return

        page = form.instance
        try:
            blocks_data = json.loads(blocks_json)
            if not isinstance(blocks_data, list):
                messages.error(request, "Invalid blocks data: expected a JSON array.")
                return
        except json.JSONDecodeError as e:
            messages.error(request, f"Invalid blocks JSON: {e}")
            return

        # Soft-delete existing blocks
        page.blocks.filter(is_deleted=False).update(is_deleted=True, deleted_at=timezone.now())

        # Create new blocks
        for i, block_data in enumerate(blocks_data):
            block_type = block_data.get("block_type", "")
            data = block_data.get("data", {})

            try:
                validate_block_data(block_type, data)
            except Exception as e:
                messages.warning(request, f"Block #{i + 1} ({block_type}): {e}")
                continue

            CMSBlock.objects.create(
                page=page,
                block_type=block_type,
                sort_order=i,
                admin_label=block_data.get("admin_label", ""),
                data=data,
            )

    # ===== Preview store endpoint =====

    def preview_store_view(self, request):
        """Store preview data in cache and return a token."""
        if request.method != "POST":
            return JsonResponse({"detail": "Method not allowed."}, status=405)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"detail": "Invalid JSON."}, status=400)

        import uuid

        token = uuid.uuid4().hex
        cache.set(f"cms:preview:{token}", data, timeout=600)
        return JsonResponse({"token": token})

    def route_conflict_view(self, request):
        route = request.GET.get("route", "")
        page_id = request.GET.get("page_id")
        normalized_route = normalize_cms_route(route)

        try:
            normalized_route = validate_cms_route(normalized_route)
        except ValidationError as exc:
            return JsonResponse(
                {
                    "normalized_route": normalized_route,
                    "has_conflict": False,
                    "is_valid": False,
                    "message": exc.messages[0],
                }
            )

        conflict_qs = CMSPage.all_objects.filter(route=normalized_route)
        if page_id:
            conflict_qs = conflict_qs.exclude(pk=page_id)

        conflict = conflict_qs.values("title", "status").first()
        if conflict:
            return JsonResponse(
                {
                    "normalized_route": normalized_route,
                    "has_conflict": True,
                    "is_valid": True,
                    "message": f'Already used by "{conflict["title"]}" ({conflict["status"]}).',
                }
            )

        return JsonResponse(
            {
                "normalized_route": normalized_route,
                "has_conflict": False,
                "is_valid": True,
                "message": "",
            }
        )

    # ===== Export =====

    @admin.action(description="Export selected pages as JSON")
    def export_pages(self, request, queryset):
        pages_data = []
        for page in queryset.prefetch_related("blocks"):
            blocks = page.blocks.filter(is_deleted=False).order_by("sort_order")
            pages_data.append(
                {
                    "slug": page.slug,
                    "route": page.route,
                    "title": page.title,
                    "meta_description": page.meta_description,
                    "page_css_class": page.page_css_class,
                    "status": page.status,
                    "sort_order": page.sort_order,
                    "blocks": [
                        {
                            "block_type": b.block_type,
                            "sort_order": b.sort_order,
                            "admin_label": b.admin_label,
                            "data": b.data,
                        }
                        for b in blocks
                    ],
                }
            )

        content = json.dumps(
            {
                "version": 1,
                "exported_at": timezone.now().isoformat(),
                "pages": pages_data,
            },
            indent=2,
            cls=DjangoJSONEncoder,
            ensure_ascii=False,
        )
        response = HttpResponse(content, content_type="application/json")
        filename = f"cms_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    # ===== Import =====

    def import_view(self, request):
        """Import CMS pages from a JSON file."""
        context = {
            **self.admin_site.each_context(request),
            "title": "Import CMS Pages",
            "opts": self.model._meta,
        }

        if request.method != "POST":
            return render(request, "admin/pages/cmspage/import_form.html", context)

        json_file = request.FILES.get("json_file")
        if not json_file:
            messages.error(request, "Please select a JSON file to import.")
            return render(request, "admin/pages/cmspage/import_form.html", context)

        try:
            raw = json_file.read().decode("utf-8")
            bundle = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            messages.error(request, f"Invalid JSON file: {e}")
            return render(request, "admin/pages/cmspage/import_form.html", context)

        if not isinstance(bundle, dict) or "pages" not in bundle:
            messages.error(request, "Invalid format: expected a JSON object with a 'pages' key.")
            return render(request, "admin/pages/cmspage/import_form.html", context)

        pages_data = bundle["pages"]
        if not isinstance(pages_data, list):
            messages.error(request, "Invalid format: 'pages' must be a list.")
            return render(request, "admin/pages/cmspage/import_form.html", context)

        action = request.POST.get("action", "dry_run")
        block_type_keys = {c[0] for c in BLOCK_TYPE_CHOICES}
        results = []

        for page_data in pages_data:
            slug = page_data.get("slug", "")
            route = page_data.get("route", "")
            title = page_data.get("title", "")
            result = {"slug": slug, "title": title, "errors": [], "action": ""}

            # Validate required fields
            if not slug:
                result["errors"].append("Missing 'slug'.")
            if not route:
                result["errors"].append("Missing 'route'.")
            if not title:
                result["errors"].append("Missing 'title'.")

            # Validate blocks
            blocks_data = page_data.get("blocks", [])
            for i, bd in enumerate(blocks_data):
                bt = bd.get("block_type", "")
                if bt not in block_type_keys:
                    result["errors"].append(f"Block #{i + 1}: unknown type '{bt}'.")
                else:
                    try:
                        validate_block_data(bt, bd.get("data", {}))
                    except Exception as e:
                        result["errors"].append(f"Block #{i + 1} ({bt}): {e}")

            # Determine create vs update
            existing = CMSPage.objects.filter(slug=slug).first() if slug else None
            result["action"] = "update" if existing else "create"

            if result["errors"]:
                results.append(result)
                continue

            # Execute if not dry run
            if action == "execute":
                try:
                    if existing:
                        existing.route = route
                        existing.title = title
                        existing.meta_description = page_data.get("meta_description", "")
                        existing.page_css_class = page_data.get("page_css_class", "")
                        existing.status = page_data.get("status", "draft")
                        existing.sort_order = page_data.get("sort_order", 0)
                        existing.save()
                        page = existing
                        # Soft-delete old blocks
                        page.blocks.filter(is_deleted=False).update(is_deleted=True, deleted_at=timezone.now())
                    else:
                        page = CMSPage.objects.create(
                            slug=slug,
                            route=route,
                            title=title,
                            meta_description=page_data.get("meta_description", ""),
                            page_css_class=page_data.get("page_css_class", ""),
                            status=page_data.get("status", "draft"),
                            sort_order=page_data.get("sort_order", 0),
                        )

                    # Create blocks
                    for i, bd in enumerate(blocks_data):
                        CMSBlock.objects.create(
                            page=page,
                            block_type=bd.get("block_type"),
                            sort_order=bd.get("sort_order", i),
                            admin_label=bd.get("admin_label", ""),
                            data=bd.get("data", {}),
                        )
                    result["success"] = True
                except Exception as e:
                    result["errors"].append(str(e))

            results.append(result)

        if action == "execute":
            success_count = sum(1 for r in results if r.get("success"))
            error_count = sum(1 for r in results if r.get("errors"))
            if success_count:
                messages.success(request, f"Successfully imported {success_count} page(s).")
            if error_count:
                messages.warning(request, f"{error_count} page(s) had errors.")

        context["results"] = results
        context["is_dry_run"] = action != "execute"
        context["has_results"] = True
        return render(request, "admin/pages/cmspage/import_form.html", context)

    # ===== Import All Seed Pages =====

    def _get_all_seed_pages(self):
        """Collect all seed page data from management commands."""
        all_pages = []
        all_pages.extend(SEED_PAGES_PHASE1)
        all_pages.extend(SEED_PAGES_AB)
        all_pages.extend(SEED_PAGES_CD)
        return all_pages

    def import_all_view(self, request):
        """Import all seed pages at once, with preview and execute modes."""
        context = {
            **self.admin_site.each_context(request),
            "title": "Import All Seed Pages",
            "opts": self.model._meta,
        }

        all_seed_pages = self._get_all_seed_pages()
        block_type_keys = {c[0] for c in BLOCK_TYPE_CHOICES}
        action = request.POST.get("action") if request.method == "POST" else None

        results = []
        for page_data in all_seed_pages:
            slug = page_data.get("slug", "")
            title = page_data.get("title", "")
            result = {"slug": slug, "title": title, "errors": [], "action": ""}

            blocks_data = page_data.get("blocks", [])
            for i, bd in enumerate(blocks_data):
                bt = bd.get("block_type", "")
                if bt not in block_type_keys:
                    result["errors"].append(f"Block #{i + 1}: unknown type '{bt}'.")
                else:
                    try:
                        validate_block_data(bt, bd.get("data", {}))
                    except Exception as e:
                        result["errors"].append(f"Block #{i + 1} ({bt}): {e}")

            existing = CMSPage.objects.filter(slug=slug).first() if slug else None
            result["action"] = "update" if existing else "create"
            result["block_count"] = len(blocks_data)

            if result["errors"]:
                results.append(result)
                continue

            if action == "execute":
                try:
                    if existing:
                        existing.route = page_data.get("route", existing.route)
                        existing.title = title
                        existing.meta_description = page_data.get("meta_description", "")
                        existing.page_css_class = page_data.get("page_css_class", "")
                        existing.status = page_data.get("status", "published")
                        existing.sort_order = page_data.get("sort_order", 0)
                        existing.save()
                        page = existing
                        page.blocks.filter(is_deleted=False).update(is_deleted=True, deleted_at=timezone.now())
                    else:
                        page = CMSPage.objects.create(
                            slug=slug,
                            route=page_data.get("route", f"/{slug}"),
                            title=title,
                            meta_description=page_data.get("meta_description", ""),
                            page_css_class=page_data.get("page_css_class", ""),
                            status=page_data.get("status", "published"),
                            sort_order=page_data.get("sort_order", 0),
                        )

                    for i, bd in enumerate(blocks_data):
                        CMSBlock.objects.create(
                            page=page,
                            block_type=bd.get("block_type"),
                            sort_order=bd.get("sort_order", i),
                            admin_label=bd.get("admin_label", ""),
                            data=bd.get("data", {}),
                        )
                    result["success"] = True
                except Exception as e:
                    result["errors"].append(str(e))

            results.append(result)

        if action == "execute":
            success_count = sum(1 for r in results if r.get("success"))
            error_count = sum(1 for r in results if r.get("errors"))
            if success_count:
                messages.success(request, f"Successfully imported {success_count} seed page(s).")
            if error_count:
                messages.warning(request, f"{error_count} page(s) had errors.")

        context["results"] = results
        context["total_pages"] = len(all_seed_pages)
        context["is_dry_run"] = action != "execute"
        context["has_results"] = action is not None
        return render(request, "admin/pages/cmspage/import_all_form.html", context)
