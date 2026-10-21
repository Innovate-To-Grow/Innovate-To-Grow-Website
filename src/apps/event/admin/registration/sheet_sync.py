"""Event-specific controls for registration spreadsheet synchronization."""

import copy
from dataclasses import dataclass

from django.contrib import admin, messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.event.models import Event, RegistrationSheetSyncConfig
from apps.event.services import registration_sheet_sync as sync_api

from .sheet_sync_form import RegistrationSheetSyncForm, configuration_fingerprint

REVIEW_SALT = "event.registration-sheet-sync.review"
REVIEW_MAX_AGE = 600


@dataclass
class _SheetSyncPage:
    """What the sheet-sync page shows after handling the request."""

    form: object
    preview: dict | None = None
    review: dict | None = None
    error: str = ""
    status: int = 200


class RegistrationSheetSyncAdminMixin:
    def get_urls(self):
        return [
            path(
                "<uuid:pk>/sheet-sync/",
                self.admin_site.admin_view(self.registration_sheet_sync_view),
                name="event_event_sheet_sync",
            ),
        ] + super().get_urls()

    @admin.display(description="Registration Google Sheet")
    def registration_sheet_management(self, obj):
        if not obj or not obj.pk:
            return "Save this event to manage its registration sheet."
        return format_html(
            '<a class="i2g-admin-action i2g-admin-action--primary" href="{}">Manage sync</a>'
            '<p class="help">Connection, timing, columns, previews, and sync status.</p>',
            reverse("admin:event_event_sheet_sync", args=[obj.pk]),
        )

    @admin.display(description="Sheet sync")
    def sheet_sync_link(self, obj):
        return format_html('<a href="{}">Manage sync</a>', reverse("admin:event_event_sheet_sync", args=[obj.pk]))

    def registration_sheet_sync_view(self, request, pk):
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        event = get_object_or_404(Event, pk=pk)
        if not self.has_view_permission(request, event):
            raise PermissionDenied("You do not have permission to view registration sheet settings.")
        if request.method == "POST" and not self.has_change_permission(request, event):
            raise PermissionDenied("You do not have permission to manage registration sheet synchronization.")
        config = RegistrationSheetSyncConfig.objects.filter(event=event).first() or RegistrationSheetSyncConfig(
            event=event
        )
        page = _SheetSyncPage(form=RegistrationSheetSyncForm(event=event, config=config))
        action = request.POST.get("action", "") if request.method == "POST" else ""
        if action:
            try:
                response = self._run_sheet_sync_action(request, event, config, action, page)
                if response is not None:
                    return response
            except (sync_api.RegistrationSyncError, ValidationError, signing.BadSignature) as exc:
                page.error = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
                page.status = 400
        elif request.method == "POST":
            page.error = "Choose a sync action."
            page.status = 400
        context = self._sheet_sync_context(request, event, config, page)
        return TemplateResponse(request, "admin/event/event/sheet_sync.html", context, status=page.status)

    def _run_sheet_sync_action(self, request, event, config, action, page):
        """Perform one POSTed action; returns a response to send, or None to re-render the page."""
        if action in {"save_settings", "check_connection", "preview"}:
            return self._run_sheet_sync_form_action(request, event, config, action, page)
        if action == "sync_now":
            if not event.registration_sheet_id:
                raise ValidationError("Save a spreadsheet connection before syncing.")
            sync_api.schedule_registration_sync(event, immediate=True)
            messages.success(
                request,
                "Sync queued. Managed registration data will be updated shortly; other sheet content is preserved.",
            )
            return redirect("admin:event_event_sheet_sync", event.pk)
        if action in {"review_adoption", "review_create", "review_rebuild"}:
            if not event.registration_sheet_id:
                raise ValidationError("Save a spreadsheet connection before continuing.")
            page.preview = sync_api.inspect_registration_sheet(event, config=config)
            operation = action.removeprefix("review_")
            if operation == "adoption" and (not page.preview.get("requires_adoption") or page.preview.get("conflicts")):
                raise ValidationError(
                    "Legacy migration requires an unambiguous match preview. Resolve conflicts before continuing."
                )
            page.review = self._sheet_sync_review(request, event, config, page.preview, operation)
            return None
        if action in {"confirm_adoption", "confirm_create", "confirm_rebuild"}:
            return self._confirm_sheet_sync_review(request, event, config, action.removeprefix("confirm_"))
        raise ValidationError("Choose a valid sync action.")

    def _run_sheet_sync_form_action(self, request, event, config, action, page):
        """Save the settings, or check/preview them on unsaved copies (nothing is written)."""
        page.form = RegistrationSheetSyncForm(request.POST, event=event, config=config)
        if not page.form.is_valid():
            page.status = 400
            return None
        if action == "save_settings":
            return self._save_sheet_sync_settings(request, event, config, page.form)
        draft_event, draft_config = copy.copy(event), copy.copy(config)
        page.form.apply(draft_event, draft_config)
        page.preview = sync_api.inspect_registration_sheet(draft_event, config=draft_config)
        messages.info(
            request,
            "Connection checked. No spreadsheet data or saved settings were changed."
            if action == "check_connection"
            else "Preview complete. No spreadsheet data or saved settings were changed.",
        )
        return None

    def _sheet_sync_context(self, request, event, config, page):
        return {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": event,
            "title": "Registration sheet sync",
            "subtitle": event.name,
            "event": event,
            "config": config,
            "form": page.form,
            "preview": page.preview,
            "review": page.review,
            "sync_error": page.error,
            "pending_changes": max(config.requested_generation - config.completed_generation, 0),
            "can_change": self.has_change_permission(request, event),
            "change_url": reverse("admin:event_event_change", args=[event.pk]),
            "registrations_url": reverse("admin:event_eventregistration_changelist") + f"?event__id__exact={event.pk}",
            "sync_log_url": reverse("admin:event_registrationsheetsynclog_changelist")
            + f"?event__id__exact={event.pk}",
            "google_config_url": reverse("admin:core_googlecredentialconfig_changelist"),
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{event.registration_sheet_id}/edit"
            if event.registration_sheet_id
            else "",
        }

    def _save_sheet_sync_settings(self, request, event, config, form):
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=event.pk)
            config = RegistrationSheetSyncConfig.objects.select_for_update().filter(
                event=event
            ).first() or RegistrationSheetSyncConfig(event=event)
            previous_settings = configuration_fingerprint(event, config)
            form.apply(event, config)
            if config.state == config.State.BLOCKED and previous_settings != configuration_fingerprint(event, config):
                config.state = config.State.IDLE
                config.last_error = ""
            config.full_clean()
            config.save()
            Event.objects.filter(pk=event.pk).update(
                registration_sheet_id=event.registration_sheet_id,
                registration_sheet_gid=event.registration_sheet_gid,
                updated_at=timezone.now(),
            )
            sync_api.schedule_registration_sync(event)
        self.log_change(request, event, "Updated registration sheet synchronization settings.")
        messages.success(request, "Sync settings saved. Pending changes follow the selected timing.")
        return redirect("admin:event_event_sheet_sync", event.pk)

    @staticmethod
    def _sheet_sync_review(request, event, config, preview, operation):
        return {
            "operation": operation,
            "token": signing.dumps(
                {
                    "event": str(event.pk),
                    "user": str(request.user.pk),
                    "operation": operation,
                    "config": configuration_fingerprint(event, config),
                    "fingerprint": preview["fingerprint"],
                },
                salt=REVIEW_SALT,
            ),
        }

    def _confirm_sheet_sync_review(self, request, event, config, operation):
        if request.POST.get("backup_acknowledged") != "on":
            raise ValidationError("Confirm that a backup will be created before continuing.")
        try:
            review = signing.loads(request.POST.get("review_token", ""), salt=REVIEW_SALT, max_age=REVIEW_MAX_AGE)
        except signing.BadSignature as exc:
            raise ValidationError("This review is missing or expired. Preview the operation again.") from exc
        expected = {
            "event": str(event.pk),
            "user": str(request.user.pk),
            "operation": operation,
            "config": configuration_fingerprint(event, config),
        }
        if any(review.get(key) != value for key, value in expected.items()):
            raise ValidationError("The saved settings or review have changed. Preview the operation again.")
        if operation == "adoption":
            count = sync_api.sync_registrations_to_sheet(
                event, adopt_legacy=True, expected_fingerprint=review["fingerprint"]
            )
            messages.success(request, f"Legacy rows migrated after backup. {count} managed row changes applied.")
        else:
            sync_api.create_registration_worksheet(event, expected_fingerprint=review["fingerprint"])
            messages.success(
                request, "Backup completed and a new managed worksheet created. The previous worksheet was preserved."
            )
        self.log_change(
            request, event, f"Completed registration sheet {operation} after preview and backup confirmation."
        )
        return redirect("admin:event_event_sheet_sync", event.pk)
