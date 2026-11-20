"""The ticket page: its read-only displays, saving, the change view and the page's own URLs."""

import uuid

from django.db.models import Case, IntegerField, Q, Value, When
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from unfold.decorators import display

from apps.core.services.email.inbound import LABELS

from ...models import HelpdeskSettings, ResponseTemplate, Ticket
from ...services import outbound, tickets
from ...services.tickets import shadow, sla
from . import timeline, views
from .queue import EDITABLE
from .views import REPLY_STATUS_CHOICES


def _clock_html(clock: sla.Clock, met_at=None) -> str:
    if clock.state == "none":
        return "No SLA"
    due = f" — due {timezone.localtime(clock.due):%b %d, %Y %H:%M}" if clock.due else ""
    met = (
        f", responded {timezone.localtime(met_at):%b %d %H:%M}" if met_at and clock.state in ("met", "breached") else ""
    )
    return format_html(
        '<span class="i2g-helpdesk-sla is-{}">{}</span>{}{}', clock.state.replace("_", "-"), clock.label, due, met
    )


class TicketPageMixin:
    """The ticket-page section of ``TicketAdmin``."""

    # --- ticket page -----------------------------------------------------------------------------------------------

    @display(description="Number")
    def number_display(self, obj):
        return obj.display_number

    @display(description="Requester")
    def requester_display(self, obj):
        if obj.requester_name:
            return f"{obj.requester_name} <{obj.requester_email}>"
        return obj.requester_email or "—"

    @display(description="Participants")
    def participants_display(self, obj):
        return ", ".join(obj.participants or []) or "—"

    @display(description="Classification")
    def classification_display(self, obj):
        label = LABELS.get(obj.classification, obj.classification or "—")
        return f"{label} — automated, hidden from the default queue" if obj.automated else label

    @display(description="Flags")
    def flags_display(self, obj):
        return ", ".join(str(flag).replace("_", " ") for flag in obj.flags or []) or "—"

    @display(description="Linked tickets")
    def links_display(self, obj):
        linked = [("Related to", obj.related_ticket), ("Merged into", obj.merged_into)]
        rows = [
            (label, reverse("admin:helpdesk_ticket_change", args=[other.pk]), other.display_number)
            for label, other in linked
            if other is not None
        ]
        return format_html_join(", ", '{} <a href="{}">{}</a>', rows) if rows else "—"

    @display(description="First response")
    def sla_response_display(self, obj):
        warning = int(HelpdeskSettings.load().sla_warning_percent)
        return _clock_html(sla.response_clock(obj, timezone.now(), warning), obj.first_responded_at)

    @display(description="Resolution")
    def sla_resolution_display(self, obj):
        warning = int(HelpdeskSettings.load().sla_warning_percent)
        return _clock_html(sla.resolution_clock(obj, timezone.now(), warning))

    def save_model(self, request, obj, form, change):
        changes = {name: form.cleaned_data[name] for name in EDITABLE if name in form.changed_data}
        changed = tickets.update_ticket(obj, actor=request.user, **changes) if change else []
        obj.refresh_from_db()
        if changed:
            self.log_change(request, obj, f"Changed {', '.join(changed)}.")

    def save_related(self, request, form, formsets, change):
        """Nothing related is edited on the ticket page."""

    def log_change(self, request, obj, message):
        # ``save_model`` logs what really changed; Django's own call (with the form's message) would log it twice.
        if isinstance(message, str):
            super().log_change(request, obj, message)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        ticket = self.get_object(request, object_id)
        extra = dict(extra_context or {})
        if ticket is not None and self.has_view_permission(request, ticket):
            settings = HelpdeskSettings.load()
            if request.method == "GET":
                tickets.mark_read([ticket])
            extra.update(
                helpdesk_timeline=timeline.build(ticket, settings),
                helpdesk_note_url=reverse("admin:helpdesk_ticket_note", args=[ticket.pk]),
                helpdesk_shadow_mode=shadow.shadow_mode_on(settings),
                **self._reply_context(request, ticket, settings),
            )
        return super().change_view(request, object_id, form_url, extra)

    def _reply_context(self, request, ticket: Ticket, settings: HelpdeskSettings) -> dict:
        refusal = outbound.can_reply(ticket, settings)
        if refusal:
            return {"helpdesk_reply_refusal": refusal}
        templates = ResponseTemplate.objects.filter(is_active=True).annotate(
            same_category=Case(
                When(Q(category_id=ticket.category_id) & Q(category__isnull=False), then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        templates = list(templates.order_by("same_category", "order", "name"))
        chosen = _chosen_template(request.GET.get("template"), templates)
        requester = ticket.requester_email.lower()
        return {
            "helpdesk_reply_url": reverse("admin:helpdesk_ticket_reply", args=[ticket.pk]),
            "helpdesk_reply_to": ticket.requester_email,
            "helpdesk_reply_cc_suggestions": [item for item in ticket.participants or [] if item.lower() != requester],
            "helpdesk_reply_templates": templates,
            "helpdesk_reply_template": chosen,
            "helpdesk_reply_body": outbound.fill(chosen.body, ticket, agent=request.user) if chosen else "",
            "helpdesk_reply_statuses": REPLY_STATUS_CHOICES,
            "helpdesk_reply_max": outbound.REPLY_MAX_CHARS,
        }

    def get_urls(self):
        custom = [
            path(
                "<uuid:pk>/note/",
                self.admin_site.admin_view(views.note_view),
                name="helpdesk_ticket_note",
            ),
            path(
                "<uuid:pk>/reply/",
                self.admin_site.admin_view(views.reply_view),
                name="helpdesk_ticket_reply",
            ),
            path(
                "<uuid:pk>/attachments/<uuid:attachment_pk>/",
                self.admin_site.admin_view(views.attachment_view),
                name="helpdesk_ticket_attachment",
            ),
        ]
        return custom + super().get_urls()


def _chosen_template(value, templates):
    try:
        wanted = uuid.UUID(str(value or ""))
    except ValueError:
        return None
    return next((template for template in templates if template.pk == wanted), None)
