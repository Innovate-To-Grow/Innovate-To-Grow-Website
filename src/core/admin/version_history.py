"""Admin registration for ModelVersion — browse recent changes, diff, rollback."""

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, path, reverse
from django.utils.html import format_html

from core.admin.base import ReadOnlyModelAdmin
from core.admin.utils import format_json, truncate_text
from core.models.base.versioning import diff_versions
from core.models.versioning import ModelVersion


@admin.register(ModelVersion)
class ModelVersionAdmin(ReadOnlyModelAdmin):
    list_display = (
        "created_at",
        "model_type",
        "object_link",
        "version_number",
        "comment_short",
        "created_by",
        "actions_column",
    )
    list_filter = ("content_type", "created_at", "created_by")
    search_fields = ("object_id", "comment")
    ordering = ("-created_at",)
    list_per_page = 50

    readonly_fields = (
        "id",
        "content_type",
        "object_id",
        "version_number",
        "comment",
        "created_at",
        "created_by",
        "data_display",
    )
    fieldsets = (
        ("Version Info", {"fields": ("content_type", "object_id", "version_number", "comment")}),
        ("Metadata", {"fields": ("created_at", "created_by")}),
        ("Stored Data", {"fields": ("data_display",)}),
    )

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    @admin.display(description="Model", ordering="content_type")
    def model_type(self, obj):
        model_class = obj.content_type.model_class()
        if model_class:
            return model_class.__name__
        return str(obj.content_type)

    @admin.display(description="Object")
    def object_link(self, obj):
        model_class = obj.content_type.model_class()
        if not model_class:
            return str(obj.object_id)
        try:
            url = reverse(
                f"admin:{model_class._meta.app_label}_{model_class._meta.model_name}_change",
                args=[obj.object_id],
            )
            label = str(obj.object_id)[:8]
            # Try to get a readable label from the actual object
            try:
                instance = model_class.all_objects.get(pk=obj.object_id)
                label = truncate_text(str(instance), 40)
            except (model_class.DoesNotExist, AttributeError):
                pass
            return format_html('<a href="{}">{}</a>', url, label)
        except NoReverseMatch:
            return str(obj.object_id)[:8]

    @admin.display(description="Comment")
    def comment_short(self, obj):
        return truncate_text(obj.comment, 60)

    @admin.display(description="Stored Data")
    def data_display(self, obj):
        return format_html(
            '<div style="max-height:600px; overflow:auto;">{}</div>',
            format_json(obj.data),
        )

    @admin.display(description="Actions")
    def actions_column(self, obj):
        diff_url = reverse("admin:core_modelversion_diff", args=[obj.pk])
        rollback_url = reverse("admin:core_modelversion_rollback", args=[obj.pk])
        return format_html(
            '<a href="{}">Diff</a> &nbsp;|&nbsp; <a href="{}">Rollback</a>',
            diff_url,
            rollback_url,
        )

    # ------------------------------------------------------------------
    # Custom URLs
    # ------------------------------------------------------------------

    def get_urls(self):
        custom_urls = [
            path(
                "<uuid:pk>/diff/",
                self.admin_site.admin_view(self.diff_view),
                name="core_modelversion_diff",
            ),
            path(
                "<uuid:pk>/rollback/",
                self.admin_site.admin_view(self.rollback_view),
                name="core_modelversion_rollback",
            ),
        ]
        return custom_urls + super().get_urls()

    # ------------------------------------------------------------------
    # Diff view
    # ------------------------------------------------------------------

    def diff_view(self, request, pk):
        version = get_object_or_404(ModelVersion, pk=pk)
        siblings = ModelVersion.objects.filter(
            content_type=version.content_type,
            object_id=version.object_id,
        ).exclude(pk=pk).order_by("-version_number")

        context = {
            **self.admin_site.each_context(request),
            "title": f"Version Diff — v{version.version_number}",
            "version": version,
            "siblings": siblings,
            "opts": self.model._meta,
        }

        compare_to = request.GET.get("compare_to")
        if compare_to:
            other = get_object_or_404(ModelVersion, pk=compare_to)
            # Always show older version on the left
            if version.version_number < other.version_number:
                v_left, v_right = version, other
            else:
                v_left, v_right = other, version
            try:
                diff = diff_versions(v_left.data, v_right.data)
            except ValueError:
                diff = {}
            # Build row data for the template (avoids complex dict lookups in DTL)
            all_fields = sorted(set((v_left.data or {}).keys()) | set((v_right.data or {}).keys()))
            rows = []
            for field in all_fields:
                left_val = (v_left.data or {}).get(field, "-")
                right_val = (v_right.data or {}).get(field, "-")
                rows.append({
                    "field": field,
                    "left": left_val if left_val is not None else "-",
                    "right": right_val if right_val is not None else "-",
                    "changed": field in diff,
                })
            context.update({
                "v_left": v_left,
                "v_right": v_right,
                "rows": rows,
            })

        return render(request, "admin/core/modelversion/diff.html", context)

    # ------------------------------------------------------------------
    # Rollback view
    # ------------------------------------------------------------------

    def rollback_view(self, request, pk):
        version = get_object_or_404(ModelVersion, pk=pk)
        model_class = version.content_type.model_class()
        changelist_url = reverse("admin:core_modelversion_changelist")

        if not model_class:
            messages.error(request, "Cannot resolve model class for this version.")
            return redirect(changelist_url)

        # Resolve the source object (include soft-deleted)
        manager = getattr(model_class, "all_objects", model_class.objects)
        try:
            obj = manager.get(pk=version.object_id)
        except model_class.DoesNotExist:
            messages.error(request, "The original object no longer exists.")
            return redirect(changelist_url)

        if request.method == "POST":
            obj.rollback(
                version_number=version.version_number,
                user=request.user,
                save_current=True,
            )
            obj.save()  # Persist restored field values (rollback only sets in-memory)
            messages.success(
                request,
                f"Rolled back {model_class.__name__} to version {version.version_number}.",
            )
            return redirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm Rollback — v{version.version_number}",
            "version": version,
            "obj": obj,
            "model_name": model_class.__name__,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/modelversion/rollback_confirm.html", context)
