"""Two Admins answering the same ticket (every Admin works every ticket): a reply is held back when someone else
replied after the reply form was shown (``outbound.queue_reply(seen_at=…)`` raises ``ReplyCollision``, judged on the
locked ticket). The reply view brings the page back with the draft, a warning naming who replied, and "Send anyway",
which sends it from that fresh page. Your own earlier reply, a reply before the form was shown, a failed reply, and a
page without a usable "seen" time (an earlier release's, or a value that is no time) never hold a reply back."""

import re
from datetime import timedelta

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ....models import TicketMessage
from ....services import outbound
from ... import corpus
from ...helpers import FakeReader, helpdesk_staff, make_admin, receive
from ...helpers.service import Status, sending_settings

Kind, Delivery = TicketMessage.Kind, TicketMessage.Delivery


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class CollisionCase(TestCase):
    def setUp(self):
        cache.clear()
        sending_settings()
        self.agent = helpdesk_staff()
        self.other = make_admin(email="sam@example.com", first_name="Sam", last_name="Lead")
        self.ticket = receive(corpus.message(), reader=FakeReader())

    def other_reply(self, *, author=None, delivery=Delivery.SENT) -> TicketMessage:
        return TicketMessage.objects.create(
            ticket=self.ticket,
            kind=Kind.REPLY,
            author=author or self.other,
            from_name="Sam Lead",
            occurred_at=timezone.now(),
            body_text="Already answered.",
            delivery_status=delivery,
        )

    def replies(self, author):
        return TicketMessage.objects.filter(ticket=self.ticket, kind=Kind.REPLY, author=author)


class QueueReplyTests(CollisionCase):
    def queue(self, seen_at):
        return outbound.queue_reply(self.ticket, actor=self.agent, body="See you at 10.", seen_at=seen_at)

    def test_someone_elses_reply_after_the_form_was_shown_holds_this_one_back(self):
        seen = timezone.now() - timedelta(seconds=1)
        self.other_reply()

        with self.assertRaises(outbound.ReplyCollision) as raised:
            self.queue(seen)

        self.assertIn("Sam Lead replied to the requester at", str(raised.exception))
        self.assertEqual(raised.exception.by, "Sam Lead")
        self.assertFalse(self.replies(self.agent).exists())

    def test_own_earlier_reply_a_reply_before_the_form_and_a_failed_one_do_not(self):
        self.other_reply()
        seen = timezone.now()
        self.other_reply(author=self.agent)
        self.other_reply(delivery=Delivery.FAILED)

        self.queue(seen)

        self.assertEqual(self.replies(self.agent).filter(delivery_status=Delivery.QUEUED).count(), 1)

    def test_without_a_seen_time_there_is_no_check(self):
        self.other_reply()

        self.queue(None)

        self.assertTrue(self.replies(self.agent).filter(delivery_status=Delivery.QUEUED).exists())


class ReplyViewTests(CollisionCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.agent)
        self.url = reverse("admin:helpdesk_ticket_change", args=[self.ticket.pk])
        self.reply_url = reverse("admin:helpdesk_ticket_reply", args=[self.ticket.pk])

    def seen_on(self, response) -> str:
        found = re.search(r'<input type="hidden" name="seen" value="([^"]+)">', response.content.decode())
        self.assertIsNotNone(found)
        return found.group(1)

    def post(self, **data):
        data.setdefault("body", "The showcase starts at 10.")
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.reply_url, data)

    def test_the_form_carries_when_it_was_shown(self):
        before = timezone.now()

        response = self.client.get(self.url)

        seen = timezone.datetime.fromisoformat(self.seen_on(response))
        self.assertGreaterEqual(seen, before)
        self.assertEqual(response.context["helpdesk_reply_collision"], "")
        self.assertContains(response, "Send reply")

    def test_a_reply_after_the_page_was_opened_keeps_the_draft_and_asks_again(self):
        seen = self.seen_on(self.client.get(self.url))
        self.other_reply()

        response = self.post(seen=seen, cc="kim@example.org", status=Status.OPEN)

        self.assertRedirects(response, f"{self.url}#helpdesk-reply", fetch_redirect_response=False)
        self.assertFalse(self.replies(self.agent).exists())
        notes = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any(note.startswith("Your reply was not sent yet: Sam Lead replied") for note in notes))

        page = self.client.get(self.url)
        self.assertEqual(page.context["helpdesk_reply_body"], "The showcase starts at 10.")
        self.assertEqual(page.context["helpdesk_reply_cc"], "kim@example.org")
        self.assertEqual(page.context["helpdesk_reply_status"], Status.OPEN)
        self.assertIn("Sam Lead replied", page.context["helpdesk_reply_collision"])
        self.assertContains(page, "Send anyway")
        self.assertContains(page, "Your draft is below")

        self.post(seen=self.seen_on(page), cc="kim@example.org", status=Status.OPEN)

        sent = self.replies(self.agent).get()
        self.assertEqual(sent.body_text, "The showcase starts at 10.")
        self.assertEqual(sent.cc_addresses, ["kim@example.org"])

    def test_a_page_without_a_usable_seen_time_still_sends(self):
        self.other_reply()
        for index, data in enumerate(({}, {"seen": "yesterday"}, {"seen": "2026-02-30T10:00:00+00:00"})):
            with self.subTest(data=data):
                self.post(body=f"Reply number {index}.", **data)

                self.assertTrue(self.replies(self.agent).filter(body_text=f"Reply number {index}.").exists())

    def test_a_time_without_a_zone_is_not_used(self):
        self.other_reply()
        naive = (timezone.now() - timedelta(hours=1)).replace(tzinfo=None).isoformat()

        self.post(seen=naive)

        self.assertTrue(self.replies(self.agent).exists())
