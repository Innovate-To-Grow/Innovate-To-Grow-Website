"""Merging tickets (Hongzhe's decision of 2026-11-12): nothing is ever merged into automated mail or spam, and spam is
never merged, whether through the service, the model or the admin (where it is refused before the typed
confirmation). A refused merge changes nothing and leaves no audit trail. People's tickets merge as before; automated
mail merged into a person's ticket changes nothing on it but its timeline, and stays hidden. Microsoft Graph is
never contacted."""

import uuid
from datetime import timedelta

from django.contrib.admin import helpers
from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.services.db_tools.safe_orm import ActionRequestError, resolve_model
from apps.core.services.email.inbound import AUTOMATED, LABELS

from ..admin import timeline
from ..models import Ticket, TicketEvent, TicketMessage
from ..services import numbering, tickets
from . import corpus
from .helpers import FakeReader, helpdesk_staff, receive

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


class MergeServiceTests(TestCase):
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

    def test_fewer_than_two_tickets_is_no_merge_and_no_refusal(self):
        bounce = make_ticket("Undeliverable", automated=True, hours_ago=5)
        merged = make_ticket("Merged", status=Status.MERGED)

        for selection in ([], [bounce], [bounce, bounce], [bounce, merged]):
            with self.subTest(len(selection)):
                self.assertEqual(tickets.merge_refusal(selection), "")
                self.assertIsNone(tickets.merge(selection, actor=self.agent))
        self.assertFalse(TicketEvent.objects.exists())

    def test_peoples_tickets_still_merge_into_the_oldest(self):
        older = make_ticket("Parking", hours_ago=5, unread=False, assignee=self.agent)
        newer = make_ticket("Parking again", requester="kim@example.org", participants=["kim@example.org", "lee@x.org"])
        tickets.add_note(newer, actor=self.agent, body="Same question as the other ticket.")
        newer.refresh_from_db()

        target = tickets.merge([newer, older], actor=self.agent)

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(target.pk, older.pk)
        self.assertEqual((newer.status, newer.merged_into), (Status.MERGED, older))
        self.assertEqual(older.messages.count(), 3)
        self.assertEqual(older.participants, ["pat@example.org", "kim@example.org", "lee@x.org"])
        self.assertEqual(older.last_activity_at, newer.last_activity_at)
        self.assertEqual((older.status, older.unread, older.assignee), (Status.OPEN, False, self.agent))
        self.assertEqual(older.events.get(kind=Kind.MERGED).data, {"source": newer.number, "messages": 2})
        self.assertEqual(newer.events.get(kind=Kind.MERGED).data, {"into": older.number})

    def test_automated_mail_merged_into_a_persons_ticket_changes_nothing_but_its_timeline(self):
        person = make_ticket("Did you get my registration?", hours_ago=5, unread=False, status=Status.PENDING_CUSTOMER)
        bounce = make_ticket("Undeliverable", requester=BOUNCE_SENDER, automated=True, hours_ago=1)
        before = Ticket.objects.get(pk=person.pk)
        bounce_closed_at = bounce.closed_at

        target = tickets.merge([bounce, person], actor=self.agent)

        person.refresh_from_db()
        bounce.refresh_from_db()
        self.assertEqual(target.pk, person.pk)
        unchanged = ("status", "unread", "participants", "last_activity_at", "automated", "closed_at", "priority")
        for name in unchanged:
            self.assertEqual(getattr(person, name), getattr(before, name), name)
        self.assertNotIn(BOUNCE_SENDER, person.participants)
        self.assertEqual(
            list(person.messages.values_list("kind", flat=True)),
            [TicketMessage.Kind.CUSTOMER, TicketMessage.Kind.AUTOMATED],
        )
        self.assertIn("automated", [entry.kind for entry in timeline.build(person)])  # shown collapsed
        # The automated ticket stays hidden mail: still automated, closed when it arrived, now merged.
        self.assertEqual(
            (bounce.status, bounce.merged_into, bounce.automated, bounce.closed_at, bounce.unread),
            (Status.MERGED, person, True, bounce_closed_at, False),
        )
        self.assertTrue(bounce.is_automated_or_spam)
        self.assertEqual(person.events.get(kind=Kind.MERGED).data, {"source": bounce.number, "messages": 1})

    def test_later_automated_mail_of_a_merged_thread_joins_the_persons_ticket_without_changing_it(self):
        reader = FakeReader()
        person = receive(corpus.message(sender="Alex Kim <alex.kim@contoso.example>"), reader=reader)
        reply = receive(corpus.out_of_office(), reader=reader)  # its own ticket: no thread names the person's
        tickets.merge([reply, person], actor=self.agent)
        tickets.mark_read([person])
        before = Ticket.objects.get(pk=person.pk)

        joined = receive(
            corpus.out_of_office(message_id="<oof-2@contoso.example>", in_reply_to="<oof-1@contoso.example>"),
            reader=reader,
        )

        self.assertEqual(joined.pk, person.pk)
        for name in ("status", "unread", "participants", "last_activity_at", "closed_at"):
            self.assertEqual(getattr(joined, name), getattr(before, name), name)
        self.assertEqual(joined.messages.filter(kind=TicketMessage.Kind.AUTOMATED).count(), 2)

    def test_a_merged_ticket_is_never_moved_to_the_queue(self):
        person = make_ticket("Question", hours_ago=5)
        bounce = make_ticket("Undeliverable", requester=BOUNCE_SENDER, automated=True)
        tickets.merge([person, bounce], actor=self.agent)
        bounce.refresh_from_db()

        self.assertEqual(tickets.move_to_queue([bounce], actor=self.agent), 0)

        bounce.refresh_from_db()
        self.assertEqual((bounce.status, bounce.automated, bounce.unread), (Status.MERGED, True, False))
        self.assertFalse(bounce.events.filter(kind=Kind.RECLASSIFIED).exists())

    def test_the_cli_and_the_assistant_cannot_reach_tickets_at_all(self):
        # /admin-api/ (the i2g-admin CLI) and the AI assistant resolve every model through safe_orm.
        for model_name in ("ticket", "ticketmessage"):
            with self.subTest(model_name), self.assertRaises(ActionRequestError):
                resolve_model("helpdesk", model_name, write=True)


