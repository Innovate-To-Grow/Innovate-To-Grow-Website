from unittest.mock import patch

from django.test import TestCase

from apps.core.tests.services.inbound import samples
from apps.helpdesk.tests.replies.test_replies_and_notices import SiteMailMixin, Status

from ...models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ...services.tickets import shadow


class LoopTests(SiteMailMixin, TestCase):
    def test_an_automatic_reply_to_an_automatic_reply_joins_its_thread_and_changes_nothing(self):
        self.sent("alex.kim@contoso.example")
        first, _row = self.receive(samples.exchange_oof_english())
        before = Ticket.objects.get(pk=first.pk)

        joined, row = self.receive(samples.auto_reply_to_auto_reply())

        self.assertEqual(joined.pk, first.pk)
        self.assertEqual((row.classification, row.result["rule"]), ("auto_reply", "references"))
        joined.refresh_from_db()
        self.assertEqual(
            (joined.status, joined.unread, joined.last_activity_at, joined.closed_at),
            (Status.CLOSED, False, before.last_activity_at, before.closed_at),
        )
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertTrue(joined.events.filter(kind=TicketEvent.Kind.AUTOMATED_MESSAGE).exists())

    def test_no_automatic_answer_is_ever_allowed_for_automated_mail(self):
        self.sent("alex.kim@contoso.example")
        self.receive(samples.exchange_oof_english())
        self.receive(samples.auto_reply_to_auto_reply())
        settings = HelpdeskSettings.objects.create(shadow_mode=False)

        with patch.object(shadow, "SENDING_IMPLEMENTED", True):
            self.assertTrue(shadow.sending_allowed(settings))
            for message in TicketMessage.objects.all():
                self.assertFalse(shadow.automatic_reply_allowed(message, settings))

    def test_a_persons_message_may_be_answered_only_once_sending_exists_and_rfc_3834_allows(self):
        self.sent("morgan.diaz@acme-industries.example")
        crm, _row = self.receive(samples.crm_reply_about_judging())
        plain, _row = self.receive(
            samples.message(
                sender="Pat Doe <pat@example.org>",
                subject="Judging",
                text="Can I judge this year?",
                message_id="<plain-1@example.org>",
                reply=False,
            )
        )
        settings = HelpdeskSettings.objects.create(shadow_mode=False)
        crm_message, plain_message = crm.messages.get(), plain.messages.get()

        self.assertFalse(shadow.automatic_reply_allowed(plain_message, settings))  # this release sends nothing
        with patch.object(shadow, "SENDING_IMPLEMENTED", True):
            self.assertTrue(shadow.automatic_reply_allowed(plain_message, settings))
            self.assertFalse(shadow.automatic_reply_allowed(crm_message, settings))

    def test_no_automatic_answer_when_a_message_looks_automated_or_sits_on_spam(self):
        # A responder that marks nothing (no Auto-Submitted, no prefix) is a "person" with a hint: never answered.
        unmarked, _row = self.receive(
            samples.message(
                sender="Quinn Lee <quinn.lee@example.org>",
                subject="Hello",
                text="I am out of the office until Monday.",
                message_id="<unmarked-1@example.org>",
                reply=False,
            )
        )
        plain, _row = self.receive(
            samples.message(
                sender="Pat Doe <pat@example.org>",
                subject="Judging",
                text="Can I judge this year?",
                message_id="<plain-2@example.org>",
                reply=False,
            )
        )
        settings = HelpdeskSettings.objects.create(shadow_mode=False)

        with patch.object(shadow, "SENDING_IMPLEMENTED", True):
            self.assertEqual((unmarked.classification, unmarked.automated), ("human", False))
            self.assertFalse(shadow.automatic_reply_allowed(unmarked.messages.get(), settings))
            self.assertTrue(shadow.automatic_reply_allowed(plain.messages.get(), settings))
            Ticket.objects.filter(pk=plain.pk).update(status=Status.SPAM)  # staff marked it spam
            self.assertFalse(shadow.automatic_reply_allowed(TicketMessage.objects.get(ticket_id=plain.pk), settings))
