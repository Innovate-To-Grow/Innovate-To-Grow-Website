"""The queue's bulk actions: resolve (with a resolution code), close, reopen, read marks, move, merge, spam.

Tickets have no owner (I2G-HELPDESK-01), so there is nothing to assign. The actions go through the ticket services,
so they follow the ticket page's rules: a resolution code to resolve (asked on a page of its own), closing only what is resolved, reopening only what is
resolved or closed, and never Close or Reopen on automated mail or spam (that is "Not automated: move to the queue").
Each changed ticket gets an admin-history entry besides its timeline.
"""

from django import forms
from django.contrib import messages
from django.contrib.admin import helpers
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils import timezone
from unfold.decorators import action

from ...models import Ticket
from ...services import tickets
from ...services.tickets.changes import RESOLUTION_NOTES_MAX_CHARS
from ...services.tickets.merging import queued_replies
from ..intake.sending import LFTextField
from .filters import MailTypeFilter

# Why "Not automated: move to the queue" left a ticket as it was (the queue's action and the ticket page's).
MOVE_SKIPPED = "only automated mail and spam are moved (a merged ticket never)."


class ResolveForm(forms.Form):
    code = forms.ChoiceField(label="Resolution code", choices=[("", "---------"), *Ticket.ResolutionCode.choices])
    # A line break counts once, as on the ticket page (the browser posts CRLF).
    notes = LFTextField(
        label="Resolution notes",
        required=False,
        max_length=RESOLUTION_NOTES_MAX_CHARS,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": RESOLUTION_NOTES_MAX_CHARS}),
    )


