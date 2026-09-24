"""Stable field identities, separate from configurable worksheet labels."""

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class RegistrationField:
    key: str
    label: str
    enabled: bool = True
    aliases: tuple[str, ...] = ()
    explicit_label: bool = False


def registration_fields(event, config=None):
    defaults = [
        RegistrationField("order", "Order"),
        RegistrationField("first_name", "First Name"),
        RegistrationField("last_name", "Last Name"),
        RegistrationField("phone", "Phone", event.collect_phone, ("Phone Number",)),
        RegistrationField("created_at", "When Started", True, ("Registered At",)),
        RegistrationField("updated_at", "Last Updated", True, ("Updated At",)),
        RegistrationField("primary_email", "Membership Primary", True, ("Primary Email",)),
        RegistrationField("secondary_email", "Membership Secondary", event.allow_secondary_email, ("Secondary Email",)),
        RegistrationField("ticket_type", "Ticket Type"),
        RegistrationField("ticket_code", "Ticket Code"),
        RegistrationField("organization", "Organization", False),
    ]
    defaults.extend(
        RegistrationField(f"question:{question.pk}", question.text)
        for question in sorted(event.questions.all(), key=lambda item: (item.order, str(item.pk)))
    )
    defaults.extend(
        [RegistrationField("status", "Registration Status"), RegistrationField("registration_id", "Registration ID")]
    )
    settings = getattr(config, "field_settings", None) or {}
    fields = []
    for field in defaults:
        choice = settings.get(field.key, {})
        if not isinstance(choice, dict):
            from .sheets import RegistrationSyncError

            raise RegistrationSyncError(f"Invalid settings for field {field.key}.")
        label = str(choice.get("label") or field.label).strip()
        fields.append(
            RegistrationField(
                field.key,
                label,
                True if field.key in {"registration_id", "status"} else choice.get("enabled", field.enabled),
                (field.label, *field.aliases),
                bool(choice.get("label")),
            )
        )
    return fields


def available_registration_fields(event, config=None):
    return [
        {
            "key": field.key,
            "label": field.label,
            "enabled": field.enabled,
            "required": field.key in {"registration_id", "status"},
        }
        for field in registration_fields(event, config)
    ]


def registration_values(registration, event, order, fields):
    """Return raw text; the provider always uses explicit stringValue cells."""
    values = {
        "order": str(order),
        "first_name": registration.attendee_first_name,
        "last_name": registration.attendee_last_name,
        "phone": registration.attendee_phone,
        "created_at": registration.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": registration.updated_at.strftime("%Y-%m-%d %H:%M"),
        "primary_email": registration.attendee_email,
        "secondary_email": registration.attendee_secondary_email,
        "ticket_type": registration.ticket.name,
        "ticket_code": registration.ticket_code,
        "organization": registration.attendee_organization,
        "status": "Active",
        "registration_id": str(registration.pk),
    }
    question_fields = [field for field in fields if field.key.startswith("question:")]
    question_labels = {field.key: field.aliases[0] if field.aliases else field.label for field in question_fields}
    label_counts = Counter(question_labels.values())
    answer_labels = Counter(
        answer.get("question_text", "") for answer in registration.question_answers if not answer.get("question_id")
    )
    for field in question_fields:
        question_id = field.key.removeprefix("question:")
        matches = [
            answer for answer in registration.question_answers if str(answer.get("question_id", "")) == question_id
        ]
        if len(matches) == 1:
            values[field.key] = str(matches[0].get("answer", ""))
            continue
        text = question_labels.get(field.key, "")
        legacy = [
            answer
            for answer in registration.question_answers
            if not answer.get("question_id") and answer.get("question_text") == text
        ]
        values[field.key] = str(legacy[0].get("answer", "")) if label_counts[text] == answer_labels[text] == 1 else ""
    return {key: str(value or "") for key, value in values.items()}
