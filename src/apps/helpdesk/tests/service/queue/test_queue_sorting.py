"""Helpdesk → Queue sort orders and the ticket-number search.

- Priority sorts by severity and Status by the ticket's life, not alphabetically by their stored values; SLA by the
  due time of the clock the column shows (tickets without a clock last); Requester by name, else address; Assigned to
  by first name; Subject sorts too.
- A ticket number typed in the search ("1234", "#1234", "I2G-#1234") finds that ticket whatever the view's filters
  (closed, automated mail) and lists it first.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.utils import timezone

from ....models import Ticket
from ...helpers import make_admin
from ...helpers.service import Status, clocked_ticket, new_ticket
from .support import QueueCase

HOUR = timedelta(hours=1)
ALL = "mail=all&status=any"
LIFE = ["new", "open", "pending_customer", "pending_internal", "resolved", "closed", "merged", "spam"]


class SortTests(QueueCase):
    def by(self, column, descending=False) -> list[str]:
        """The subjects in the order of ``column`` (clicked once, or twice for ``descending``), every ticket listed."""
        index = self.get(ALL).context["cl"].list_display.index(column)
        return self.listed(f"{ALL}&o={'-' if descending else ''}{index}")

    def test_priority_sorts_by_severity(self):
        for priority in ("low", "urgent", "normal", "high"):
            new_ticket(subject=priority, priority=priority)

        self.assertEqual(self.by("priority_column"), ["urgent", "high", "normal", "low"])
        self.assertEqual(self.by("priority_column", descending=True), ["low", "normal", "high", "urgent"])

    def test_status_sorts_by_the_tickets_life(self):
        for status in sorted(LIFE):
            new_ticket(subject=status, status=status)

        self.assertEqual(self.by("status_column"), LIFE)
        self.assertEqual(self.by("status_column", descending=True), LIFE[::-1])

    def test_sla_sorts_by_the_due_time_the_column_shows_and_no_clock_last(self):
        now = timezone.now()
        new_ticket(subject="no clock")
        clocked_ticket(subject="response in 22 h", started=now - 2 * HOUR)
        clocked_ticket(subject="response in 4 h", started=now - 20 * HOUR)
        # Responded: the column shows the resolution (due in 10 h), not the response that was due 86 h ago.
        responded = {"status": Status.OPEN, "first_responded_at": now - 109 * HOUR}
        clocked_ticket(subject="resolution in 10 h", started=now - 110 * HOUR, **responded)

        self.assertEqual(
            self.by("sla_column"), ["response in 4 h", "resolution in 10 h", "response in 22 h", "no clock"]
        )

    def test_subject_requester_and_assignee_sort(self):
        kim = make_admin(email="kim@example.com", first_name="Kim", last_name="Lee")
        bo = make_admin(email="bo@example.com", first_name="Bo", last_name="Zane")
        new_ticket(subject="b", requester_name="adam", requester_email="zz@example.org", assignee=kim)
        new_ticket(subject="c", requester_name="", requester_email="bob@example.org", assignee=self.agent)  # Avery
        new_ticket(subject="a", requester_name="carl", requester_email="aa@example.org", assignee=bo)

        self.assertEqual(self.by("subject_column"), ["a", "b", "c"])
        self.assertEqual(self.by("subject_column", descending=True), ["c", "b", "a"])
        self.assertEqual(self.by("requester_column"), ["b", "c", "a"])  # adam, bob@example.org, carl
        self.assertEqual(self.by("assignee_column"), ["c", "a", "b"])  # Avery, Bo, Kim


class NumberSearchTests(QueueCase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.closed = new_ticket(subject="Parking", status=Status.CLOSED, last_activity_at=now - 48 * HOUR)
        self.automated = new_ticket(
            subject="Automatic reply", automated=True, status=Status.CLOSED, classification="auto_reply"
        )
        # More recent, so listed first by last activity: it only mentions the closed ticket's number.
        self.mention = new_ticket(subject=f"About ticket {self.closed.number}", status=Status.OPEN)

    def search(self, typed) -> list[str]:
        return self.listed(urlencode({"q": typed}))

    def test_a_number_finds_the_ticket_whatever_the_default_view_hides_and_lists_it_first(self):
        number = self.closed.number
        for typed in (str(number), f"#{number}", f"I2G-#{number}"):
            with self.subTest(typed):
                expected = ["Parking", self.mention.subject] if typed == str(number) else ["Parking"]
                self.assertEqual(self.search(typed), expected)
        self.assertEqual(self.search(self.automated.display_number), ["Automatic reply"])
        spam = new_ticket(subject="You have won", status=Status.SPAM, classification="spam")
        self.assertEqual(self.search(str(spam.number)), ["You have won"])

    def test_only_the_number_reaches_past_the_filters(self):
        self.assertEqual(self.search("Parking"), [])  # the default view: people's open tickets
        self.assertEqual(self.listed("q=Parking&status=any"), ["Parking"])
        self.assertEqual(self.search(f"#{self.mention.number + 1}"), [])  # no such ticket

    def test_a_sorted_column_still_orders_the_tickets_after_the_number(self):
        new_ticket(subject=f"High: {self.closed.number}", status=Status.OPEN, priority="high")
        Ticket.objects.filter(pk=self.mention.pk).update(priority="urgent")
        index = self.get().context["cl"].list_display.index("priority_column")

        listed = self.listed(urlencode({"q": str(self.closed.number), "o": str(index)}))

        self.assertEqual(listed, ["Parking", self.mention.subject, f"High: {self.closed.number}"])
