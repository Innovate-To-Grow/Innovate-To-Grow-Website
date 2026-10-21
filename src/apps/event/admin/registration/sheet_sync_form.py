"""The registration Google Sheet settings form (destination, ID column, field-to-column mappings)."""

import copy
import hashlib
import json
import re
from urllib.parse import parse_qs, urlparse

from django import forms
from django.core.exceptions import ValidationError

from apps.event.services import registration_sheet_sync as sync_api

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
