"""A sender whose long display name was folded inside its quotes (as Outlook folds "Last, First - Department, ..."):
core's ``addresses()`` unfolds the header before reading it, so the message keeps its requester. Read folded, the
comma in the name split it into an entry without an address: the ticket had no requester, could not be answered, and
the sender's own follow-up could not join it by its number."""

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, Member

from ... import corpus
from ...helpers import FakeReader, receive

NAME = "Smith, Jane - Office of the Registrar, University"


def folded(*, fold="\r\n ", message_id="<fold-1@mail.example.edu>", subject="Transcript question") -> bytes:
    """Raw MIME whose From header is folded (``fold``) inside the quoted display name."""
    return corpus._join(
        [
            f'From: "Smith, Jane - Office of the Registrar,{fold}University" <JSmith@Example.edu>',
            f"To: {corpus.SITE}",
            f"Subject: {subject}",
            "Date: Wed, 11 Nov 2026 10:00:00 +0000",
            f"Message-ID: {message_id}",
            "MIME-Version: 1.0",
            "Content-Type: text/plain; charset=utf-8",
            "",
            "Hello, could you confirm that our team is registered for the showcase?",
            "",
        ]
    )


class FoldedSenderTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_the_folded_sender_is_the_requester(self):
        for index, fold in enumerate(("\r\n ", "\r\n\t")):
            with self.subTest(fold=fold):
                ticket = receive(folded(fold=fold, message_id=f"<fold-{index}@mail.example.edu>"))

                self.assertEqual((ticket.requester_email, ticket.requester_name), ("jsmith@example.edu", NAME))
                self.assertEqual(ticket.participants, ["jsmith@example.edu"])
                message = ticket.messages.get()
                self.assertEqual((message.from_address, message.from_name), ("jsmith@example.edu", NAME))
                self.assertEqual((ticket.automated, ticket.classification), (False, "human"))

    def test_the_requester_is_the_member_and_their_follow_up_joins_by_the_ticket_number(self):
        member = Member.objects.create_user(password="x", first_name="Jane", last_name="Smith")
        ContactEmail.objects.create(
            member=member, email_address="jsmith@example.edu", email_type="primary", verified=True
        )
        reader = FakeReader()
        ticket = receive(folded(), reader=reader)
        subject = f"Re: Transcript question [{ticket.display_number}]"

        follow_up = receive(folded(message_id="<fold-2@mail.example.edu>", subject=subject), reader=reader)

        self.assertEqual(ticket.requester_member, member)
        self.assertEqual(follow_up.pk, ticket.pk)
        self.assertEqual(follow_up.messages.count(), 2)
