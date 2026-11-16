import asyncio
import datetime

from django.core.cache import cache
from django.test import TransactionTestCase
from django.utils import timezone

from apps.cms.models import (
    NewsArticle,
    NewsFeedSource,
)
from apps.event.tests.helpers import (
    make_event,
    make_member,
    make_registration,
    make_ticket,
)
from apps.system_intelligence.services import tools as si_tools


class RegistrationToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="ada@example.com", first_name="Ada", last_name="Lovelace")
        self.event = make_event(name="Demo Day", date=datetime.date(2026, 5, 1))
        self.ticket = make_ticket(self.event, name="General")
        self.registration = make_registration(
            self.member,
            self.event,
            self.ticket,
            attendee_email="ada@example.com",
            attendee_first_name="Ada",
            attendee_last_name="Lovelace",
            ticket_code="TICKET-XYZ",
        )

    def test_search_registrations_by_all_filters(self):
        # registrations.py lines 32/34/38: event_id, event_name, ticket_id filters.
        result = asyncio.run(
            si_tools.search_event_registrations(
                event_id=str(self.event.pk),
                event_name="Demo",
                email="ada@example.com",
                ticket_id=str(self.ticket.pk),
            )
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["attendee_email"], "ada@example.com")

    def test_registration_detail_by_ticket_code(self):
        # registrations.py lines 72-73: ticket_code branch.
        result = asyncio.run(si_tools.get_registration_detail(ticket_code="TICKET-XYZ"))
        self.assertEqual(result["registration"]["ticket_code"], "TICKET-XYZ")
        self.assertEqual(result["event"]["name"], "Demo Day")
        self.assertEqual(result["ticket"]["name"], "General")

    def test_registration_detail_without_args_returns_tool_error(self):
        # registrations.py line 75: ActionRequestError surfaced.
        result = asyncio.run(si_tools.get_registration_detail())
        self.assertIn("Provide registration_id or ticket_code", result["result"])


class NewsSourceToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml", is_active=True
        )
        NewsArticle.objects.create(
            source="ucm",
            source_guid="news-1",
            title="Award",
            source_url="https://example.com/news",
            published_at=timezone.now(),
        )

    def test_news_source_by_id(self):
        # news.py line 23: source_id branch.
        result = asyncio.run(si_tools.get_news_source_detail(source_id=str(self.source.pk)))
        self.assertEqual(result["source"]["source_key"], "ucm")

    def test_news_source_by_source_key(self):
        # news.py lines 25-26: source_key branch.
        result = asyncio.run(si_tools.get_news_source_detail(source_key="ucm"))
        self.assertEqual(result["source"]["name"], "UC Merced")
        self.assertEqual(result["article_count"], 1)

    def test_news_source_by_name(self):
        # news.py lines 27-28: name icontains branch.
        result = asyncio.run(si_tools.get_news_source_detail(name="Merced"))
        self.assertEqual(result["source"]["source_key"], "ucm")

    def test_news_source_without_args_returns_tool_error(self):
        # news.py line 29: ActionRequestError surfaced.
        result = asyncio.run(si_tools.get_news_source_detail())
        self.assertIn("Provide source_id, source_key, or name", result["result"])
