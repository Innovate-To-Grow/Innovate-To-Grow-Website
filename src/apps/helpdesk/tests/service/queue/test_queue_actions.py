"""Helpdesk → Queue bulk actions that follow the ticket page's rules.

- Resolve… asks for one resolution code (and notes) on a page of its own, then resolves people's open tickets only.
- Close takes resolved tickets only; Reopen resolved or closed people's tickets only, clearing their resolution.
- Mark as unread. Tickets have no owner (I2G-HELPDESK-01): "Assign to me" and "Unassign" are gone, and a list page
  an earlier release rendered that posts them changes nothing.
- Each ticket an action changed, and only those, gets an admin-history entry.
"""

from django.contrib import messages
from django.contrib.messages import get_messages

from ....models import Ticket
from ....services.tickets import MOVE_TO_QUEUE
from ...helpers import make_admin
from ...helpers.service import Status, new_ticket
from .support import QueueCase, history

MOVE = '"Not automated: move to the queue"'


def current(*selected) -> list[tuple]:
    return [Ticket.objects.values_list("status", "resolution_code").get(pk=item.pk) for item in selected]


class ResolveActionTests(QueueCase):
    def setUp(self):
        super().setUp()
        self.open = new_ticket(subject="Parking", status=Status.OPEN)
        self.new = new_ticket(subject="Badges")
        self.automated = new_ticket(subject="Automatic reply", automated=True, classification="auto_reply")
        self.closed = new_ticket(subject="Lost badge", status=Status.CLOSED, resolution_code="duplicate")
        self.spam = new_ticket(subject="You have won", status=Status.SPAM, classification="spam")
        self.chosen = (self.open, self.new, self.automated, self.closed, self.spam)

    def test_the_action_first_asks_for_the_code_on_a_page_naming_the_tickets(self):
        before = current(*self.chosen)

        response = self.act("resolve_tickets", *self.chosen, follow=False)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/helpdesk/ticket/resolve.html")
        self.assertFalse(response.context["form"].is_bound)
        for ticket in self.chosen:
            self.assertContains(response, f"{ticket.display_number}: {ticket.subject} — {ticket.get_status_display()}")
            self.assertContains(
                response, f'<input type="hidden" name="_selected_action" value="{ticket.pk}">', html=True
            )
        self.assertContains(response, '<input type="hidden" name="apply" value="1">', html=True)
        self.assertContains(response, "Resolve 5 tickets")
        self.assertContains(response, 'href="/admin/helpdesk/ticket/?mail=all&amp;status=any"')  # Cancel: the list
        self.assertEqual(current(*self.chosen), before)

    def test_applying_without_a_code_shows_the_page_again_with_the_error(self):
        before = current(*self.chosen)

        response = self.act("resolve_tickets", *self.chosen, follow=False, apply="1", code="", notes="Answered.")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].errors["code"], ["This field is required."])
        self.assertContains(response, "This field is required.")
        self.assertEqual(current(*self.chosen), before)

    def test_a_code_resolves_peoples_open_tickets_only_and_reports_the_rest(self):
        response = self.act("resolve_tickets", *self.chosen, apply="1", code="solved", notes="Answered by phone.")

        self.assertEqual(
            self.messages(response),
            ["2 tickets resolved. 3 left as they were: only people's open tickets are resolved here."],
        )
        self.assertEqual(
            current(*self.chosen),
            [
                (Status.RESOLVED, "solved"),
                (Status.RESOLVED, "solved"),
                (Status.NEW, ""),
                (Status.CLOSED, "duplicate"),
                (Status.SPAM, ""),
            ],
        )
        self.open.refresh_from_db()
        self.assertEqual(self.open.resolution_notes, "Answered by phone.")
        self.assertEqual(history(self.open), ["Resolved: Solved (bulk action)."])
        self.assertEqual([history(ticket) for ticket in (self.automated, self.closed, self.spam)], [[], [], []])

    def test_notes_count_each_line_break_once_as_on_the_ticket_page(self):
        notes = "\r\n".join(["x" * 199] * 99 + ["x" * 200])  # 20,000 characters with "\n"; 20,099 as posted

        self.act("resolve_tickets", self.open, apply="1", code="solved", notes=notes)

        self.open.refresh_from_db()
        self.assertEqual((self.open.status, len(self.open.resolution_notes)), (Status.RESOLVED, 20000))


