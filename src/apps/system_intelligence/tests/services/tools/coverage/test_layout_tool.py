import asyncio
import datetime

from django.core.cache import cache
from django.test import TransactionTestCase

from apps.cms.models import (
    FooterContent,
    Menu,
)
from apps.event.tests.helpers import (
    make_event,
    make_ticket,
)
from apps.mail.models import EmailCampaign, RecipientLog
from apps.system_intelligence.services import tools as si_tools


class LayoutToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.menu = Menu.objects.create(
            name="main", display_name="Main", is_active=True, items=[{"title": "Home", "url": "/"}]
        )
        Menu.objects.create(name="footer-nav", display_name="Footer", is_active=False, items=[])

    def test_search_menus_filters_by_name_and_active(self):
        # layout.py line 13 (wrapper) + 34/37-38/39-41 filter branches.
        result = asyncio.run(si_tools.search_menus(name="main", is_active=True))
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["name"], "main")

    def test_search_menus_inactive_only(self):
        result = asyncio.run(si_tools.search_menus(is_active=False))
        names = {row["name"] for row in result["rows"]}
        self.assertIn("footer-nav", names)
        self.assertNotIn("main", names)

    def test_find_menu_by_id(self):
        # layout.py line 49: menu_id branch.
        result = asyncio.run(si_tools.get_menu_detail(menu_id=str(self.menu.pk)))
        self.assertEqual(result["menu"]["name"], "main")

    def test_find_menu_without_args_returns_tool_error(self):
        # layout.py line 52: ActionRequestError surfaced.
        result = asyncio.run(si_tools.get_menu_detail())
        self.assertIn("Provide menu_id or name", result["result"])

    def test_footer_detail_by_id(self):
        # layout.py line 67: footer_id branch.
        footer = FooterContent.objects.create(
            slug="main-footer", name="Main Footer", is_active=True, content={"columns": []}
        )
        result = asyncio.run(si_tools.get_footer_content_detail(footer_id=str(footer.pk)))
        self.assertEqual(result["footer"]["slug"], "main-footer")

    def test_footer_detail_by_slug(self):
        # layout.py line 69: slug branch.
        FooterContent.objects.create(slug="alt-footer", name="Alt", is_active=False, content={})
        result = asyncio.run(si_tools.get_footer_content_detail(slug="alt-footer"))
        self.assertEqual(result["footer"]["name"], "Alt")

    def test_footer_detail_fallback_latest(self):
        # layout.py line 73: active_only False -> latest by updated_at.
        footer = FooterContent.objects.create(slug="latest-footer", name="Latest", is_active=False, content={})
        result = asyncio.run(si_tools.get_footer_content_detail(active_only=False))
        self.assertEqual(result["footer"]["id"], str(footer.pk))


class MailToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.campaign = EmailCampaign.objects.create(name="Spring Blast", subject="Hello", body="Body")
        RecipientLog.objects.create(
            campaign=self.campaign, email_address="ok@example.com", recipient_name="OK", status="sent"
        )
        RecipientLog.objects.create(
            campaign=self.campaign,
            email_address="bad@example.com",
            recipient_name="Bad",
            status="failed",
            error_message="Rejected",
        )

    def test_recipient_logs_filtered_by_status_and_email(self):
        # mail.py lines 65/67: status + email filters.
        result = asyncio.run(
            si_tools.get_campaign_recipient_logs(campaign_name="Spring", status="failed", email="bad@example.com")
        )
        self.assertEqual(result["recipient_logs"]["total"], 1)
        self.assertEqual(result["recipient_logs"]["rows"][0]["email_address"], "bad@example.com")

    def test_find_campaign_by_name_branch(self):
        # mail.py line 38: campaign_name branch resolves the campaign.
        result = asyncio.run(si_tools.get_failed_recipient_report(campaign_name="Spring"))
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["campaign"]["name"], "Spring Blast")

    def test_find_campaign_without_args_returns_tool_error(self):
        # mail.py line 39: ActionRequestError surfaced as tool output.
        result = asyncio.run(si_tools.get_campaign_recipient_logs())
        self.assertIn("Provide campaign_id or campaign_name", result["result"])


class EventLookupToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.event = make_event(name="Demo Day", date=datetime.date(2026, 5, 1))
        self.event.slug = "demo-day"
        self.event.save()
        make_ticket(self.event, name="General")

    def test_find_event_by_slug(self):
        # lookup.py lines 39-40: slug branch.
        result = asyncio.run(si_tools.get_event_detail(slug="demo-day"))
        self.assertEqual(result["event"]["name"], "Demo Day")

    def test_find_event_by_name(self):
        # lookup.py lines 41-42: name icontains branch ordered by -date.
        result = asyncio.run(si_tools.get_event_detail(name="Demo"))
        self.assertEqual(result["event"]["slug"], "demo-day")

    def test_find_event_without_args_returns_tool_error(self):
        # lookup.py line 43: ActionRequestError surfaced.
        result = asyncio.run(si_tools.get_event_detail())
        self.assertIn("Provide event_id, slug, or name", result["result"])
