"""The ticket page: its read-only displays, saving, the change view and the page's own URLs and actions."""

from django.contrib import messages
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from unfold.decorators import action, display

from apps.core.services.email.inbound import LABELS

from ...models import HelpdeskSettings, Ticket
from ...services import sla, tickets
from ...services.sla.display import paused_left
from ...services.tickets import shadow
from . import timeline, views
from .actions import MOVE_SKIPPED
from .form import EDITABLE

# The page's "Not automated: move to the queue" (an Unfold submit-line action: a button beside Save).
MOVE_HERE = "move_to_queue_here"


def _no_sla(ticket: Ticket) -> str:
    """No SLA, and why when a person's ticket was imported too late for one (backfilled mail has no clock)."""
    if not ticket.backfilled or ticket.sla_started_at or ticket.is_automated_or_spam or not ticket.first_message_at:
        return "No SLA"
    late = max(0.0, (ticket.created_at - ticket.first_message_at).total_seconds())
    hours = max(1, round(late / 3600))
    after = f"{hours} h" if hours < 72 else f"{round(late / 86400)} days"
    return f"No SLA (backfilled: imported {after} after it arrived)"


def _clock_html(clock: sla.Clock, ticket: Ticket, met_at=None) -> str:
    if clock.state == "none":
        return _no_sla(ticket)
    if clock.state == "paused":
        # The due time moves on while the clock stands still: what is left of the target says more.
        due = f" — {paused_left(ticket)} left when it runs again"
    else:
        due = f" — due {timezone.localtime(clock.due):%b %d, %Y %H:%M}" if clock.due else ""
    met = (
        f", responded {timezone.localtime(met_at):%b %d %H:%M}" if met_at and clock.state in ("met", "breached") else ""
    )
    return format_html(
        '<span class="i2g-helpdesk-sla is-{}">{}</span>{}{}', clock.state.replace("_", "-"), clock.label, due, met
    )


def _saved(obj: Ticket) -> Ticket:
    """The ticket as saved: after a refused save the form has already written its values onto ``obj``."""
    saved = getattr(obj, "_helpdesk_saved", None)
    if saved is None:
        saved = Ticket.objects.filter(pk=obj.pk).first() or obj
        obj._helpdesk_saved = saved
    return saved


def _link(ticket: Ticket):
    return reverse("admin:helpdesk_ticket_change", args=[ticket.pk]), ticket.display_number