class MergeModelTests(TestCase):
    """``Ticket.clean`` refuses the same targets for any form or ``full_clean()`` path."""

    def setUp(self):
        cache.clear()
        self.ticket = make_ticket("Question")

    def refusal(self, target) -> list[str]:
        self.ticket.merged_into = target
        with self.assertRaises(ValidationError) as refused:
            self.ticket.full_clean()
        return refused.exception.messages

    def test_a_new_merge_target_that_is_automated_mail_or_spam_is_refused(self):
        bounce = make_ticket("Undeliverable", automated=True)
        classified = make_ticket("You have won", automated=True, classification="spam")
        marked = make_ticket("Cheap watches", status=Status.SPAM)

        self.assertEqual(
            self.refusal(bounce),
            [f"Nothing is merged into automated mail or spam, and {bounce.display_number} is automated mail."],
        )
        for spam in (classified, marked):
            with self.subTest(spam.subject):
                self.assertEqual(
                    self.refusal(spam),
                    [f"Nothing is merged into automated mail or spam, and {spam.display_number} is spam."],
                )

    def test_a_ticket_merges_only_into_another_ticket_that_is_not_merged(self):
        merged = make_ticket("Merged", status=Status.MERGED)
        message = ["A ticket can only be merged into another ticket that is not merged itself."]

        self.assertEqual(self.refusal(self.ticket), message)
        self.assertEqual(self.refusal(merged), message)
        self.ticket.merged_into_id = uuid.uuid4()
        with self.assertRaises(ValidationError) as missing:
            self.ticket.full_clean()
        self.assertEqual(list(missing.exception.message_dict), ["merged_into"])  # the field's own check

    def test_a_persons_ticket_is_a_valid_target_and_an_earlier_merge_is_not_judged_again(self):
        later = make_ticket("Same question")
        later.merged_into = self.ticket
        later.full_clean()  # a person's ticket may be the target

        tickets.merge([later, self.ticket], actor=helpdesk_staff())
        Ticket.objects.filter(pk=self.ticket.pk).update(status=Status.SPAM)  # the target is marked spam afterwards
        later.refresh_from_db()

        self.assertEqual(later.merged_into, self.ticket)
        later.full_clean()  # the merge made earlier is not judged again
        make_ticket("Unmerged").full_clean()


class MergeAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)
        self.bounce = make_ticket("Undeliverable", requester=BOUNCE_SENDER, automated=True, hours_ago=9)
        self.pat = make_ticket("Parking", hours_ago=8)
        self.kim = make_ticket("Parking too", requester="kim@example.org", hours_ago=7)
        self.spam = make_ticket(
            "You have won", requester="winner@lottery.example", automated=True, classification="spam"
        )

    def act(self, *selected, view=EVERYTHING, select_across=False, follow=False):
        data = {
            "action": "merge_tickets",
            "index": "0",
            "select_across": "1" if select_across else "0",
            helpers.ACTION_CHECKBOX_NAME: [str(ticket.pk) for ticket in selected],
        }
        return self.client.post(f"{reverse(CHANGELIST)}{view}", data, follow=follow)

    def confirm(self, word="MERGE"):
        token = self.client.session[ACTION_SESSION_KEY]["token"]
        url = reverse("admin:helpdesk_ticket_confirm_action")
        return self.client.post(url, {"confirmation_word": word, "token": token}, follow=True)

    def messages(self, response) -> list[str]:
        return [str(message) for message in get_messages(response.wsgi_request)]

    def listed(self, view) -> set[str]:
        return {ticket.subject for ticket in self.client.get(f"{reverse(CHANGELIST)}{view}").context["cl"].result_list}

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_a_merge_into_automated_mail_is_refused_before_the_typed_confirmation(self):
        before = snapshot()

        response = self.act(self.kim, self.bounce, self.pat)

        self.assertRedirects(response, f"{reverse(CHANGELIST)}{EVERYTHING}", fetch_redirect_response=False)
        self.assertNotIn(ACTION_SESSION_KEY, self.client.session)  # no confirmation was asked for
        self.assertEqual(self.messages(response), [into_hidden(self.bounce, f"automated mail ({LABELS['bounce']})")])
        self.assertEqual(snapshot(), before)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_select_all_takes_the_oldest_ticket_and_is_refused_on_it(self):
        before = snapshot()

        response = self.act(self.pat, select_across=True, follow=True)

        self.assertIn(into_hidden(self.bounce, f"automated mail ({LABELS['bounce']})"), self.messages(response))
        self.assertNotIn(ACTION_SESSION_KEY, self.client.session)
        self.assertEqual(snapshot(), before)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_spam_is_refused_as_part_of_a_merge(self):
        before = snapshot()

        response = self.act(self.pat, self.kim, self.spam, follow=True)

        self.assertEqual(self.messages(response), [spam_source(self.spam)])
        self.assertEqual(snapshot(), before)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_a_merge_that_turned_into_spam_after_the_confirmation_page_is_refused_when_it_runs(self):
        self.assertIn("confirm-action", self.act(self.pat, self.kim).url)
        tickets.mark_spam([self.pat], actor=helpdesk_staff(email="other.agent@example.com"))  # meanwhile
        before = snapshot()

        response = self.confirm()

        self.assertEqual(self.messages(response), [into_hidden(self.pat, "spam")])
        self.assertEqual(snapshot(), before)
        self.assertFalse(TicketEvent.objects.filter(kind=Kind.MERGED).exists())

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_peoples_tickets_still_merge_after_the_typed_word(self):
        response = self.act(self.kim, self.pat)
        self.assertIn("confirm-action", response.url)

        page = self.client.get(response.url)
        self.assertContains(page, "Merge into the oldest selected ticket (not automated mail or spam)")
        response = self.confirm()

        self.kim.refresh_from_db()
        self.assertEqual((self.kim.status, self.kim.merged_into), (Status.MERGED, self.pat))
        self.assertEqual(self.messages(response), [f"Merged into {self.pat.display_number}."])

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_automated_mail_merged_into_an_older_persons_ticket_stays_out_of_the_queue(self):
        reply = make_ticket(
            "Automatic reply: Parking", requester="pat@example.org", automated=True, classification="auto_reply"
        )

        response = self.act(reply, self.pat, follow=True)

        reply.refresh_from_db()
        self.assertEqual(self.messages(response), [f"Merged into {self.pat.display_number}."])
        self.assertEqual((reply.status, reply.automated, reply.merged_into), (Status.MERGED, True, self.pat))
        self.assertNotIn(reply.subject, self.listed("?status=any"))  # people's tickets, every status
        self.assertIn(reply.subject, self.listed(AUTOMATED_VIEW))
        self.assertEqual(self.listed(""), {"Parking", "Parking too"})  # the default queue is unchanged

    def test_the_automated_and_spam_view_offers_no_merge(self):
        def choices(view):
            response = self.client.get(f"{reverse(CHANGELIST)}{view}")
            return [name for name, _label in response.context["action_form"].fields["action"].choices]

        self.assertIn("merge_tickets", choices(EVERYTHING))
        self.assertIn("merge_tickets", choices(""))
        self.assertNotIn("merge_tickets", choices(AUTOMATED_VIEW))
        self.assertIn("move_to_queue", choices(AUTOMATED_VIEW))

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_a_merge_posted_to_the_automated_and_spam_view_does_nothing(self):
        before = snapshot()

        response = self.act(self.spam, self.bounce, view=AUTOMATED_VIEW, follow=True)

        self.assertEqual(self.messages(response), ["No action selected."])
        self.assertEqual(snapshot(), before)
