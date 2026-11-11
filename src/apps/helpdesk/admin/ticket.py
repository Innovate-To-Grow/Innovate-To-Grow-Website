"""Helpdesk → Queue: the ticket list and the ticket page.

The list opens on people's open tickets: automated mail and spam are hidden unless the Mail filter asks for them
(the sidebar's "Automated & spam"). The ticket page edits status, priority, category and assignee (each change goes
to the ticket's audit trail; no typed confirmation, which would be noise on every status change) and shows the
timeline with the note form below the form. Merging and marking spam do need a typed confirmation. Tickets are
created only from mail, and deleted only by retention or an I2G Master (behind the typed confirmation). Nothing here
sends anything.
"""

from django.contrib import admin, messages
from django.db.models import Count, Q
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from unfold.decorators import action, display

from apps.core.admin import BaseModelAdmin
from apps.core.services.email.inbound import LABELS

from ..models import HelpdeskSettings, Ticket, TicketMessage
from ..services import numbering, shadow, tickets
from . import timeline, views
from .filters import AssigneeFilter, MailTypeFilter, StatusViewFilter, UnreadFilter

Status = Ticket.Status
STATUS_COLORS = {
    Status.NEW: "info",
    Status.OPEN: "warning",
    Status.PENDING_CUSTOMER: "info",
    Status.PENDING_INTERNAL: "info",
    Status.RESOLVED: "success",
    Status.CLOSED: "success",
    Status.MERGED: "info",
    Status.SPAM: "danger",
}
PRIORITY_COLORS = {"low": "info", "normal": "info", "high": "warning", "urgent": "danger"}
EDITABLE = ("status", "priority", "category", "assignee")


