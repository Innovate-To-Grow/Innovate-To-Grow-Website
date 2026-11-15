from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, Member
from apps.helpdesk.tests.ingest.test_ingest_rules import Kind, Status

from .. import corpus
from ..helpers import FakeReader, receive


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
