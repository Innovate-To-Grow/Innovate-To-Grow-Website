"""What a reply says, and when it is refused as a double. Staff's text is sent as written: a line break typed as CRLF
counts once toward the limit, and only a personal sign-in link is removed (a long ordinary link, such as a Microsoft
Forms address, stays whole). The same reply again by the same author within ten minutes is refused unless the first
one did not go out. The email's text part quotes the requester's message under a date in the site's time zone."""

from datetime import UTC, datetime, timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from ....models import TicketMessage
from ....services import outbound
from ....services.outbound import compose
from ... import corpus
from ...helpers import helpdesk_staff, make_admin
from ...helpers.service import new_ticket, sending_settings

Delivery = TicketMessage.Delivery
FORMS = (
    "https://forms.office.com/Pages/ResponsePage.aspx?id="
    "DQSIkWdsW0yxEjajBLZtrQAAAAAAAAAAAAMAAJ1vB0FUQ0FUMkNWTlpHNjJWWDg0RlJUT0hPTy4u"
)
DOUBLE = "This reply was already sent a moment ago (see the timeline); it was not sent twice."


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class ReplyTextTests(TestCase):
    def setUp(self):
        cache.clear()
        sending_settings()
        self.agent = helpdesk_staff()
        self.ticket = new_ticket(participants=["pat@example.org"])

    def reply(self, body="Hello Pat, the showcase starts at 10.", actor=None):
        with self.captureOnCommitCallbacks(execute=True):
            return outbound.queue_reply(self.ticket, actor=actor or self.agent, body=body)

    def replies(self):
        return TicketMessage.objects.filter(kind=TicketMessage.Kind.REPLY)

    def test_only_a_personal_sign_in_link_is_removed(self):
        token = "R" * 64  # a long run of letters is no link: kept too
        message = self.reply(f"Fill in {FORMS} (ref {token}); your link: {corpus.LOGIN_LINK} {corpus.UNSUBSCRIBE_LINK}")

        self.assertEqual(
            message.body_text,
            f"Fill in {FORMS} (ref {token}); your link: [sign-in link removed] [sign-in link removed]",
        )

    def test_a_crlf_line_break_counts_once(self):
        body = ("x" * 99 + "\r\n") * 200  # 20,200 characters as posted, 19,999 once the breaks are one each

        message = self.reply(body)

        self.assertEqual(len(message.body_text), 19999)
        self.assertNotIn("\r", message.body_text)
        self.assertEqual(len(self.reply("y" * 20000).body_text), 20000)
        with self.assertRaisesMessage(
            outbound.ReplyRefused, "A reply can be at most 20,000 characters (20,001 written)."
        ):
            self.reply("z" * 20001)

    def test_the_same_reply_again_within_ten_minutes_is_refused(self):
        first = self.reply()
        for status in (Delivery.QUEUED, Delivery.SENT):
            TicketMessage.objects.filter(pk=first.pk).update(delivery_status=status)
            with self.subTest(status), self.assertRaisesMessage(outbound.ReplyRefused, DOUBLE):
                self.reply("  Hello Pat, the showcase starts at 10.\r\n")  # the same text once cleaned
        self.assertEqual(self.replies().count(), 1)
        self.assertEqual(self.ticket.events.filter(kind="reply").count(), 1)

    def test_a_reply_that_did_not_go_out_may_be_sent_again_at_once(self):
        self.reply()
        for status in (Delivery.FAILED, Delivery.UNCERTAIN):
            self.replies().update(delivery_status=status)  # every earlier copy did not go out (or is not confirmed)
            with self.subTest(status):
                self.assertEqual(self.reply().delivery_status, Delivery.QUEUED)
        self.assertEqual(self.replies().count(), 3)

    def test_ten_minutes_later_another_author_or_another_text_is_no_double(self):
        first = self.reply()
        self.reply(actor=make_admin(email="kim@example.com"))
        self.reply("Hello Pat, the showcase starts at 11.")
        TicketMessage.objects.filter(pk=first.pk).update(
            delivery_status=Delivery.SENT, occurred_at=timezone.now() - timedelta(minutes=11)
        )
        self.reply()

        self.assertEqual(self.replies().count(), 4)


@override_settings(TIME_ZONE="America/Los_Angeles")
class QuotedTextTests(TestCase):
    def quoted(self, when, **values):
        values.setdefault("from_name", "Pat Doe")
        return TicketMessage(
            ticket=new_ticket(),
            kind=TicketMessage.Kind.CUSTOMER,
            from_address="pat@example.org",
            occurred_at=when,
            body_text="When does it start?\nAnd where?",
            **values,
        )

    def test_the_text_part_quotes_the_message_under_a_local_date_with_its_zone(self):
        ticket = new_ticket()
        winter = self.quoted(datetime(2026, 11, 11, 10, 0, tzinfo=UTC))
        summer = self.quoted(datetime(2026, 7, 1, 17, 30, tzinfo=UTC), from_name="")

        text = compose.reply_text("See you there.", ticket, winter)

        self.assertTrue(text.startswith(f"See you there.\n\n--\n{compose.footer(ticket)}\n\n"))
        self.assertTrue(text.endswith("On Nov 11, 2026 02:00 PST, Pat Doe wrote:\n> When does it start?\n> And where?"))
        self.assertIn("On Jul 01, 2026 10:30 PDT, pat@example.org wrote:", compose.reply_text("Hi", ticket, summer))
        html = compose.reply_html("See you there.", ticket, winter)
        self.assertIn("Nov 11, 2026 02:00 PST", html)
        self.assertEqual(html.count("When does it start?"), 1)  # quoted once, not again in the body

    def test_nothing_is_quoted_without_a_message_or_its_text(self):
        ticket = new_ticket()
        purged = self.quoted(timezone.now(), body_purged_at=timezone.now())

        for quoted in (None, purged):
            with self.subTest(quoted):
                self.assertNotIn("wrote:", compose.reply_text("Hi", ticket, quoted))