@admin.register(Ticket)
class TicketAdmin(BaseModelAdmin):
    list_display = (
        "number_column",
        "subject_column",
        "requester_column",
        "status_column",
        "priority_column",
        "category",
        "assignee",
        "last_activity_at",
        "message_count",
    )
    list_display_links = ("number_column", "subject_column")
    list_filter = (MailTypeFilter, StatusViewFilter, AssigneeFilter, UnreadFilter, "priority", "category")
    list_select_related = ("category", "assignee")
    search_fields = ("subject", "requester_email", "requester_name")
    search_help_text = "Number (1234 or I2G-#1234), subject, or the requester's address or name."
    ordering = ("-last_activity_at",)
    actions = (
        "assign_to_me",
        "unassign",
        "close_tickets",
        "reopen_tickets",
        "mark_read",
        "move_to_queue",
        "merge_tickets",
        "mark_spam",
    )
    actions_no_confirmation = (
        "assign_to_me",
        "unassign",
        "close_tickets",
        "reopen_tickets",
        "mark_read",
        "move_to_queue",
    )
    fieldsets = (
        ("Ticket", {"fields": ("number_display", "subject", "status", "priority", "category", "assignee")}),
        ("Requester", {"fields": ("requester_display", "requester_member", "participants_display")}),
        (
            "Mail",
            {
                "fields": (
                    "classification_display",
                    "flags_display",
                    "campaign",
                    "links_display",
                    "first_message_at",
                    "last_activity_at",
                    "closed_at",
                )
            },
        ),
    )
    readonly_fields = (
        "number_display",
        "subject",
        "requester_display",
        "requester_member",
        "participants_display",
        "classification_display",
        "flags_display",
        "campaign",
        "links_display",
        "first_message_at",
        "last_activity_at",
        "closed_at",
    )
    change_form_outer_after_template = "admin/helpdesk/ticket/timeline.html"
    list_before_template = "admin/helpdesk/ticket/shadow_notice.html"

    class Media:
        css = {"all": ("helpdesk/css/helpdesk.css",)}

    # --- access ----------------------------------------------------------------------------------------------------

    def has_add_permission(self, request):
        return False  # tickets come from mail

    def has_delete_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_superuser", False)) and super().has_delete_permission(request, obj)

    def _should_skip_confirmation(self, request):
        # Saving the ticket page needs no typed confirmation (it would be noise on every status change). Deleting a
        # ticket (I2G Master only; its messages, files and audit trail go with it) and the merge and spam actions
        # keep theirs, so the skip is limited to the change view.
        match = getattr(request, "resolver_match", None)
        if request.method == "POST" and getattr(match, "url_name", "") == f"{self.opts.app_label}_ticket_change":
            return True
        return super()._should_skip_confirmation(request)

    def get_action_confirmation_word(self, action_name):
        return {"merge_tickets": "MERGE", "mark_spam": "SPAM"}.get(
            action_name, super().get_action_confirmation_word(action_name)
        )

    # --- list ------------------------------------------------------------------------------------------------------

    def get_queryset(self, request):
        inbound = Q(messages__kind__in=TicketMessage.INBOUND_KINDS)
        return super().get_queryset(request).annotate(inbound_count=Count("messages", filter=inbound))

    def get_search_results(self, request, queryset, search_term):
        """The usual search, plus the ticket whose number was typed ("1234", "#1234" or "I2G-#1234")."""
        results, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        number = numbering.parse_number(search_term)
        if number is not None:
            results = results | queryset.filter(number=number)
        return results, may_have_duplicates

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        assignee = form.base_fields.get("assignee")
        if assignee is not None:
            # Staff who may work tickets, and whoever holds this one now (so the page still saves after a grant ends).
            allowed = {member.pk for member in tickets.helpdesk_staff()}
            if obj is not None and obj.assignee_id:
                allowed.add(obj.assignee_id)
            assignee.queryset = assignee.queryset.filter(pk__in=allowed)
        return form

    @display(description="Ticket", ordering="number")
    def number_column(self, obj):
        return obj.display_number

    @display(description="Subject")
    def subject_column(self, obj):
        dot = format_html('<span class="i2g-helpdesk-unread" title="Unread">●</span> ') if obj.unread else ""
        return format_html("{}{}", dot, obj.subject or "(no subject)")

    @display(description="Requester", ordering="requester_email")
    def requester_column(self, obj):
        member = " (member)" if obj.requester_member_id else ""
        return f"{obj.requester_name or obj.requester_email}{member}"

    @display(description="Status", label=STATUS_COLORS, ordering="status")
    def status_column(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Priority", label=PRIORITY_COLORS, ordering="priority")
    def priority_column(self, obj):
        return obj.priority, obj.get_priority_display()

    @display(description="Messages", ordering="inbound_count")
    def message_count(self, obj):
        return getattr(obj, "inbound_count", 0)

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
            )
        return super().change_view(request, object_id, form_url, extra)

    def get_urls(self):
        custom = [
            path(
                "<uuid:pk>/note/",
                self.admin_site.admin_view(views.note_view),
                name="helpdesk_ticket_note",
            ),
            path(
                "<uuid:pk>/attachments/<uuid:attachment_pk>/",
                self.admin_site.admin_view(views.attachment_view),
                name="helpdesk_ticket_attachment",
            ),
        ]
        return custom + super().get_urls()

    # --- actions ---------------------------------------------------------------------------------------------------

    def _done(self, request, count: int, what: str) -> None:
        messages.success(request, f"{count} ticket{'s' if count != 1 else ''} {what}.")

    @action(description="Assign to me")
    def assign_to_me(self, request, queryset):
        self._done(request, tickets.assign(list(queryset), request.user, actor=request.user), "assigned to you")

    @action(description="Unassign")
    def unassign(self, request, queryset):
        self._done(request, tickets.assign(list(queryset), None, actor=request.user), "unassigned")

    @action(description="Close")
    def close_tickets(self, request, queryset):
        self._done(request, tickets.set_status(list(queryset), Status.CLOSED, actor=request.user), "closed")

    @action(description="Reopen")
    def reopen_tickets(self, request, queryset):
        reopenable = list(queryset.exclude(status=Status.MERGED).exclude(automated=True))
        self._done(request, tickets.set_status(reopenable, Status.OPEN, actor=request.user), "reopened")

    @action(description="Mark as read")
    def mark_read(self, request, queryset):
        self._done(request, tickets.mark_read(list(queryset)), "marked as read")

    @action(description="Not automated: move to the queue")
    def move_to_queue(self, request, queryset):
        self._done(request, tickets.move_to_queue(list(queryset), actor=request.user), "moved to the queue")

    @action(description="Merge into the oldest selected ticket")
    def merge_tickets(self, request, queryset):
        target = tickets.merge(list(queryset), actor=request.user)
        if target is None:
            messages.error(request, "Select at least two tickets that are not merged already.")
            return
        messages.success(request, f"Merged into {target.display_number}.")

    @action(description="Mark as spam")
    def mark_spam(self, request, queryset):
        self._done(request, tickets.mark_spam(list(queryset), actor=request.user), "marked as spam")
