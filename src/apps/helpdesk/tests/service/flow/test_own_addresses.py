"""The helpdesk's own addresses (``replies.site_addresses``): the From address, the Graph mailbox the site sends
from, every mailbox the intake reads, and each mailbox a ticket's mail arrived in. A reply never goes to one of them
(as the requester or in Cc) and the acknowledgement skips them. A reply's Reply-To is the mailbox the requester wrote
to, when that is not the From address."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob, MicrosoftGraphProviderConfig

from ....models import IntakeState, TicketMessage
from ....services import outbound
from ....services.outbound import acknowledgement, replies
from ... import corpus
from ...helpers import FakeReader, queue, receive
from ...helpers.service import new_ticket, sending_settings
from ..outbound.test_jobs import JobTestCase, claimed

FROM = "i2g@g.ucmerced.edu"  # the From address while no email service is configured
INTAKE = "helpdesk@ucmerced.edu"
ARRIVED = "events@ucmerced.edu"


def graph_sends_as(mailbox):
    return patch.object(
        MicrosoftGraphProviderConfig, "load", return_value=MicrosoftGraphProviderConfig(mailbox=mailbox)
    )


def arrived_in(ticket, mailbox, **values):
    """``ticket`` with a message of its requester that arrived in ``mailbox``."""
    TicketMessage.objects.create(
        ticket=ticket,
        kind=TicketMessage.Kind.CUSTOMER,
        inbound=queue(mailbox=mailbox),
        from_address=ticket.requester_email,
        occurred_at=timezone.now(),
        **values,
    )
    return ticket


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class SiteAddressTests(TestCase):
    def setUp(self):
        cache.clear()
        self.settings = sending_settings(send_acknowledgement=True)
        IntakeState.objects.create(mailbox="Helpdesk@UCMerced.edu")

    def test_every_kind_of_own_address(self):
        ticket = arrived_in(new_ticket(), "Events@UCMerced.edu")

        with graph_sends_as("Sender@UCMerced.edu"):
            self.assertEqual(replies.site_addresses(), {FROM, "sender@ucmerced.edu", INTAKE})
            self.assertEqual(replies.site_addresses(ticket), {FROM, "sender@ucmerced.edu", INTAKE, ARRIVED})
        # Without a mailbox of its own, Graph sends as the From address.
        self.assertEqual(replies.site_addresses(), {FROM, INTAKE})
        self.assertEqual(replies.site_addresses(new_ticket()), {FROM, INTAKE})  # no mail arrived for it

    def test_every_mailbox_a_tickets_mail_arrived_in_and_the_latest_one_for_answers(self):
        ticket = arrived_in(new_ticket(), "old@ucmerced.edu")
        TicketMessage.objects.filter(ticket=ticket).update(created_at=timezone.now() - timedelta(days=1))
        arrived_in(ticket, ARRIVED)

        self.assertTrue({"old@ucmerced.edu", ARRIVED} <= replies.site_addresses(ticket))
        self.assertEqual(replies.reply_mailbox(ticket), ARRIVED)
        self.assertEqual(replies.reply_mailbox(new_ticket()), "")

    def test_a_requester_among_them_is_never_answered(self):
        refusal = "The requester is one of the helpdesk's own addresses."
        candidates = (
            new_ticket(requester_email="I2G@g.ucmerced.edu"),
            new_ticket(requester_email="sender@ucmerced.edu"),
            new_ticket(requester_email=INTAKE.upper()),
            arrived_in(new_ticket(requester_email=ARRIVED), ARRIVED),
        )
        with graph_sends_as("sender@ucmerced.edu"):
            for ticket in candidates:
                with self.subTest(ticket.requester_email):
                    self.assertEqual(replies.can_reply(ticket, self.settings), refusal)
                    with self.assertRaisesMessage(outbound.ReplyRefused, refusal):
                        outbound.queue_reply(ticket, actor=None, body="Hello")
        self.assertEqual(replies.can_reply(arrived_in(new_ticket(), ARRIVED), self.settings), "")

    def test_none_of_them_is_copied_on_a_reply(self):
        ticket = arrived_in(new_ticket(), ARRIVED)
        with graph_sends_as("sender@ucmerced.edu"):
            for address in ("I2G@g.ucmerced.edu", "Sender@UCMerced.edu", INTAKE, ARRIVED):
                expected = f"{address.lower()} is the helpdesk's own address: it is never copied on a reply."
                with self.subTest(address), self.assertRaisesMessage(replies.ReplyRefused, expected):
                    replies.parse_cc(f"kim@example.org, {address}", ticket)
        self.assertEqual(replies.parse_cc(f"kim@example.org, {ARRIVED}"), ["kim@example.org", ARRIVED])  # elsewhere

    def test_the_acknowledgement_skips_them(self):
        for address in (INTAKE, ARRIVED):
            ticket = arrived_in(new_ticket(requester_email=address), ARRIVED, auth_summary={"dmarc": "pass"})
            with self.subTest(address), self.captureOnCommitCallbacks(execute=True):
                self.assertIsNone(acknowledgement.queue_acknowledgement(ticket, ticket.messages.get(), self.settings))
        person = arrived_in(new_ticket(), ARRIVED, auth_summary={"dmarc": "pass"})
        with self.captureOnCommitCallbacks(execute=True):
            self.assertIsNotNone(acknowledgement.queue_acknowledgement(person, person.messages.get(), self.settings))


class ReplyToTests(JobTestCase):
    def reply_on(self, ticket):
        with self.captureOnCommitCallbacks(execute=True):
            message = outbound.queue_reply(ticket, actor=self.agent, body="See you there.")
        return message, claimed(BackgroundJob.objects.get(dedupe_key=f"reply:{message.pk}"))

    def test_answers_go_to_the_mailbox_the_requester_wrote_to(self):
        ticket = receive(corpus.message(), reader=FakeReader())  # it arrived in the site's mailbox

        message, job = self.reply_on(ticket)
        email = self.run_job(job).call_args.args[0]

        self.assertEqual((message.from_address, email.reply_to), (FROM, (corpus.SITE,)))

    def test_none_when_that_mailbox_is_the_from_address(self):
        ticket = arrived_in(new_ticket(subject="Judging"), corpus.SITE)
        message, job = self.reply_on(ticket)
        TicketMessage.objects.filter(pk=message.pk).update(from_address=corpus.SITE.upper())

        email = self.run_job(job).call_args.args[0]

        self.assertEqual(email.reply_to, ())
