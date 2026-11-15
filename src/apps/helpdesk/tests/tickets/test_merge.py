"""Merging tickets (Hongzhe's decision of 2026-11-12): nothing is ever merged into automated mail or spam, and spam is
never merged, whether through the service, the model or the admin (where it is refused before the typed
confirmation). A refused merge changes nothing and leaves no audit trail. People's tickets merge as before; automated
mail merged into a person's ticket changes nothing on it but its timeline, and stays hidden. Microsoft Graph is
never contacted."""

from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.services.email.inbound import AUTOMATED, LABELS

from ...models import Ticket, TicketEvent, TicketMessage
from ...services import tickets
from ...services.tickets import numbering
from ..helpers import helpdesk_staff

Status = Ticket.Status
Kind = TicketEvent.Kind
CHANGELIST = "admin:helpdesk_ticket_changelist"
ACTION_SESSION_KEY = "_admin_pending_action_helpdesk_ticket"
EVERYTHING = "?mail=all&status=any"
AUTOMATED_VIEW = "?mail=automated&status=any"
BOUNCE_SENDER = "postmaster@ucmerced.onmicrosoft.com"


def make_ticket(subject, *, requester="pat@example.org", hours_ago=1, automated=False, **values) -> Ticket:
    """A ticket with one message (automated mail: closed at once, as the ingest makes it), in creation (number) order."""
    at = timezone.now() - timedelta(hours=hours_ago)
    if automated:
        values.setdefault("classification", "bounce")
        values.setdefault("status", Status.SPAM if values["classification"] == "spam" else Status.CLOSED)
        values.setdefault("closed_at", at)
        values.setdefault("priority", Ticket.Priority.LOW)
    else:
        values.setdefault("status", Status.OPEN)
        values.setdefault("classification", "human")
    values.setdefault("participants", [requester])
    ticket = numbering.create_ticket(
        subject=subject,
        requester_email=requester,
        automated=automated,
        first_message_at=at,
        last_activity_at=at,
        **values,
    )
    TicketMessage.objects.create(
        ticket=ticket,
        kind=TicketMessage.Kind.AUTOMATED if automated else TicketMessage.Kind.CUSTOMER,
        from_address=requester,
        subject=subject,
        body_text=subject,
        occurred_at=at,
        classification=values["classification"],
    )
    return ticket


def snapshot():
    """Every ticket, message, audit event and admin log entry as stored: a refused merge must leave all of it alone."""
    return (
        list(Ticket.objects.order_by("number").values()),
        list(TicketMessage.objects.order_by("pk").values("pk", "ticket_id", "kind", "updated_at")),
        list(TicketEvent.objects.order_by("pk").values("pk", "ticket_id", "kind", "data")),
        LogEntry.objects.count(),
    )


def into_hidden(ticket: Ticket, what: str) -> str:
    return (
        f"Nothing was merged: {ticket.display_number}, the oldest selected ticket, is {what}, and nothing is merged "
        'into automated mail or spam. Leave it out of the selection, or use "Not automated: move to the queue" on it '
        "first if a person wrote it."
    )


def spam_source(ticket: Ticket) -> str:
    return (
        f"Nothing was merged: {ticket.display_number} is spam, and spam is never merged into a person's ticket. Leave "
        'it out of the selection, or use "Not automated: move to the queue" on it first if it is not spam.'
    )


class _MergeServiceCase(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def assert_refused(self, selection, message):
        before = snapshot()
        self.assertEqual(tickets.merge_refusal(selection), message)
        with self.assertRaises(tickets.MergeRefused) as refused:
            tickets.merge(selection, actor=self.agent)
        self.assertEqual(str(refused.exception), message)
        self.assertEqual(snapshot(), before)
        self.assertFalse(TicketEvent.objects.filter(kind=Kind.MERGED).exists())


class MergeServiceTests(_MergeServiceCase):
    def test_nothing_is_merged_into_automated_mail_of_any_class(self):
        for classification in sorted(AUTOMATED):
            with self.subTest(classification):
                target = make_ticket("Automated", automated=True, classification=classification, hours_ago=5)
                person = make_ticket("Question", hours_ago=1)
                what = "spam" if classification == "spam" else f"automated mail ({LABELS[classification]})"

                self.assert_refused([person, target], into_hidden(target, what))

    def test_automated_mail_without_a_known_class_is_refused_as_well(self):
        target = make_ticket("Automated", automated=True, classification="", hours_ago=5)
        person = make_ticket("Question")

        self.assert_refused([target, person], into_hidden(target, "automated mail"))

    def test_nothing_is_merged_into_a_ticket_staff_marked_as_spam(self):
        marked = make_ticket("Cheap watches", requester="seller@example.net", hours_ago=5)
        tickets.mark_spam([marked], actor=self.agent)
        marked.refresh_from_db()
        person = make_ticket("Question")

        self.assertFalse(marked.automated)
        self.assert_refused([person, marked], into_hidden(marked, "spam"))

    def test_spam_is_never_merged_into_a_persons_ticket(self):
        person = make_ticket("Question", hours_ago=5)
        classified = make_ticket(
            "You have won", requester="winner@lottery.example", automated=True, classification="spam"
        )
        marked = make_ticket("Cheap watches", requester="seller@example.net")
        tickets.mark_spam([marked], actor=self.agent)
        marked.refresh_from_db()
        # Automated mail that staff closed by hand is still classified spam.
        closed = make_ticket("Prize", automated=True, classification="spam", status=Status.CLOSED)

        for spam in (classified, marked, closed):
            with self.subTest(spam.subject):
                self.assert_refused([person, spam], spam_source(spam))
        self.assertEqual(
            tickets.merge_refusal([person, make_ticket("Other question"), classified]), spam_source(classified)
        )

    def test_the_rows_are_judged_again_once_locked(self):
        # The selection as the list showed it, then changed by someone else before the merge ran.
        target, other, third = (make_ticket(f"Question {index}", hours_ago=5 - index) for index in range(3))
        merged_elsewhere = make_ticket("Another question")
        changes = (
            (target, {"automated": True, "classification": "auto_reply", "status": Status.CLOSED}),
            (other, {"status": Status.SPAM}),
            (third, {"status": Status.MERGED, "merged_into": merged_elsewhere}),
        )
        expected = (
            into_hidden(target, f"automated mail ({LABELS['auto_reply']})"),
            spam_source(other),
            f"Nothing was merged: {third.display_number} was merged meanwhile. Reload the list and try again.",
        )
        for (ticket, values), message in zip(changes, expected, strict=True):
            with self.subTest(message):
                stale = [Ticket.objects.get(pk=item.pk) for item in (target, other, third)]
                saved = Ticket.objects.filter(pk=ticket.pk).values(*values).get()
                Ticket.objects.filter(pk=ticket.pk).update(**values)
                before = snapshot()

                self.assertEqual(tickets.merge_refusal(stale), "")  # what the list showed was fine
                with self.assertRaises(tickets.MergeRefused) as refused:
                    tickets.merge(stale, actor=self.agent)

                self.assertEqual(str(refused.exception), message)
                self.assertEqual(snapshot(), before)
                Ticket.objects.filter(pk=ticket.pk).update(**saved)
        self.assertFalse(TicketEvent.objects.filter(kind=Kind.MERGED).exists())
