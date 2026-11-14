"""The queue's bulk actions: assign, close, reopen, mark read, move, merge, mark as spam."""

from django.contrib import messages
from unfold.decorators import action

from ...services import tickets
from .queue import Status


class TicketActionsMixin:
    """The actions section of ``TicketAdmin``."""

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

    @action(description="Merge into the oldest selected ticket (not automated mail or spam)")
    def merge_tickets(self, request, queryset):
        try:
            target = tickets.merge(list(queryset), actor=request.user)
        except tickets.MergeRefused as refused:
            messages.error(request, str(refused))
            return
        if target is None:
            messages.error(request, "Select at least two tickets that are not merged already.")
            return
        messages.success(request, f"Merged into {target.display_number}.")

    @action(description="Mark as spam")
    def mark_spam(self, request, queryset):
        self._done(request, tickets.mark_spam(list(queryset), actor=request.user), "marked as spam")
