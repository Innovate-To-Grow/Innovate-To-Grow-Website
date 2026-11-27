"""Helpdesk → Queue: the ticket list and the ticket page.

The list opens on people's open tickets: automated mail and spam are hidden unless the Mail filter asks for them
(the sidebar's "Automated & spam"); "Not automated: move to the queue" brings one back, from the list or beside Save
on its page. The ticket page works a ticket ServiceNow style: status, impact and urgency (the
priority follows), category, and the resolution code and notes (each change goes to the ticket's audit trail, with
who made it; no typed confirmation, which would be noise on every status change). It shows who replied last, the SLA
clocks, the timeline, the reply form (only while shadow mode is off) and the internal-note form. A merged ticket's
status is read-only, and the Status list has no "Merged": only a merge makes one. Merging and marking spam do need a
typed confirmation. A merge into automated mail or spam is refused before that confirmation (and again by the service
when it runs), and the "Automated & spam" view, where every ticket is one, offers no merge. Tickets are created only
from mail, and deleted only by retention or by an Admin behind the typed confirmation.

Tickets have no owner (I2G-HELPDESK-01): every Admin works every ticket, so there is no assignee, assignment group,
"Assigned to me" or "My groups". The list's "Last reply" column and the page's "Last reply" line say who answered the
requester last, and the reply form warns before sending when someone else replied since the page was opened. A
bookmark of a removed view (``?assignee=…``, ``?group=…``) is redirected to the list without it.
"""

from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect

from apps.core.admin import BaseModelAdmin

from ...models import Ticket
from ...services.tickets import shadow
from .actions import TicketActionsMixin
from .filters import MailTypeFilter, PriorityFilter, ReplyFilter, SLAFilter, StatusViewFilter, UnreadFilter
from .page import MOVE_HERE, TicketPageMixin
from .queue import TicketQueueMixin

# The list parameters of the views tickets had while they had an owner ("Assigned to me", "My groups", …).
REMOVED_PARAMETERS = ("assignee", "group")


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
        "last_reply_column",
        "last_activity_at",
        "message_count",
    )
    list_display_links = ("number_column", "subject_column")
    list_filter = (
        MailTypeFilter,
        StatusViewFilter,
        ReplyFilter,
        SLAFilter,
        UnreadFilter,
        PriorityFilter,
        "category",
    )
    list_select_related = ("category",)
    search_fields = ("subject", "requester_email", "requester_name")
    search_help_text = "Number (1234 or I2G-#1234), subject, or the requester's address or name."
    ordering = ("-last_activity_at",)
    actions = (
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
        "resolve_tickets",
        "close_tickets",
        "reopen_tickets",
        "mark_read",
        "mark_unread",
        "move_to_queue",
    )
    actions_submit_line = (MOVE_HERE,)  # the ticket page's own "Not automated: move to the queue"
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
                    "last_reply_display",
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
        "last_reply_display",
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
        if request.method == "GET" and any(name in request.GET for name in REMOVED_PARAMETERS):
            # An old bookmark of a view that is gone: the list without it, rather than Django's error page.
            kept = request.GET.copy()
            for name in REMOVED_PARAMETERS:
                kept.pop(name, None)
            query = kept.urlencode()
            return HttpResponseRedirect(f"{request.path}?{query}" if query else request.path)
        extra = {"helpdesk_shadow_mode": shadow.shadow_mode_on(), **(extra_context or {})}
        return super().changelist_view(request, extra)

    def has_add_permission(self, request):
        return False  # tickets come from mail

    def has_change_permission(self, request, obj=None):
        # A merged ticket is read-only (its messages and mail are on the ticket it was merged into).
        if obj is not None and obj.status == Ticket.Status.MERGED:
            return False
        return super().has_change_permission(request, obj)

    def get_actions_submit_line(self, request, object_id):
        # The page's move to the queue only where it moves something: automated mail or spam that is not merged.
        actions = super().get_actions_submit_line(request, object_id)
        try:
            ticket = Ticket.objects.only("status", "automated").filter(pk=unquote(str(object_id))).first()
        except (ValidationError, ValueError):
            ticket = None
        if ticket is not None and ticket.is_automated_or_spam and self.has_change_permission(request, ticket):
            return actions
        return [item for item in actions if not item.action_name.endswith(f"_{MOVE_HERE}")]

    def _should_skip_confirmation(self, request):
        # Saving the ticket page needs no typed confirmation (it would be noise on every status change). Deleting a
        # ticket (its messages, files and audit trail go with it) and the merge and spam actions keep theirs, so the
        # skip is limited to the change view.
        match = getattr(request, "resolver_match", None)
        if request.method == "POST" and getattr(match, "url_name", "") == f"{self.opts.app_label}_ticket_change":
            return True
        return super()._should_skip_confirmation(request)
