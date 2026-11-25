"""Helpdesk → Queue: the ticket list and the ticket page.

The list opens on people's open tickets: automated mail and spam are hidden unless the Mail filter asks for them
(the sidebar's "Automated & spam"). The ticket page edits status, priority, category and assignee (each change goes
to the ticket's audit trail; no typed confirmation, which would be noise on every status change) and shows the
timeline with the note form below the form. A merged ticket's status is read-only, and the Status list has no
"Merged": only a merge makes one. Merging and marking spam do need a typed confirmation. A merge into
automated mail or spam is refused before that confirmation (and again by the service when it runs), and the
"Automated & spam" view, where every ticket is one, offers no merge. Tickets are created only from mail, and deleted
only by retention or by an Admin behind the typed confirmation. Nothing here sends anything.
"""

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.http import HttpResponseRedirect

from apps.core.admin import BaseModelAdmin

from ...models import Ticket
from ...services import tickets
from .actions import TicketActionsMixin
from .filters import AssigneeFilter, MailTypeFilter, StatusViewFilter, UnreadFilter
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

    def _should_skip_confirmation(self, request):
        # Saving the ticket page needs no typed confirmation (it would be noise on every status change). Deleting a
        # ticket (its messages, files and audit trail go with it) and the merge and spam actions keep theirs, so the
        # skip is limited to the change view.
        match = getattr(request, "resolver_match", None)
        if request.method == "POST" and getattr(match, "url_name", "") == f"{self.opts.app_label}_ticket_change":
            return True
        return super()._should_skip_confirmation(request)

    def get_action_confirmation_word(self, action_name):
        return {"merge_tickets": "MERGE", "mark_spam": "SPAM"}.get(
            action_name, super().get_action_confirmation_word(action_name)
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if request.GET.get(MailTypeFilter.parameter_name) == "automated":
            actions.pop("merge_tickets", None)  # every ticket listed is automated mail or spam: nothing to merge into
        return actions

    def response_action(self, request, queryset):
        # A merge the service would refuse is refused here, before staff are asked to type the confirmation word.
        refusal = self._merge_refusal(request, queryset)
        if refusal:
            messages.error(request, refusal)
            return HttpResponseRedirect(request.get_full_path())
        return super().response_action(request, queryset)

    def _merge_refusal(self, request, queryset) -> str:
        action_form = self._bound_action_form(request)
        if action_form is None or not action_form.is_valid() or action_form.cleaned_data["action"] != "merge_tickets":
            return ""
        if not action_form.cleaned_data["select_across"]:
            queryset = queryset.filter(pk__in=request.POST.getlist(helpers.ACTION_CHECKBOX_NAME))
        return tickets.merge_refusal(list(queryset))
