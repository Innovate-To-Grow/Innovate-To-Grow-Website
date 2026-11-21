from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, Member
from apps.helpdesk.tests.ingest.test_ingest_rules import Kind, Status

from ...models import Ticket
from ...services import outbound, tickets
from ...services.outbound.replies import last_inbound
from .. import corpus
from ..helpers import FakeReader, helpdesk_staff, receive
from ..service.intake.scam_mail import DMARC_PASS

PASS = {"Authentication-Results": DMARC_PASS}


class EdgeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reader = FakeReader()

    def test_a_members_other_addresses_count_as_participants(self):
        member = Member.objects.create_user(password="x", first_name="Pat", last_name="Doe")
        ContactEmail.objects.create(member=member, email_address="pat@example.org", email_type="primary", verified=True)
        ContactEmail.objects.create(
            member=member, email_address="pat.doe@work.example", email_type="secondary", verified=True
        )
        first = receive(corpus.message(), reader=self.reader)

        joined = receive(
            corpus.message(sender="pat.doe@work.example", message_id="<w@x>", subject=f"Re: [{first.display_number}]"),
            reader=self.reader,
        )

        self.assertEqual(joined.pk, first.pk)

    def test_an_address_a_member_never_verified_is_not_hers(self):
        eve = Member.objects.create_user(password="x", first_name="Eve", last_name="Member")
        ContactEmail.objects.create(member=eve, email_address="eve@example.org", email_type="primary", verified=True)
        ContactEmail.objects.create(member=eve, email_address="victor@example.net", email_type="other")  # no code yet
        victor = receive(corpus.message(sender="Victor <victor@example.net>", message_id="<v1@x>"), reader=self.reader)
        hers = corpus.message(sender="Eve <eve@example.org>", message_id="<e1@x>", subject=f"[{victor.display_number}]")
        own = receive(corpus.message(sender="Eve <eve@example.org>", message_id="<e2@x>"), conversation="AAQk-eve")
        answer = corpus.message(sender="Victor <victor@example.net>", message_id="<v2@x>", subject="RE: Hi")

        self.assertIsNone(victor.requester_member)
        self.assertNotEqual(receive(hers, reader=self.reader).pk, victor.pk)  # Eve is no participant of his ticket
        self.assertEqual(own.requester_member, eve)
        self.assertNotEqual(receive(answer, conversation="AAQk-eve").pk, own.pk)  # nor is he of hers

    def test_a_requester_answers_with_her_own_other_address_whatever_she_named_before(self):
        for number, named in enumerate(("Lia Aide <lia@example.org>", "Mo Aide <mo@example.org>")):
            raw = corpus.message(sender="Nora Field <nora@example.edu>", message_id=f"<n{number}@x>",
                                 headers={**PASS, "Reply-To": named})  # fmt: skip
            receive(raw)  # she wrote for two people, on tickets of theirs
        ticket = receive(corpus.message(sender="Nora Field <nora@example.edu>", message_id="<n3@x>", headers=PASS))
        tickets.update_ticket(ticket, actor=helpdesk_staff(), status=Status.PENDING_CUSTOMER)
        home = {**PASS, "Reply-To": "Nora Field <nora@home.example>", "X-MS-Exchange-Organization-SCL": "5"}
        answer = corpus.message(sender="Nora Field <nora@example.edu>", message_id="<n4@x>", headers=home,
                                subject=f"Re: [{ticket.display_number}]", text="Thanks, I will bring two.")  # fmt: skip

        self.assertEqual(receive(answer).pk, ticket.pk)  # also as Exchange-rated spam: an answer, flagged
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.OPEN)
        later = corpus.message(sender="Nora Field <nora@home.example>", message_id="<n5@x>", text="One more thing.",
                               subject=f"Re: [{ticket.display_number}]")  # fmt: skip
        self.assertEqual(receive(later).pk, ticket.pk)
        self.assertEqual(last_inbound(ticket).internet_message_id, "<n5@x>")  # her other address is hers
        self.assertNotIn("nora@home.example", outbound.cc_suggestions(Ticket.objects.get(pk=ticket.pk)))

    def test_her_own_other_addresses_elsewhere_never_make_her_a_form(self):
        sender = "Nora Field <nora@example.edu>"
        named = ("nora.f@home.example", "nora.g@home.example", "Nora Field <nora.2@x.org>", "Nora Field <n3@x.org>")
        for number, reply_to in enumerate(named):  # nameless, or under her own name: hers, each a ticket of its own
            receive(corpus.message(sender=sender, message_id=f"<o{number}@x>", headers={**PASS, "Reply-To": reply_to}))
        ticket = receive(corpus.message(sender=sender, message_id="<o9@x>", headers=PASS))

        for number, (writer, aide) in enumerate(
            ((sender, "Ana Aide <ana@x.org>"), ("nora@example.edu", "Bo <b@x.org>"))
        ):
            raw = corpus.message(sender=writer, message_id=f"<a{number}@x>", subject=f"Re: [{ticket.display_number}]",
                                 headers={**PASS, "Reply-To": aide})  # fmt: skip
            self.assertEqual(receive(raw).pk, ticket.pk)

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

    def test_nul_characters_never_keep_a_message_out_of_the_queue(self):
        # PostgreSQL text and JSON cannot hold NUL: before they were dropped, such a message failed every attempt.
        raw = corpus.forwarded(inner_text="quoted\x00text").replace(b"<fwd-1@", b"<fwd-1\x00@", 1)
        raw = raw.replace(b"Please see below;", b"Please see\x00 below;", 1)

        ticket = receive(raw, reader=self.reader, internet_message_id="")

        message = ticket.messages.get()
        self.assertEqual(message.internet_message_id, "<fwd-1@mail.example.org>")
        self.assertIn("Please see below;", message.body_text)
        self.assertEqual(message.attached_messages[0]["text"].strip(), "quotedtext")

    def test_a_blocked_type_named_with_trailing_dots_is_still_blocked(self):
        raw = corpus.message(attachments=[("invoice.js.", b"WScript.Echo(1)", "application/octet-stream")])

        ticket = receive(raw, reader=self.reader)

        attachment = ticket.messages.get().attachments.get()
        self.assertEqual((attachment.filename, attachment.blocked, attachment.content), ("invoice.js", True, None))

    def test_a_message_without_a_sender_still_becomes_a_ticket(self):
        raw = b"Subject: no sender\r\nMessage-ID: <nosender@x>\r\n\r\nhello"

        ticket = receive(raw, reader=self.reader)

        self.assertEqual((ticket.requester_email, ticket.requester_member, ticket.status), ("", None, Status.NEW))
