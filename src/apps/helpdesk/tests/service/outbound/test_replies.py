"""Replies to the requester: when they are refused (shadow mode, merged, automated or spam, an address that cannot be
mailed or is the site's own, jobs off, an empty or too long text, a bad Cc), and what a queued reply stores, records
and enqueues; and which message a reply quotes."""

from django.core.cache import cache
from django.test import TestCase, override_settings

from ....models import HelpdeskSettings, TicketEvent, TicketMessage
from ....services.outbound import replies
from ...helpers.service import Status, new_ticket, sending_settings

Kind = TicketEvent.Kind
Delivery = TicketMessage.Delivery


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class CanReplyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.settings = sending_settings()

    def test_a_persons_open_ticket_can_be_answered(self):
        self.assertEqual(replies.can_reply(new_ticket(), self.settings), "")

    def test_refusals(self):
        cases = (
            ("shadow mode", new_ticket(), HelpdeskSettings(shadow_mode=True), "Shadow mode is on"),
            ("merged", new_ticket(status=Status.MERGED), self.settings, "This ticket was merged"),
            ("automated", new_ticket(automated=True, status=Status.CLOSED), self.settings, "Automated mail and spam"),
            ("spam", new_ticket(status=Status.SPAM), self.settings, "Automated mail and spam"),
            ("no address", new_ticket(requester_email=""), self.settings, "cannot be mailed"),
            ("display name", new_ticket(requester_email="Pat <pat@example.org>"), self.settings, "cannot be mailed"),
            ("own address", new_ticket(requester_email="I2G@g.ucmerced.edu"), self.settings, "helpdesk's own address"),
        )
        for name, ticket, settings, reason in cases:
            with self.subTest(name):
                self.assertIn(reason, replies.can_reply(ticket, settings))

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    def test_jobs_off_refuses(self):
        self.assertIn("Background jobs are off", replies.can_reply(new_ticket(), self.settings))

    def test_the_saved_settings_are_read_when_none_are_given(self):
        self.assertEqual(replies.can_reply(new_ticket()), "")
        HelpdeskSettings.objects.update(shadow_mode=True)
        self.assertIn("Shadow mode", replies.can_reply(new_ticket()))


class ParseCcTests(TestCase):
    def test_commas_and_semicolons_lowercased_and_deduplicated(self):
        self.assertEqual(
            replies.parse_cc(" Kim@Example.org; lee@example.org, kim@example.org ,, "),
            ["kim@example.org", "lee@example.org"],
        )
        self.assertEqual(replies.parse_cc(""), [])
        self.assertEqual(replies.parse_cc(None), [])

    def test_too_many_or_not_plain_addresses_are_refused(self):
        with self.assertRaisesMessage(replies.ReplyRefused, "At most 10 Cc addresses."):
            replies.parse_cc(",".join(f"p{n}@example.org" for n in range(11)))
        for bad in ("not-an-address", "Kim <kim@example.org>", "kim@example.org\r\nBcc: x@example.org"):
            with self.subTest(bad), self.assertRaisesMessage(replies.ReplyRefused, "Use plain email addresses"):
                replies.parse_cc(bad)
