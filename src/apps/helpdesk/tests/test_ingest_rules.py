"""What every inbound message becomes (Hongzhe's decision of 2026-11-11): a person's or an uncertain message opens or
joins a normal ticket; automated mail opens a ticket closed at once and hidden, joins a thread without changing it,
and never reopens anything; the site's own mail keeps no content. Microsoft Graph is never contacted."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail, Member
from apps.core.models import InboundMessage
from apps.core.services.email.inbound import LINK_PLACEHOLDER
from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.mail.models import EmailCampaign

from ..models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ..services.ingest.store import OWN_MAIL_NOTE
from . import corpus
from .helpers import FakeReader, ingest, queue, receive

Status = Ticket.Status
Kind = TicketEvent.Kind
AUTOMATED_SAMPLES = {
    "auto_reply": corpus.out_of_office,
    "left_org": corpus.left_organisation,
    "bounce": corpus.bounce_report,
    "receipt": corpus.read_receipt,
    "system": corpus.calendar_reply,
    "bulk": corpus.list_mail,
    "spam": corpus.spam,
    "own": corpus.own_message,
}


def event_kinds(ticket) -> list[str]:
    return list(ticket.events.order_by("created_at").values_list("kind", flat=True))


class PersonTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_persons_message_opens_a_visible_unread_ticket(self):
        ticket = receive(corpus.message(cc="Kim <kim@example.org>, Site <i2g@ucmerced.edu>"))

        self.assertGreaterEqual(ticket.number, 1001)
        self.assertEqual(ticket.display_number, f"I2G-#{ticket.number}")
        self.assertEqual(
            (ticket.status, ticket.priority, ticket.automated, ticket.unread, ticket.classification),
            (Status.NEW, Ticket.Priority.NORMAL, False, True, "human"),
        )
        self.assertEqual((ticket.requester_email, ticket.requester_name), ("pat@example.org", "Pat Doe"))
        self.assertEqual(ticket.participants, ["pat@example.org", "kim@example.org"])
        self.assertEqual(ticket.subject, "Question about the showcase")
        self.assertIsNone(ticket.closed_at)
        self.assertFalse(ticket.backfilled)
        self.assertEqual(event_kinds(ticket), [Kind.CREATED])
        message = ticket.messages.get()
        self.assertEqual((message.kind, message.scam_level), (TicketMessage.Kind.CUSTOMER, "low"))
        self.assertEqual(message.occurred_at, ticket.first_message_at)

    def test_the_requester_is_linked_to_the_member_who_owns_the_address(self):
        member = Member.objects.create_user(password="x", first_name="Pat", last_name="Doe")
        ContactEmail.objects.create(member=member, email_address="Pat@Example.org", email_type="secondary")

        self.assertEqual(receive(corpus.message()).requester_member, member)

    def test_a_reply_to_a_campaign_is_a_new_ticket_linked_to_the_campaign(self):
        campaign = EmailCampaign.objects.create(name="Blast", subject="Innovate to Grow 2026")
        make_email(internet_message_id="<blast-1@ucmerced.edu>", campaign_id=campaign.pk)

        ticket = receive(corpus.message(in_reply_to="<blast-1@ucmerced.edu>", subject="Re: Innovate to Grow 2026"))

        self.assertEqual(ticket.campaign, campaign)
        self.assertEqual(ticket.status, Status.NEW)

    def test_mail_imported_long_after_it_arrived_is_backfilled(self):
        old = receive(corpus.message(), received=timezone.now() - timedelta(days=3))

        self.assertTrue(old.backfilled)

    def test_a_high_scam_score_makes_it_spam_and_a_medium_one_suspicious(self):
        with patch("apps.helpdesk.services.ingest.classify.analyze_email", return_value={"risk_level": "high"}):
            spam = receive(corpus.message(message_id="<s1@example.org>"))
        with patch("apps.helpdesk.services.ingest.classify.analyze_email", return_value={"risk_level": "medium"}):
            suspicious = receive(corpus.message(message_id="<s2@example.org>", sender="other@example.org"))

        self.assertEqual((spam.status, spam.automated, spam.classification), (Status.SPAM, True, "spam"))
        self.assertEqual(
            (suspicious.status, suspicious.automated, suspicious.flags), (Status.NEW, False, ["suspicious"])
        )

    def test_a_forged_site_address_is_a_suspicious_ticket(self):
        ticket = receive(corpus.own_message(internal=False))

        self.assertEqual((ticket.automated, ticket.classification), (False, "human"))
        self.assertIn("suspicious", ticket.flags)

    def test_sign_in_links_are_scrubbed_everywhere_they_are_stored(self):
        raw = corpus.message(
            subject=f"Re: link {corpus.LOGIN_LINK}",
            text=f"My link {corpus.LOGIN_LINK} and {corpus.UNSUBSCRIBE_LINK} fail",
            html=f'<p><a href="{corpus.IMPERSONATE_LINK}">link</a></p>',
        )

        ticket = receive(raw)
        forwarded = receive(corpus.forwarded())

        message = ticket.messages.get()
        stored = " ".join((ticket.subject, message.subject, message.body_text, message.body_html))
        self.assertNotIn("token=", stored)
        self.assertNotIn("unsubscribe/", stored)
        self.assertEqual(stored.count(LINK_PLACEHOLDER), 5)  # two subjects, two links in the text, one in the HTML
        (attached,) = forwarded.messages.get().attached_messages
        self.assertEqual(attached["text"].strip(), f"Sign in here: {LINK_PLACEHOLDER}")


class AutomatedMailTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_every_automated_class_opens_a_closed_hidden_low_priority_ticket(self):
        for classification, build in AUTOMATED_SAMPLES.items():
            with self.subTest(classification):
                ticket = receive(build())
                self.assertEqual(ticket.classification, classification)
                self.assertTrue(ticket.automated)
                self.assertEqual(ticket.status, Status.SPAM if classification == "spam" else Status.CLOSED)
                self.assertEqual((ticket.priority, ticket.unread), (Ticket.Priority.LOW, False))
                self.assertEqual(ticket.closed_at, ticket.first_message_at)
                self.assertEqual(ticket.messages.get().kind, TicketMessage.Kind.AUTOMATED)

    def test_the_inbound_row_keeps_the_class_for_other_tools(self):
        reader = FakeReader()
        row = queue(corpus.left_organisation(), reader=reader)
        ingest(reader)

        row.refresh_from_db()
        self.assertEqual(
            (row.status, row.classification, row.subtype), (InboundMessage.Status.DONE, "left_org", "left_org")
        )
        self.assertTrue(row.result["created"])

    def test_the_sites_own_mail_keeps_no_content(self):
        raw = corpus.message(
            sender="Innovate to Grow <i2g@ucmerced.edu>",
            text="Your code is 123456",
            html="<p>Your code is 123456</p>",
            headers={"X-MS-Exchange-Organization-AuthAs": "Internal"},
            attachments=[("ticket.pdf", b"%PDF-1.7", "application/pdf")],
        )

        message = receive(raw).messages.get()

        self.assertEqual((message.body_text, message.body_html), (OWN_MAIL_NOTE, ""))
        self.assertFalse(message.attachments.exists())
        self.assertEqual(message.attached_messages, [])

    def test_automated_mail_keeps_no_text_of_the_messages_it_returns(self):
        raw = corpus.message(
            sender="MAILER-DAEMON <mailer-daemon@mx.example.org>",
            subject="Undelivered Mail Returned to Sender",
            message_id="<ndr-2@mx.example.org>",
        )
        ticket = receive(raw)

        self.assertEqual(ticket.classification, "bounce")
        self.assertEqual(ticket.messages.get().attached_messages, [])

    def test_automated_mail_joins_its_thread_without_changing_the_ticket(self):
        reader = FakeReader()
        human = receive(corpus.message(sender="Alex Kim <alex.kim@contoso.example>"), reader=reader)
        Ticket.objects.filter(pk=human.pk).update(status=Status.CLOSED, closed_at=timezone.now(), unread=False)
        before = Ticket.objects.get(pk=human.pk)

        joined = receive(corpus.out_of_office(in_reply_to="<m1@mail.example.org>"), reader=reader)

        joined.refresh_from_db()
        self.assertEqual(joined.pk, human.pk)
        self.assertEqual(
            (joined.status, joined.unread, joined.last_activity_at, joined.closed_at),
            (Status.CLOSED, False, before.last_activity_at, before.closed_at),
        )
        self.assertEqual(
            list(joined.messages.values_list("kind", flat=True)),
            [TicketMessage.Kind.CUSTOMER, TicketMessage.Kind.AUTOMATED],
        )
        self.assertEqual(event_kinds(joined), [Kind.CREATED, Kind.AUTOMATED_MESSAGE])

    def test_an_automated_ticket_never_reopens_and_a_person_gets_a_new_ticket(self):
        reader = FakeReader()
        automated = receive(corpus.out_of_office(), reader=reader)

        follow = receive(
            corpus.message(sender="Alex Kim <alex.kim@contoso.example>", in_reply_to="<oof-1@contoso.example>"),
            reader=reader,
        )

        automated.refresh_from_db()
        self.assertNotEqual(follow.pk, automated.pk)
        self.assertEqual((automated.status, automated.automated), (Status.CLOSED, True))
        self.assertEqual((follow.status, follow.related_ticket), (Status.NEW, automated))
        self.assertIn(Kind.RELATED, event_kinds(automated))


class ThreadingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reader = FakeReader()
        self.first = receive(corpus.message(cc="kim@example.org"), reader=self.reader, conversation="CONV-1")

    def reply(self, **values):
        values.setdefault("message_id", f"<r{TicketMessage.objects.count()}@mail.example.org>")
        conversation = values.pop("conversation", "")
        return receive(corpus.message(**values), reader=self.reader, conversation=conversation)

    def test_a_reply_joins_by_references_and_marks_the_ticket_unread(self):
        Ticket.objects.filter(pk=self.first.pk).update(unread=False, status=Status.PENDING_CUSTOMER)

        joined = self.reply(sender="Lee <lee@example.org>", references="<root@x> <m1@mail.example.org>")

        self.assertEqual(joined.pk, self.first.pk)
        self.assertEqual((joined.status, joined.unread), (Status.OPEN, True))
        self.assertIn("lee@example.org", joined.participants)
        self.assertGreaterEqual(joined.last_activity_at, self.first.last_activity_at)
        self.assertEqual(event_kinds(joined), [Kind.CREATED, Kind.CUSTOMER_MESSAGE, Kind.STATUS])

    def test_a_reply_soon_after_closing_reopens_the_ticket(self):
        Ticket.objects.filter(pk=self.first.pk).update(
            status=Status.RESOLVED, closed_at=timezone.now(), resolved_at=timezone.now()
        )

        reopened = self.reply(in_reply_to="<m1@mail.example.org>")

        self.assertEqual(reopened.pk, self.first.pk)
        self.assertEqual((reopened.status, reopened.closed_at, reopened.resolved_at), (Status.OPEN, None, None))
        self.assertIn(Kind.REOPENED, event_kinds(reopened))

    def test_a_reply_long_after_closing_opens_a_linked_follow_up(self):
        closed_at = timezone.now() - timedelta(days=HelpdeskSettings().reopen_window_days + 1)
        Ticket.objects.filter(pk=self.first.pk).update(status=Status.CLOSED, closed_at=closed_at)

        follow_up = self.reply(in_reply_to="<m1@mail.example.org>")

        self.assertNotEqual(follow_up.pk, self.first.pk)
        self.assertEqual(follow_up.related_ticket_id, self.first.pk)
        related = self.first.events.get(kind=Kind.RELATED)
        self.assertEqual(related.data, {"number": follow_up.number, "reason": "follow-up after the ticket closed"})

    def test_the_subject_token_works_only_for_participants(self):
        token = f"Re: Question [I2G-#{self.first.number}]"

        joined = self.reply(subject=token, sender="kim@example.org")
        stranger = self.reply(subject=token, sender="stranger@evil.example")

        self.assertEqual(joined.pk, self.first.pk)
        self.assertNotEqual(stranger.pk, self.first.pk)
        mention = stranger.events.get(kind=Kind.MENTION)
        self.assertEqual(mention.data, {"number": self.first.number})

    def test_a_token_without_brackets_and_in_any_case_threads_too(self):
        joined = self.reply(subject=f"about i2g-#{self.first.number} again")

        self.assertEqual(joined.pk, self.first.pk)

    def test_the_conversation_id_works_only_for_participants(self):
        joined = self.reply(conversation="CONV-1")
        stranger = self.reply(conversation="CONV-1", sender="someone@else.example")

        self.assertEqual(joined.pk, self.first.pk)
        self.assertNotEqual(stranger.pk, self.first.pk)

    def test_a_persons_reply_prefers_their_human_ticket_over_an_automated_one(self):
        receive(corpus.out_of_office(sender="Pat Doe <pat@example.org>"), reader=self.reader, conversation="CONV-1")

        joined = self.reply(conversation="CONV-1")

        self.assertEqual(joined.pk, self.first.pk)

    def test_a_merged_ticket_is_followed(self):
        target = receive(corpus.message(sender="other@example.org", message_id="<t@x>"), reader=self.reader)
        Ticket.objects.filter(pk=self.first.pk).update(status=Status.MERGED, merged_into=target)

        joined = self.reply(in_reply_to="<m1@mail.example.org>")

        self.assertEqual(joined.pk, target.pk)


class DuplicateTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_second_copy_of_a_message_is_not_stored_or_even_fetched(self):
        reader = FakeReader()
        first = receive(corpus.message(), reader=reader)
        second_copy = queue(corpus.message(), reader=reader)
        fetched_before = len(reader.fetched)

        ingest(reader)

        second_copy.refresh_from_db()
        self.assertEqual(len(reader.fetched), fetched_before)
        self.assertEqual(second_copy.result, {"ticket": first.number, "duplicate": True})
        self.assertEqual(TicketMessage.objects.count(), 1)

    def test_a_message_without_a_message_id_is_recognised_by_its_content(self):
        reader = FakeReader()
        first = receive(corpus.message(message_id=None), reader=reader)
        again = queue(corpus.message(message_id=None), reader=reader)

        ingest(reader)

        again.refresh_from_db()
        self.assertEqual(again.result["ticket"], first.number)
        self.assertTrue(again.result["duplicate"])
        self.assertEqual(TicketMessage.objects.count(), 1)


class FloodTests(TestCase):
    def setUp(self):
        cache.clear()
        HelpdeskSettings.objects.create(flood_threshold=2, flood_window_minutes=60)

    def test_more_new_tickets_than_the_threshold_from_one_sender_are_grouped(self):
        reader = FakeReader()
        tickets = [
            receive(corpus.message(message_id=f"<f{index}@x>", subject=f"Spam run {index}"), reader=reader)
            for index in range(4)
        ]

        self.assertEqual(len({ticket.pk for ticket in tickets[:2]}), 2)
        self.assertEqual(tickets[2].pk, tickets[1].pk)
        self.assertEqual(tickets[3].pk, tickets[1].pk)
        grouped = Ticket.objects.get(pk=tickets[1].pk)
        self.assertIn("flood", grouped.flags)
        self.assertEqual(grouped.messages.count(), 3)
        self.assertIn(Kind.FLOOD, event_kinds(grouped))

    def test_automated_mail_is_never_grouped(self):
        reader = FakeReader()
        numbers = {
            receive(corpus.out_of_office(message_id=f"<o{index}@x>"), reader=reader).number for index in range(4)
        }

        self.assertEqual(len(numbers), 4)


class EdgeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reader = FakeReader()

    def test_a_members_other_addresses_count_as_participants(self):
        member = Member.objects.create_user(password="x", first_name="Pat", last_name="Doe")
        ContactEmail.objects.create(member=member, email_address="pat@example.org", email_type="primary")
        ContactEmail.objects.create(member=member, email_address="pat.doe@work.example", email_type="secondary")
        first = receive(corpus.message(), reader=self.reader)

        joined = receive(
            corpus.message(sender="pat.doe@work.example", message_id="<w@x>", subject=f"Re: [{first.display_number}]"),
            reader=self.reader,
        )

        self.assertEqual(joined.pk, first.pk)

    def test_a_token_naming_no_ticket_is_ignored(self):
        ticket = receive(corpus.message(subject="About I2G-#999999"), reader=self.reader)

        self.assertFalse(ticket.events.filter(kind=Kind.MENTION).exists())

    def test_hostile_header_values_are_cut_to_what_the_database_holds(self):
        long_local = "a" * 300
        raw = corpus.message(sender=f"{'N' * 400} <{long_local}@example.org>", subject="S " * 400)

        ticket = receive(raw, reader=self.reader)

        self.assertEqual(len(ticket.requester_email), 254)
        self.assertLessEqual(len(ticket.subject), 255)
        self.assertLessEqual(len(ticket.requester_name), 255)

    def test_a_message_without_a_sender_still_becomes_a_ticket(self):
        raw = b"Subject: no sender\r\nMessage-ID: <nosender@x>\r\n\r\nhello"

        ticket = receive(raw, reader=self.reader)

        self.assertEqual((ticket.requester_email, ticket.requester_member, ticket.status), ("", None, Status.NEW))
