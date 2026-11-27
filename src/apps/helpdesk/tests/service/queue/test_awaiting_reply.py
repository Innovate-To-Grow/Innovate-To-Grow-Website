"""Tickets awaiting a staff reply (``outbound.activity.awaiting_reply``): a person's open ticket, not waiting for the
requester, whose requester wrote after the last staff reply or that nobody answered yet. A failed reply or the
automatic acknowledgement is no answer. The sidebar's Helpdesk badge counts them (one query, cached briefly; "99+"
above 99, nothing for a non-Admin or when counting fails) and the queue's "Awaiting Reply" view lists them."""

import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.event.tests.helpers import make_member

from ....admin.tickets import filters as badge
from ....models import Ticket, TicketMessage
from ....services.outbound import activity
from ...helpers import helpdesk_staff
from ...tickets.test_tickets import new_ticket
from .support import QueueCase

Kind, Delivery, Status = TicketMessage.Kind, TicketMessage.Delivery, Ticket.Status


def message(ticket, kind, minutes_ago, **values) -> TicketMessage:
    at = timezone.now() - timedelta(minutes=minutes_ago)
    return TicketMessage.objects.create(ticket=ticket, kind=kind, occurred_at=at, **values)


def asked(subject="Asked", minutes_ago=30, **values) -> Ticket:
    """A person's ticket whose requester wrote ``minutes_ago``."""
    ticket = new_ticket(subject=subject, **values)
    message(ticket, Kind.CUSTOMER, minutes_ago)
    return ticket


def awaiting() -> set[str]:
    return set(activity.awaiting_reply().values_list("subject", flat=True))


class AwaitingReplyTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_new_ticket_nobody_answered_awaits_a_reply(self):
        asked("New one")
        new_ticket(subject="No message at all", status=Status.OPEN)

        self.assertEqual(awaiting(), {"New one", "No message at all"})

    def test_the_requester_writing_after_the_last_staff_reply_awaits_one_again(self):
        ticket = asked("Answered, then asked again", minutes_ago=60, status=Status.OPEN)
        message(ticket, Kind.REPLY, 30, delivery_status=Delivery.SENT)
        message(ticket, Kind.CUSTOMER, 10)

        self.assertEqual(awaiting(), {"Answered, then asked again"})

    def test_a_ticket_staff_answered_last_does_not(self):
        for status in (Delivery.SENT, Delivery.QUEUED, Delivery.UNCERTAIN):
            ticket = asked(f"Answered {status}", status=Status.OPEN)
            message(ticket, Kind.REPLY, 5, delivery_status=status)

        self.assertEqual(awaiting(), set())

    def test_a_failed_reply_or_the_acknowledgement_is_no_answer(self):
        failed = asked("Failed reply")
        message(failed, Kind.REPLY, 5, delivery_status=Delivery.FAILED)
        acknowledged = asked("Acknowledged")
        message(acknowledged, Kind.REPLY, 5, automatic=True, delivery_status=Delivery.SENT)
        noted = asked("Only a note")
        message(noted, Kind.NOTE, 5)

        self.assertEqual(awaiting(), {"Failed reply", "Acknowledged", "Only a note"})

    def test_internal_hold_counts_but_waiting_for_the_requester_does_not(self):
        asked("Internal", status=Status.PENDING_INTERNAL)
        asked("Waiting for them", status=Status.PENDING_CUSTOMER)

        self.assertEqual(awaiting(), {"Internal"})

    def test_done_merged_spam_and_automated_tickets_never_count(self):
        for status in (Status.RESOLVED, Status.CLOSED, Status.MERGED, Status.SPAM):
            asked(f"Done {status}", status=status)
        asked("Automated", automated=True)

        self.assertEqual(awaiting(), set())

    def test_the_count_is_one_query_and_shared_briefly(self):
        asked("One")
        asked("Two")

        with self.assertNumQueries(1):
            self.assertEqual(activity.awaiting_reply_count(), 2)
        asked("Three")
        with self.assertNumQueries(0):
            self.assertEqual(activity.awaiting_reply_count(), 2)
        with self.assertNumQueries(1):
            self.assertEqual(activity.awaiting_reply_count(fresh=True), 3)
        self.assertEqual(cache.get(activity.AWAITING_CACHE_KEY), 3)


class BadgeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def badge(self, user) -> str:
        request = self.factory.get("/admin/")
        request.user = user
        return badge.awaiting_reply_badge(request)

    def test_nothing_for_anyone_but_an_admin(self):
        asked()

        self.assertEqual(self.badge(AnonymousUser()), "")
        self.assertEqual(self.badge(make_member(email="pat@example.org")), "")

    def test_the_count_for_an_admin_and_nothing_at_zero(self):
        agent = helpdesk_staff()
        self.assertEqual(self.badge(agent), "")

        asked("One")
        asked("Two")
        cache.clear()

        self.assertEqual(self.badge(agent), "2")

    def test_more_than_99_shows_99_plus(self):
        with patch.object(activity, "awaiting_reply_count", return_value=150):
            self.assertEqual(self.badge(helpdesk_staff()), "99+")

    def test_a_count_that_fails_shows_nothing_and_is_logged(self):
        with (
            patch.object(activity, "awaiting_reply_count", side_effect=RuntimeError("database away")),
            self.assertLogs("apps.helpdesk.admin.tickets.filters", "ERROR") as logged,
        ):
            self.assertEqual(self.badge(helpdesk_staff()), "")
        self.assertIn("Could not count", logged.output[0])


class AwaitingViewTests(QueueCase):
    def test_the_view_lists_only_tickets_awaiting_a_reply(self):
        asked("Waiting on us")
        answered = asked("Answered")
        message(answered, Kind.REPLY, 5, delivery_status=Delivery.SENT)

        self.assertEqual(self.listed("reply=awaiting"), ["Waiting on us"])
        self.assertEqual(set(self.listed()), {"Waiting on us", "Answered"})

    def helpdesk_group(self, response) -> dict:
        return next(group for group in response.context["sidebar_navigation"] if group["title"] == "Helpdesk")

    def test_the_sidebar_shows_the_count_on_helpdesk_and_lights_awaiting_reply(self):
        for number in range(3):
            asked(f"Asked {number}")

        response = self.client.get(f"{reverse('admin:helpdesk_ticket_changelist')}?reply=awaiting")

        self.assertEqual(response.status_code, 200)
        group = self.helpdesk_group(response)
        self.assertEqual(str(group["badge_callback"]), "3")
        html = response.content.decode()
        self.assertRegex(html, re.compile(r"Helpdesk\s*<span[^>]*>\s*3\s*</span>"))
        items = {item["title"]: item for item in group["items"]}
        self.assertEqual(items["Awaiting Reply"]["link"], "/admin/helpdesk/ticket/?reply=awaiting")
        self.assertTrue(items["Awaiting Reply"]["active"])
        self.assertFalse(items["Queue"]["active"])

    def test_the_plain_queue_lights_queue_not_awaiting_reply(self):
        response = self.get()

        items = {item["title"]: item for item in self.helpdesk_group(response)["items"]}
        self.assertTrue(items["Queue"]["active"])
        self.assertFalse(items["Awaiting Reply"]["active"])
