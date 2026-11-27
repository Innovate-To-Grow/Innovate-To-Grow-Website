"""The ticket page saves only what this person edited (``TicketForm.edited``): each editable field carries the value
the page showed in Django's hidden initial input.

- A field someone else changed since the page was shown keeps its new value.
- The same field changed by both: the save is refused, saying which field and what to do, and nothing changes.
- A form posted without the hidden inputs is judged against the row: what equals the row is no edit.
"""

from unittest.mock import patch

from django.contrib.admin.models import LogEntry

from ....models import Ticket, TicketCategory, TicketEvent
from ....services import tickets
from ...helpers.service import Status, new_ticket
from .support import PageCase, change_url

RELOAD = (
    "changed while you were editing this ticket (someone else, or a new message). Reload the page to see the ticket as "
    "it is now, then make your change again."
)


class TwoTabsTestCase(PageCase):
    """Two pages opened on the same ticket before either was saved."""

    def setUp(self):
        super().setUp()
        self.registration = TicketCategory.objects.create(name="Registration")
        self.parking = TicketCategory.objects.create(name="Parking")
        self.ticket = new_ticket(status=Status.OPEN)
        self.mine, self.theirs = self.shown(self.ticket), self.shown(self.ticket)

    def current(self) -> Ticket:
        return Ticket.objects.get(pk=self.ticket.pk)


class OtherPeoplesChangesTests(TwoTabsTestCase):
    def test_a_field_someone_else_changed_meanwhile_keeps_its_new_value(self):
        self.assertEqual(
            self.save(self.ticket, self.theirs, status=Status.PENDING_INTERNAL, category=self.registration).status_code,
            302,
        )

        response = self.save(self.ticket, self.mine, impact="1")

        self.assertEqual(response.status_code, 302)
        ticket = self.current()
        self.assertEqual(
            (ticket.status, ticket.category, ticket.impact, ticket.priority),
            (Status.PENDING_INTERNAL, self.registration, 1, "high"),  # theirs, and mine (impact 1 × urgency 2 is High)
        )

    def test_the_same_field_changed_by_both_is_refused_and_nothing_changes(self):
        self.save(self.ticket, self.theirs, status=Status.PENDING_INTERNAL)
        before, events = self.current(), TicketEvent.objects.count()

        response = self.save(self.ticket, self.mine, status=Status.PENDING_CUSTOMER, impact="1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.form(response).non_field_errors(), [f"Status {RELOAD}"])
        self.assertContains(response, f"Status {RELOAD}")
        ticket = self.current()
        self.assertEqual((ticket.status, ticket.impact, ticket.priority), (before.status, 2, before.priority))
        self.assertEqual(TicketEvent.objects.count(), events)

    def test_every_field_both_changed_is_named(self):
        self.save(self.ticket, self.theirs, status=Status.PENDING_INTERNAL, category=self.registration)

        response = self.save(self.ticket, self.mine, status=Status.PENDING_CUSTOMER, category=self.parking)

        self.assertEqual(self.form(response).non_field_errors(), [f"Status, Category {RELOAD}"])
        self.assertEqual((self.current().status, self.current().category), (Status.PENDING_INTERNAL, self.registration))

    def test_both_making_the_same_change_is_no_conflict(self):
        self.save(self.ticket, self.theirs, status=Status.PENDING_INTERNAL)

        response = self.save(self.ticket, self.mine, status=Status.PENDING_INTERNAL, urgency="1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual((self.current().status, self.current().urgency), (Status.PENDING_INTERNAL, 1))
        self.assertEqual(self.ticket.events.filter(kind=TicketEvent.Kind.STATUS).count(), 1)

    def test_a_change_the_ingest_made_meanwhile_is_kept_too(self):
        waiting = new_ticket(status=Status.PENDING_CUSTOMER)
        shown = self.shown(waiting)
        # The requester answers while the page is open: the ingest moves the ticket back to In progress.
        Ticket.objects.filter(pk=waiting.pk).update(status=Status.OPEN)

        response = self.save(waiting, shown, urgency="3")

        self.assertEqual(response.status_code, 302)
        waiting.refresh_from_db()
        self.assertEqual((waiting.status, waiting.urgency), (Status.OPEN, 3))


class EditedFieldsTests(PageCase):
    def setUp(self):
        super().setUp()
        self.ticket = new_ticket(status=Status.OPEN)

    def post(self, data):
        with patch.object(tickets, "update_ticket", wraps=tickets.update_ticket) as update:
            response = self.client.post(change_url(self.ticket), data)
        self.assertEqual(response.status_code, 302)
        update.assert_called_once()
        return update.call_args.kwargs

    def test_only_the_edited_fields_reach_update_ticket(self):
        changes = self.post({**self.shown(self.ticket), "urgency": "1", "resolution_notes": "Called back."})

        self.assertEqual(set(changes), {"actor", "urgency", "resolution_notes"})
        self.assertEqual((changes["urgency"], changes["resolution_notes"]), (1, "Called back."))
        self.assertEqual(
            LogEntry.objects.get(object_id=str(self.ticket.pk)).change_message,
            "Changed urgency, priority, resolution notes.",
        )

    def test_posting_the_page_unchanged_changes_and_logs_nothing(self):
        changes = self.post(self.shown(self.ticket))

        self.assertEqual(set(changes), {"actor"})
        self.assertFalse(self.ticket.events.exists())
        self.assertFalse(LogEntry.objects.filter(object_id=str(self.ticket.pk)).exists())

    def test_a_form_without_the_hidden_initial_values_is_judged_against_the_row(self):
        data = {name: value for name, value in self.shown(self.ticket).items() if not name.startswith("initial-")}
        data["status"] = Status.PENDING_CUSTOMER

        changes = self.post(data)

        self.assertEqual(changes["status"], Status.PENDING_CUSTOMER)
        self.assertEqual(set(changes), {"actor", "status"})  # the rest equals the row: no edit
        self.assertEqual(Ticket.objects.get(pk=self.ticket.pk).status, Status.PENDING_CUSTOMER)
