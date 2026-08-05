"""Admin workflow for permanent route redirects."""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.urls import path, reverse
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget, UnfoldAdminTextInputWidget

from apps.cms.models import RouteRedirect
from apps.cms.services.route_redirects import destination_route_choices, redirect_mapping_conflicts
from apps.core.admin import BaseModelAdmin


class RouteRedirectAdminForm(forms.ModelForm):
    destination_path = forms.ChoiceField(
        label="Destination path",
        help_text="Choose a published CMS page or fixed public application route.",
        widget=UnfoldAdminSelectWidget,
    )

    class Meta:
        model = RouteRedirect
        fields = "__all__"
        widgets = {
            "source_path": UnfoldAdminTextInputWidget(
                attrs={
                    "data-role": "route-redirect-source",
                    "autocomplete": "off",
                    "spellcheck": "false",
                }
            ),
            "notes": UnfoldAdminTextareaWidget(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "Select a destination…"), *destination_route_choices()]
        current_destination = self.instance.destination_path if self.instance.pk else ""
        flattened_values = {value for group in choices[1:] for value, _label in group[1]}
        if current_destination and current_destination not in flattened_values:
            choices.append(("Current value", [(current_destination, f"{current_destination} (currently unavailable)")]))
        self.fields["destination_path"].choices = choices


@admin.register(RouteRedirect)
class RouteRedirectAdmin(BaseModelAdmin):
    form = RouteRedirectAdminForm
    change_form_template = "admin/cms/routeredirect/change_form.html"
    list_display = (
        "source_path",
        "destination_path",
        "is_active",
        "edge_sync_status",
        "updated_at",
    )
    list_filter = ("is_active", "edge_sync_status")
    search_fields = ("source_path", "destination_path", "notes")
    readonly_fields = (
        "edge_sync_status",
        "edge_sync_error",
        "edge_sync_attempted_at",
        "edge_synced_at",
        "created_at",
        "updated_at",
    )
    actions = ("activate_redirects", "deactivate_redirects", "retry_edge_sync")
    fieldsets = (
        (
            "Permanent redirect",
            {
                "fields": ("source_path", "destination_path", "is_active", "notes"),
                "description": (
                    "New mappings are saved inactive. Review the conflict result, then enable the saved mapping: "
                    "redirects are exact, internal, permanent 301s that browsers and search engines may cache "
                    "for a long time."
                ),
            },
        ),
        (
            "Amplify edge sync",
            {
                "fields": (
                    "edge_sync_status",
                    "edge_sync_error",
                    "edge_sync_attempted_at",
                    "edge_synced_at",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is None and "is_active" not in readonly:
            readonly.append("is_active")
        if obj is not None and "source_path" not in readonly:
            readonly.append("source_path")
        return readonly

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_urls(self):
        custom_urls = [
            path(
                "conflict-check/",
                self.admin_site.admin_view(self.conflict_check_view),
                name="cms_routeredirect_conflict_check",
            )
        ]
        return custom_urls + super().get_urls()

    def _change_form_context(self, obj=None):
        return {
            "route_redirect_check_url": reverse("admin:cms_routeredirect_conflict_check"),
            "current_redirect_id": str(obj.pk) if obj else "",
            "current_redirect_source": obj.source_path if obj else "",
        }

    def add_view(self, request, form_url="", extra_context=None):
        context = {**(extra_context or {}), **self._change_form_context()}
        return super().add_view(request, form_url, context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id)
        context = {**(extra_context or {}), **self._change_form_context(obj)}
        return super().change_view(request, object_id, form_url, context)

    def conflict_check_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to access route redirects.")

        source, destination, conflicts = redirect_mapping_conflicts(
            request.GET.get("source_path", ""),
            request.GET.get("destination_path", ""),
            exclude_redirect_id=request.GET.get("redirect_id") or None,
        )
        invalid = any(conflict.code == "invalid" for conflict in conflicts)
        return JsonResponse(
            {
                "source_path": source,
                "destination_path": destination,
                "is_valid": not invalid,
                "has_conflict": bool(conflicts),
                "message": conflicts[0].message if conflicts else "Route mapping is available.",
                "conflicts": [
                    {"code": conflict.code, "field": conflict.field, "message": conflict.message}
                    for conflict in conflicts
                ],
            }
        )

    @admin.action(description="Enable selected permanent redirects")
    def activate_redirects(self, request, queryset):
        activated = 0
        for redirect in queryset:
            if redirect.is_active:
                continue
            redirect.is_active = True
            try:
                redirect.save(update_fields=["is_active", "updated_at"])
            except ValidationError as exc:
                self.message_user(request, f"Could not enable {redirect.source_path}: {exc}", level=messages.ERROR)
            else:
                activated += 1
        if activated:
            self.message_user(request, f"Enabled {activated} permanent redirect(s).", level=messages.SUCCESS)

    @admin.action(description="Disable selected redirects")
    def deactivate_redirects(self, request, queryset):
        disabled = 0
        for redirect in queryset.filter(is_active=True):
            redirect.is_active = False
            redirect.save(update_fields=["is_active", "updated_at"])
            disabled += 1
        if disabled:
            self.message_user(request, f"Disabled {disabled} redirect(s).", level=messages.SUCCESS)

    @admin.action(description="Retry Amplify edge sync for selected redirects")
    def retry_edge_sync(self, request, queryset):
        eligible = queryset.filter(Q(is_active=True) | Q(edge_rule_managed=True))
        redirect_ids = list(eligible.values_list("pk", flat=True))
        if not redirect_ids:
            self.message_user(
                request,
                "No selected redirects require edge synchronization.",
                level=messages.WARNING,
            )
            return

        eligible.update(
            edge_sync_status=RouteRedirect.EdgeSyncStatus.PENDING,
            edge_sync_error="",
        )

        from apps.cms.services.amplify_redirects import schedule_amplify_redirect_sync

        job = schedule_amplify_redirect_sync(immediate=True, redirect_ids=redirect_ids)
        if job is None:
            self.message_user(
                request,
                "Edge sync is pending; Amplify configuration or the background job service is unavailable.",
                level=messages.WARNING,
            )
        else:
            self.message_user(request, "Amplify edge reconciliation was queued.", level=messages.SUCCESS)