class CloseAndReopenTests(QueueCase):
    def setUp(self):
        super().setUp()
        self.resolved = new_ticket(subject="resolved", status=Status.RESOLVED, resolution_code="solved")
        self.closed = new_ticket(
            subject="closed", status=Status.CLOSED, resolution_code="workaround", resolution_notes="Use the side door."
        )
        self.open = new_ticket(subject="open", status=Status.OPEN)
        self.spam = new_ticket(subject="spam", status=Status.SPAM, classification="spam")
        self.automated = new_ticket(
            subject="automated", automated=True, status=Status.RESOLVED, resolution_code="solved"
        )
        self.merged = new_ticket(subject="merged", status=Status.MERGED, merged_into=self.open)

    def test_close_takes_resolved_peoples_tickets_only(self):
        response = self.act("close_tickets", self.resolved, self.open, self.automated)

        why = "only resolved tickets are closed here; resolve the others first (they need a resolution code)."
        moved = f' Automated mail and spam go back with "{MOVE_TO_QUEUE}"; a merged ticket stays as it is.'
        self.assertEqual(self.messages(response), [f"1 ticket closed. 2 left as they were: {why}{moved}"])
        self.assertEqual(
            self.messages(self.act("close_tickets", self.open)), [f"0 tickets closed. 1 left as it was: {why}"]
        )
        self.assertEqual(
            current(self.resolved, self.open, self.automated),
            [(Status.CLOSED, "solved"), (Status.OPEN, ""), (Status.RESOLVED, "solved")],
        )
        self.assertEqual([history(self.resolved), history(self.open)], [["Closed (bulk action)."], []])

    def test_reopen_takes_resolved_or_closed_peoples_tickets_and_clears_their_resolution(self):
        chosen = (self.resolved, self.closed, self.open, self.spam, self.automated, self.merged)

        response = self.act("reopen_tickets", *chosen)

        why = f"only resolved or closed people's tickets are reopened; for automated mail or spam use {MOVE}."
        self.assertEqual(self.messages(response), [f"2 tickets reopened. 4 left as they were: {why}"])
        self.assertEqual(
            current(*chosen),
            [
                (Status.OPEN, ""),
                (Status.OPEN, ""),
                (Status.OPEN, ""),
                (Status.SPAM, ""),
                (Status.RESOLVED, "solved"),
                (Status.MERGED, ""),
            ],
        )
        self.closed.refresh_from_db()
        self.assertEqual((self.closed.resolution_notes, self.closed.closed_at), ("", None))
        self.assertEqual([history(ticket) for ticket in chosen[:3]], [["Reopened (bulk action)."]] * 2 + [[]])
        self.assertEqual(self.open.events.count(), 0)  # it was open already: untouched


class ReadAndRetiredActionTests(QueueCase):
    def levels(self, response) -> list[str]:
        return [message.level for message in get_messages(response.wsgi_request)]

    def test_the_retired_assignment_actions_change_nothing(self):
        kim = make_admin(email="kim@example.com")
        held = new_ticket(subject="held", assignee=kim)

        for action in ("assign_to_me", "unassign"):
            with self.subTest(action):
                response = self.act(action, held)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.levels(response), [messages.WARNING])  # Django: no such action
                self.assertEqual(Ticket.objects.get(pk=held.pk).assignee, kim)
        self.assertEqual(history(held), [])

    def test_mark_as_unread(self):
        read, unread = new_ticket(subject="read"), new_ticket(subject="unread", unread=True)

        response = self.act("mark_unread", read, unread)

        self.assertEqual(self.messages(response), ["1 ticket marked as unread."])
        self.assertEqual([Ticket.objects.get(pk=item.pk).unread for item in (read, unread)], [True, True])
        self.assertEqual(history(read), [])  # a read mark is no field change

    def test_history_only_on_the_tickets_an_action_changed(self):
        unread = new_ticket(subject="unread", unread=True)
        nobodys = new_ticket(subject="nobody's")
        automated = new_ticket(subject="automated", automated=True, status=Status.CLOSED, classification="bounce")

        self.act("mark_read", unread, nobodys)
        self.act("move_to_queue", automated, nobodys)

        self.assertEqual(history(unread), [])  # a read mark is no field change
        self.assertEqual(history(automated), ["Moved to the queue: not automated (bulk action)."])
        self.assertEqual(history(nobodys), [])
