"""Event-specific controls for registration spreadsheet synchronization."""

import copy
import hashlib
import json
import re
from urllib.parse import parse_qs, urlparse

from django import forms
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

REVIEW_SALT = "event.registration-sheet-sync.review"
REVIEW_MAX_AGE = 600
REQUIRED_FIELDS = {"registration_id", "status"}


def column_letter(column):
    result = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        result = chr(65 + remainder) + result
    return result


class SheetColumnField(forms.CharField):
    def clean(self, value):
        value = super().clean(value).strip().upper()
        if not value:
            return None
        if value.isdigit():
            number = int(value)
        elif re.fullmatch(r"[A-Z]{1,3}", value):
            number = 0
            for letter in value:
                number = number * 26 + ord(letter) - 64
        else:
            raise ValidationError("Enter a column letter such as A or a number such as 1.")
        if not 1 <= number <= 18278:
            raise ValidationError("Choose a column from A to ZZZ (1 to 18278).")
        return number


class RegistrationSheetSyncForm(forms.Form):
    spreadsheet = forms.CharField(
        required=False,
        label="Spreadsheet URL or ID",
        max_length=500,
        help_text="Share the spreadsheet with the configured Google service account as an editor.",
    )
    worksheet_id = forms.IntegerField(
        required=False,
        min_value=0,
        label="Worksheet ID (gid)",
        help_text="The number after gid= in the sheet URL. Leave blank to use the first worksheet.",
    )
    sync_mode = forms.ChoiceField(
        label="Sync timing",
        choices=(
            ("automatic", "Automatic after changes"),
            ("interval", "Batch changes at an interval"),
            ("manual", "Manual only"),
        ),
        widget=forms.RadioSelect,
    )
    interval_minutes = forms.TypedChoiceField(
        label="Batch changes every",
        choices=((1, "1 minute"), (5, "5 minutes"), (15, "15 minutes"), (30, "30 minutes")),
        coerce=int,
    )
    header_row = forms.IntegerField(min_value=1, max_value=1000, label="Header row")

    def __init__(self, *args, event, config, **kwargs):
        self.schema = sync_api.available_registration_fields(event)
        self.existing_field_settings = copy.deepcopy(config.field_settings)
        initial = {
            "spreadsheet": event.registration_sheet_id,
            "worksheet_id": event.registration_sheet_gid,
            "sync_mode": config.sync_mode,
            "interval_minutes": config.interval_minutes,
            "header_row": config.header_row,
        }
        super().__init__(*args, initial=initial, **kwargs)
        for index, field in enumerate(self.schema):
            key = field["key"]
            settings = config.field_settings.get(key, {})
            enabled = True if key in REQUIRED_FIELDS else settings.get("enabled", field.get("enabled", True))
            self.fields[f"field_{index}_enabled"] = forms.BooleanField(
                required=False, initial=enabled, disabled=key in REQUIRED_FIELDS, label=f"Include {field['label']}"
            )
            self.fields[f"field_{index}_label"] = forms.CharField(
                initial=settings.get("label", field["label"]), max_length=500, label=f"{field['label']} column label"
            )
            column = config.column_mappings.get(key)
            self.fields[f"field_{index}_column"] = SheetColumnField(
                required=False,
                initial=column_letter(column) if isinstance(column, int) and column > 0 else "",
                label=f"{field['label']} sheet column",
                widget=forms.TextInput(attrs={"placeholder": "Automatic", "list": "sheet-column-options"}),
            )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sheet-sync-input")
            field.widget.attrs.setdefault("aria-label", field.label)

    @property
    def field_rows(self):
        return [
            {
                "key": field["key"],
                "label": field["label"],
                "required": field["key"] in REQUIRED_FIELDS,
                "enabled": self[f"field_{index}_enabled"],
                "column_label": self[f"field_{index}_label"],
                "column": self[f"field_{index}_column"],
            }
            for index, field in enumerate(self.schema)
        ]

    def clean_spreadsheet(self):
        value = self.cleaned_data["spreadsheet"].strip()
        if not value:
            return ""
        if "://" in value:
            parsed = urlparse(value)
            match = re.match(r"^/spreadsheets/d/([A-Za-z0-9_-]+)(?:/|$)", parsed.path)
            if parsed.scheme != "https" or parsed.hostname != "docs.google.com" or not match:
                raise ValidationError("Enter a Google Sheets URL or its spreadsheet ID.")
            return match.group(1)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValidationError("Enter a Google Sheets URL or its spreadsheet ID.")
        return value

    def clean(self):
        cleaned = super().clean()
        raw_url = self.data.get("spreadsheet", "") if self.is_bound else ""
        if "://" in raw_url and cleaned.get("worksheet_id") is None:
            parsed = urlparse(raw_url)
            query = {**parse_qs(parsed.query), **parse_qs(parsed.fragment)}
            gid = query.get("gid", [""])[0]
            if gid.isdigit():
                cleaned["worksheet_id"] = int(gid)
        settings = self.existing_field_settings.copy()
        mappings = {}
        used_columns = {}
        enabled_labels = {}
        for index, field in enumerate(self.schema):
            key = field["key"]
            enabled = cleaned.get(f"field_{index}_enabled", False)
            label = cleaned.get(f"field_{index}_label", "")
            column = cleaned.get(f"field_{index}_column")
            settings[key] = {"enabled": enabled}
            if label and label != field["label"]:
                settings[key]["label"] = label
            if enabled and label:
                normalized = label.casefold()
                if normalized in enabled_labels:
                    self.add_error(f"field_{index}_label", "Enabled fields must have different column labels.")
                enabled_labels[normalized] = key
            if column is not None:
                if column in used_columns:
                    self.add_error(f"field_{index}_column", "Each sheet column can be mapped to only one field.")
                mappings[key] = column
                used_columns[column] = key
        cleaned["field_settings"] = settings
        cleaned["column_mappings"] = mappings
        return cleaned

    def apply(self, event, config):
        event.registration_sheet_id = self.cleaned_data["spreadsheet"]
        event.registration_sheet_gid = self.cleaned_data["worksheet_id"]
        for field in ("sync_mode", "interval_minutes", "header_row", "field_settings", "column_mappings"):
            setattr(config, field, self.cleaned_data[field])
        config.debounce_seconds = 15
        config.max_delay_seconds = 60