class TicketActionsMixin:
    """The actions section of ``TicketAdmin``: the actions, their typed-confirmation words, and the refusals and
    notes shown before a confirmation."""

    def _done(self, request, count: int, what: str, skipped: int = 0, why: str = "") -> None:
        text = f"{count} ticket{'s' if count != 1 else ''} {what}."
        if skipped:
            text += f" {skipped} left as {'they were' if skipped != 1 else 'it was'}: {why}"
        (messages.success if count or not skipped else messages.warning)(request, text)

    def _log(self, request, chosen, started, message: str) -> None:
        """An admin-history entry on each ticket the action changed (its row was updated since ``started``)."""
        for ticket in Ticket.objects.filter(pk__in=[item.pk for item in chosen], updated_at__gte=started):
            self.log_change(request, ticket, message)

    @action(description="Resolve… (with a resolution code)")
    def resolve_tickets(self, request, queryset):
        chosen, started = list(queryset), timezone.now()
        form = ResolveForm(request.POST if "apply" in request.POST else None)
        if form.is_bound and form.is_valid():
            code, notes = form.cleaned_data["code"], form.cleaned_data["notes"]
            count = tickets.resolve(chosen, actor=request.user, code=code, notes=notes)
            why = "only people's open tickets are resolved here."
            self._done(request, count, "resolved", len(chosen) - count, why)
            self._log(request, chosen, started, f"Resolved: {Ticket.ResolutionCode(code).label} (bulk action).")
            return None
        context = {
            **self.admin_site.each_context(request),
            "title": "Resolve tickets",
            "opts": self.opts,
            "form": form,
            "tickets": chosen,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "select_across": request.POST.get("select_across", "0"),
        }
        return TemplateResponse(request, "admin/helpdesk/ticket/resolve.html", context)

    @action(description="Close (resolved tickets)")
    def close_tickets(self, request, queryset):
        chosen, started = list(queryset), timezone.now()
        count = tickets.close(chosen, actor=request.user)
        why = "only resolved tickets are closed here; resolve the others first (they need a resolution code)."
        if any(ticket.is_automated_or_spam or ticket.status == Ticket.Status.MERGED for ticket in chosen):
            why += f' Automated mail and spam go back with "{tickets.MOVE_TO_QUEUE}"; a merged ticket stays as it is.'
        self._done(request, count, "closed", len(chosen) - count, why)
        self._log(request, chosen, started, "Closed (bulk action).")

    @action(description="Reopen (resolved or closed tickets)")
    def reopen_tickets(self, request, queryset):
        chosen, started = list(queryset), timezone.now()
        count = tickets.reopen(chosen, actor=request.user)
        why = f'only resolved or closed people\'s tickets are reopened; for automated mail or spam use "{tickets.MOVE_TO_QUEUE}".'
        self._done(request, count, "reopened", len(chosen) - count, why)
        self._log(request, chosen, started, "Reopened (bulk action).")

    @action(description="Mark as read")
    def mark_read(self, request, queryset):
        self._done(request, tickets.mark_read(list(queryset)), "marked as read")

    @action(description="Mark as unread")
    def mark_unread(self, request, queryset):
        self._done(request, tickets.mark_unread(list(queryset)), "marked as unread")

    @action(description="Not automated: move to the queue")
    def move_to_queue(self, request, queryset):
        chosen, started = list(queryset), timezone.now()
        count = tickets.move_to_queue(chosen, actor=request.user)
        self._done(request, count, "moved to the queue", len(chosen) - count, MOVE_SKIPPED)
        self._log(request, chosen, started, "Moved to the queue: not automated (bulk action).")

    @action(description="Merge into the oldest selected ticket (not automated mail or spam)")
    def merge_tickets(self, request, queryset):
        chosen, started = list(queryset), timezone.now()
        try:
            target = tickets.merge(chosen, actor=request.user)
        except tickets.MergeRefused as refused:
            messages.error(request, str(refused))
            return
        if target is None:
            messages.error(request, "Select at least two tickets that are not merged already.")
            return
        messages.success(request, f"Merged into {target.display_number}.")
        self._log(request, chosen, started, f"Merged into {target.display_number} (bulk action).")

    @action(description="Mark as spam")
    def mark_spam(self, request, queryset):
        chosen, started = list(queryset), timezone.now()
        count = tickets.mark_spam(chosen, actor=request.user)
        self._done(request, count, "marked as spam", len(chosen) - count, "they are spam or merged already.")
        self._log(request, chosen, started, "Marked as spam (bulk action).")

    def get_action_confirmation_word(self, action_name):
        return {"merge_tickets": "MERGE", "mark_spam": "SPAM"}.get(
            action_name, super().get_action_confirmation_word(action_name)
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if request.GET.get(MailTypeFilter.parameter_name) == "automated":
            # Every ticket listed is automated mail or spam: nothing to merge into, resolve, close or reopen there
            # (a person's message goes back with "Not automated: move to the queue").
            for name in ("merge_tickets", "resolve_tickets", "close_tickets", "reopen_tickets"):
                actions.pop(name, None)
        return actions

    def response_action(self, request, queryset):
        # A merge the service would refuse is refused here, before staff are asked to type the confirmation word; the
        # confirmation page then names the tickets (and, for a merge, the one they go into).
        chosen = self._chosen(request, queryset, ("merge_tickets", "mark_spam"))
        if chosen is not None:
            action_name, selected = chosen
            refusal = tickets.merge_refusal(selected) if action_name == "merge_tickets" else ""
            if action_name == "merge_tickets" and not refusal and len(self._unmerged(selected)) < 2:
                refusal = "Select at least two tickets that are not merged already."
            if action_name == "mark_spam" and all(ticket.status in ("spam", "merged") for ticket in selected):
                refusal = "Nothing to mark: the selected tickets are spam or merged already."
            if refusal:
                messages.error(request, refusal)
                return HttpResponseRedirect(request.get_full_path())
            if not self.action_confirmation_off(request):
                messages.info(request, self._confirmation_note(action_name, selected))
        return super().response_action(request, queryset)

    def _chosen(self, request, queryset, names):
        action_form = self._bound_action_form(request)
        if action_form is None or not action_form.is_valid() or action_form.cleaned_data["action"] not in names:
            return None
        if not action_form.cleaned_data["select_across"]:
            queryset = queryset.filter(pk__in=request.POST.getlist(helpers.ACTION_CHECKBOX_NAME))
        return action_form.cleaned_data["action"], list(queryset.order_by("number"))

    @staticmethod
    def _unmerged(selected):
        return [ticket for ticket in selected if ticket.status != Ticket.Status.MERGED]

    def _confirmation_note(self, action_name: str, selected) -> str:
        numbers = ", ".join(ticket.display_number for ticket in selected[:20])
        more = f" and {len(selected) - 20} more" if len(selected) > 20 else ""
        if action_name == "merge_tickets":
            target, *sources = self._unmerged(selected)
            waiting = [s.display_number for s in sources if queued_replies(s).filter(automatic=False).exists()]
            stopped = (
                f" A reply queued on {', '.join(waiting)} will not be sent: write it again there." if waiting else ""
            )
            return f"Merging {numbers}{more} into {target.display_number} (the oldest).{stopped}"
        return f"Marking as spam: {numbers}{more}."