class TicketPageMixin:
    """The ticket-page section of ``TicketAdmin``."""

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
        if not obj.is_automated_or_spam:
            return label
        if obj.status == Ticket.Status.MERGED:
            return f"{label} — hidden from the default queue; it was merged, so it stays as it is."
        # The page's own button beside Save carries this name (so does the queue's bulk action).
        return (
            f'{label} — hidden from the default queue. If a person wrote it, use "{tickets.MOVE_TO_QUEUE}" beside '
            "Save at the bottom of this page."
        )

    @display(description="Flags")
    def flags_display(self, obj):
        flags = [str(flag).replace("_", " ") for flag in obj.flags or []]
        if obj.backfilled:
            flags.append("backfilled (imported late: no SLA and no acknowledgement)")
        return ", ".join(flags) or "—"

    @display(description="Linked tickets")
    def links_display(self, obj):
        rows = [("Related to", *_link(obj.related_ticket))] if obj.related_ticket_id else []
        if obj.merged_into_id:
            rows.append(("Merged into", *_link(obj.merged_into)))
        rows += [("Follow-up", *_link(other)) for other in obj.followed_by.order_by("number")[:20]]
        rows += [("Merged in", *_link(other)) for other in obj.merged_tickets.order_by("number")[:20]]
        return format_html_join(", ", '{} <a href="{}">{}</a>', rows) if rows else "—"

    @display(description="Resolved or closed at")
    def closed_display(self, obj):
        return timezone.localtime(obj.closed_at).strftime("%b %d, %Y %H:%M") if obj.closed_at else "—"

    @display(description="First response")
    def sla_response_display(self, obj):
        saved, warning = _saved(obj), int(HelpdeskSettings.load().sla_warning_percent)
        return _clock_html(sla.response_clock(saved, timezone.now(), warning), saved, saved.first_responded_at)

    @display(description="Resolution")
    def sla_resolution_display(self, obj):
        saved, warning = _saved(obj), int(HelpdeskSettings.load().sla_warning_percent)
        return _clock_html(sla.resolution_clock(saved, timezone.now(), warning), saved)

    def save_model(self, request, obj, form, change):
        # Only what this person edited (``TicketForm.edited``): a value changed by someone else since the page was
        # shown stays as it is now.
        edited = getattr(form, "edited", None)
        edited = form.changed_data if edited is None else edited
        changes = {name: form.cleaned_data[name] for name in EDITABLE if name in edited}
        changed = tickets.update_ticket(obj, actor=request.user, **changes) if change else []
        obj.refresh_from_db()
        obj._helpdesk_saved = None
        if changed:
            labels = [str(Ticket._meta.get_field(name).verbose_name) for name in changed]
            self.log_change(request, obj, f"Changed {', '.join(labels)}.")

    def save_related(self, request, form, formsets, change):
        """Nothing related is edited on the ticket page."""

    def log_change(self, request, obj, message):
        # ``save_model`` logs what really changed; Django's own call (with the form's message) would log it twice.
        if isinstance(message, str):
            super().log_change(request, obj, message)

    @action(description=tickets.MOVE_TO_QUEUE, icon="move_to_inbox")
    def move_to_queue_here(self, request, obj):
        """The queue action's move, for this ticket (what the form edited is saved first, as for any Unfold
        submit-line action); its message, and an admin-history entry when it moved."""
        started = timezone.now()
        count = tickets.move_to_queue([obj], actor=request.user)
        self._done(request, count, "moved to the queue", 1 - count, MOVE_SKIPPED)
        self._log(request, [obj], started, "Moved to the queue: not automated.")

    def response_change(self, request, obj):
        # Run here, after the save: ``save_model`` above never calls Unfold's, which would run it as well.
        if f"{self.opts.app_label}_{self.opts.model_name}_{MOVE_HERE}" in request.POST:
            self.move_to_queue_here(request, obj)
            context = {"preserved_filters": self.get_preserved_filters(request), "opts": self.opts}
            return HttpResponseRedirect(add_preserved_filters(context, request.path))
        return super().response_change(request, obj)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        ticket = self.get_object(request, object_id)
        if request.method == "POST" and ticket is not None and ticket.status == Ticket.Status.MERGED:
            # Merged while the page was open: its page is read-only now, so the save is refused with the reason.
            target = f" into {ticket.merged_into.display_number}" if ticket.merged_into_id else ""
            messages.error(
                request, f"{ticket.display_number} was merged{target} while you were editing: nothing was saved."
            )
            return HttpResponseRedirect(reverse("admin:helpdesk_ticket_change", args=[ticket.pk]))
        extra = dict(extra_context or {})
        if ticket is not None and self.has_view_permission(request, ticket):
            settings = HelpdeskSettings.load()
            if request.method == "GET":
                tickets.mark_read([ticket])
            extra.update(
                helpdesk_timeline=timeline.build(ticket, settings),
                helpdesk_settings=settings,  # the message cards name the SCL and BCL thresholds in effect
                helpdesk_note_url=reverse("admin:helpdesk_ticket_note", args=[ticket.pk]),
                helpdesk_shadow_mode=shadow.shadow_mode_on(settings),
                **views.reply_context(request, ticket, settings),
                **views.form_helpers(request, ticket),
            )
        return super().change_view(request, object_id, form_url, extra)

    def get_urls(self):
        custom = [
            path("<uuid:pk>/note/", self.admin_site.admin_view(views.note_view), name="helpdesk_ticket_note"),
            path("<uuid:pk>/reply/", self.admin_site.admin_view(views.reply_view), name="helpdesk_ticket_reply"),
            path(
                "<uuid:pk>/attachments/<uuid:attachment_pk>/",
                self.admin_site.admin_view(views.attachment_view),
                name="helpdesk_ticket_attachment",
            ),
        ]
        return custom + super().get_urls()