def configuration_fingerprint(event, config):
    settings = copy.deepcopy(config.field_settings)
    for field in sync_api.available_registration_fields(event):
        choice = settings.get(field["key"], {})
        settings[field["key"]] = {
            "enabled": True if field["key"] in REQUIRED_FIELDS else choice.get("enabled", field["enabled"]),
            "label": str(choice.get("label") or field["label"]).strip(),
        }
    values = {
        "spreadsheet": event.registration_sheet_id,
        "worksheet": event.registration_sheet_gid,
        "field_settings": settings,
        **{
            field: getattr(config, field)
            for field in (
                "sync_mode",
                "debounce_seconds",
                "max_delay_seconds",
                "interval_minutes",
                "header_row",
                "column_mappings",
            )
        },
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


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
        form = RegistrationSheetSyncForm(event=event, config=config)
        preview = None
        review = None
        error = ""
        status = 200
        action = request.POST.get("action", "") if request.method == "POST" else ""
        if action:
            try:
                if action in {"save_settings", "check_connection", "preview"}:
                    form = RegistrationSheetSyncForm(request.POST, event=event, config=config)
                    if form.is_valid():
                        if action == "save_settings":
                            return self._save_sheet_sync_settings(request, event, config, form)
                        draft_event, draft_config = copy.copy(event), copy.copy(config)
                        form.apply(draft_event, draft_config)
                        preview = sync_api.inspect_registration_sheet(draft_event, config=draft_config)
                        messages.info(
                            request,
                            "Connection checked. No spreadsheet data or saved settings were changed."
                            if action == "check_connection"
                            else "Preview complete. No spreadsheet data or saved settings were changed.",
                        )
                    else:
                        status = 400
                elif action == "sync_now":
                    if not event.registration_sheet_id:
                        raise ValidationError("Save a spreadsheet connection before syncing.")
                    sync_api.schedule_registration_sync(event, immediate=True)
                    messages.success(
                        request,
                        "Sync queued. Managed registration data will be updated shortly; other sheet content is preserved.",
                    )
                    return redirect("admin:event_event_sheet_sync", event.pk)
                elif action in {"review_adoption", "review_create", "review_rebuild"}:
                    if not event.registration_sheet_id:
                        raise ValidationError("Save a spreadsheet connection before continuing.")
                    preview = sync_api.inspect_registration_sheet(event, config=config)
                    operation = action.removeprefix("review_")
                    if operation == "adoption" and (not preview.get("requires_adoption") or preview.get("conflicts")):
                        raise ValidationError(
                            "Legacy migration requires an unambiguous match preview. Resolve conflicts before continuing."
                        )
                    review = self._sheet_sync_review(request, event, config, preview, operation)
                elif action in {"confirm_adoption", "confirm_create", "confirm_rebuild"}:
                    return self._confirm_sheet_sync_review(request, event, config, action.removeprefix("confirm_"))
                else:
                    raise ValidationError("Choose a valid sync action.")
            except (sync_api.RegistrationSyncError, ValidationError, signing.BadSignature) as exc:
                error = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
                status = 400
        elif request.method == "POST":
            error = "Choose a sync action."
            status = 400
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": event,
            "title": "Registration sheet sync",
            "subtitle": event.name,
            "event": event,
            "config": config,
            "form": form,
            "preview": preview,
            "review": review,
            "sync_error": error,
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
        return TemplateResponse(request, "admin/event/event/sheet_sync.html", context, status=status)

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
