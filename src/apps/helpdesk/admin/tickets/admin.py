"""Helpdesk → Queue: the ticket list and the ticket page.

The list opens on people's open tickets: automated mail and spam are hidden unless the Mail filter asks for them
(the sidebar's "Automated & spam"). The ticket page works a ticket ServiceNow style: status, impact and urgency (the
priority follows), category, assignment group and assignee, and the resolution code and notes (each change goes to
the ticket's audit trail; no typed confirmation, which would be noise on every status change). It shows the SLA
clocks, the timeline, the reply form (only while shadow mode is off) and the internal-note form. A merged ticket's
status is read-only, and the Status list has no "Merged": only a merge makes one. Merging and marking spam do need a
typed confirmation. A merge into automated mail or spam is refused before that confirmation (and again by the service
when it runs), and the "Automated & spam" view, where every ticket is one, offers no merge. Tickets are created only
from mail, and deleted only by retention or an I2G Master (behind the typed confirmation).
"""

from django.contrib import admin, messages

from apps.core.admin import BaseModelAdmin

from ...models import AssignmentGroup, Ticket
from ...services.tickets import shadow
from .actions import TicketActionsMixin
from .filters import (
    AssigneeFilter,
    GroupFilter,
    MailTypeFilter,
    PriorityFilter,
    SLAFilter,
    StatusViewFilter,
    UnreadFilter,
)
from .page import TicketPageMixin
from .queue import TicketQueueMixin


@admin.register(Ticket)
class TicketAdmin(TicketQueueMixin, TicketPageMixin, TicketActionsMixin, BaseModelAdmin):
    list_display = (
        "number_column",
        "subject_column",
        "requester_column",
        "status_column",
        "priority_column",
        "sla_column",
        "category",
        "group_column",
        "assignee_column",
        "last_activity_at",
        "message_count",
    )
    list_display_links = ("number_column", "subject_column")
    list_filter = (
        MailTypeFilter,
        StatusViewFilter,
        AssigneeFilter,
        GroupFilter,
        SLAFilter,
        UnreadFilter,
        PriorityFilter,
        "category",
    )
    list_select_related = ("category", "assignee", "assignment_group")
    search_fields = ("subject", "requester_email", "requester_name")
    search_help_text = "Number (1234 or I2G-#1234), subject, or the requester's address or name."
    ordering = ("-last_activity_at",)
    actions = (
        "assign_to_me",
        "unassign",
        "resolve_tickets",
        "close_tickets",
        "reopen_tickets",
        "mark_read",
        "mark_unread",
        "move_to_queue",
        "merge_tickets",
        "mark_spam",
    )
    actions_no_confirmation = (
        "assign_to_me",
        "unassign",
        "resolve_tickets",
        "close_tickets",
        "reopen_tickets",
        "mark_read",
        "mark_unread",
        "move_to_queue",
    )
    empty_value_display = "—"
    fieldsets = (
        (
            "Ticket",
            {
                "fields": (
                    "number_display",
                    "subject",
                    "status",
                    ("impact", "urgency"),
                    "priority",
                    "category",
                    ("assignment_group", "assignee"),
                    "links_display",
                )
            },
        ),
        ("SLA", {"fields": ("sla_response_display", "sla_resolution_display")}),
        (
            "Resolution",
            {
                "description": "A resolution code is needed to resolve or close the ticket; reopening clears it.",
                "fields": ("resolution_code", "resolution_notes", "resolved_at"),
            },
        ),
        ("Requester", {"fields": ("requester_display", "requester_member", "participants_display")}),
        (
            "Mail",
            {
                "classes": ("collapse",),
                "fields": (
                    "classification_display",
                    "flags_display",
                    "campaign",
                    "first_message_at",
                    "last_activity_at",
                    "closed_display",
                ),
            },
        ),
    )
    readonly_fields = (
        "number_display",
        "subject",
        "priority",
        "sla_response_display",
        "sla_resolution_display",
        "resolved_at",
        "requester_display",
        "requester_member",
        "participants_display",
        "classification_display",
        "flags_display",
        "campaign",
        "links_display",
        "first_message_at",
        "last_activity_at",
        "closed_display",
    )
    change_form_outer_after_template = "admin/helpdesk/ticket/timeline.html"
    list_before_template = "admin/helpdesk/ticket/shadow_notice.html"

    class Media:
        css = {"all": ("helpdesk/css/helpdesk.css",)}
        js = ("helpdesk/js/ticket-page.js", "helpdesk/js/ticket-form.js")

    # --- access ----------------------------------------------------------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        if request.GET.get(GroupFilter.parameter_name) == "mine" and request.method == "GET":
            if not AssignmentGroup.objects.filter(members=request.user).exists():
                messages.info(
                    request, "You are in no assignment group, so My Groups is empty: Helpdesk → Assignment Groups."
                )
        extra = {"helpdesk_shadow_mode": shadow.shadow_mode_on(), **(extra_context or {})}
        return super().changelist_view(request, extra)

    def has_add_permission(self, request):
        return False  # tickets come from mail

    def has_delete_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_superuser", False)) and super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        # A merged ticket is read-only (its messages and mail are on the ticket it was merged into).
        if obj is not None and obj.status == Ticket.Status.MERGED:
            return False
        return super().has_change_permission(request, obj)

    def _should_skip_confirmation(self, request):
        # Saving the ticket page needs no typed confirmation (it would be noise on every status change). Deleting a
        # ticket (I2G Master only; its messages, files and audit trail go with it) and the merge and spam actions
        # keep theirs, so the skip is limited to the change view.
        match = getattr(request, "resolver_match", None)
        if request.method == "POST" and getattr(match, "url_name", "") == f"{self.opts.app_label}_ticket_change":
            return True
        return super()._should_skip_confirmation(request)
