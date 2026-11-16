"""Coverage tests for the system_intelligence tools batch.

These exercise the async agent tool wrappers (legacy, exports, approval) plus the
domain/cms/event read helpers and the shared query helpers. External LLM/agent
machinery is never invoked: the read tools run real ORM queries through
``run_action_service_async`` and the legacy tools dispatch through the local
``TOOL_REGISTRY``.
"""

import asyncio
import datetime

from django.core.cache import cache
from django.db.models import QuerySet
from django.test import SimpleTestCase, TransactionTestCase

from apps.authn.models import ContactEmail, ContactPhone
from apps.cms.models import (
    Menu,
    PageView,
)
from apps.event.tests.helpers import (
    make_event,
    make_member,
    make_registration,
    make_ticket,
)
from apps.mail.models import EmailCampaign, RecipientLog
from apps.system_intelligence.services import tools as si_tools
from apps.system_intelligence.services.actions.exceptions import ActionRequestError
from apps.system_intelligence.services.query_tools.tool_modules.helpers import MAX_ROWS
from apps.system_intelligence.services.tools.query_helpers import (
    apply_date_range,
    bounded_limit,
    require_one,
)


class QueryHelpersTests(SimpleTestCase):
    """Pure helpers — no DB rows required for the targeted branches."""

    def test_bounded_limit_falls_back_to_default_on_bad_value(self):
        # Lines 13-14: int("abc") raises ValueError -> value = default.
        self.assertEqual(bounded_limit("abc"), 20)

    def test_bounded_limit_clamps_to_max_rows(self):
        self.assertEqual(bounded_limit(10**9), MAX_ROWS)

    def test_require_one_raises_when_queryset_empty(self):
        # Line 35: missing object surfaces a labelled ActionRequestError.
        empty = Menu.objects.none()
        with self.assertRaises(ActionRequestError) as cm:
            require_one(empty, "Widget")
        self.assertEqual(str(cm.exception), "Widget was not found.")

    def test_apply_date_range_filters_both_bounds(self):
        # Lines 41 and 43: each branch appends a filter to the queryset.
        base = PageView.objects.all()
        filtered = apply_date_range(
            base, "timestamp", date_from="2025-01-01T00:00:00+00:00", date_to="2025-12-31T00:00:00+00:00"
        )
        self.assertIsInstance(filtered, QuerySet)
        where = str(filtered.query).lower()
        self.assertIn(">=", where)
        self.assertIn("<=", where)
        self.assertIsNot(filtered, base)


class MemberToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(
            email="ada@example.com",
            first_name="Ada",
            last_name="Lovelace",
            organization="Analytical Engines",
            title="Engineer",
        )
        ContactPhone.objects.create(
            member=self.member, phone_number="2095550100", region="1-US", subscribe=True, verified=True
        )

    def test_get_member_activity_summary_aggregates_domains(self):
        # members.py lines 122-131 + 42/50: activity summary via member_id lookup.
        event = make_event(name="Demo Day", date=datetime.date(2026, 5, 1))
        ticket = make_ticket(event, name="General")
        make_registration(self.member, event, ticket, attendee_email="ada@example.com")
        campaign = EmailCampaign.objects.create(name="Invite", subject="Join", body="Hi")
        RecipientLog.objects.create(
            campaign=campaign, member=self.member, email_address="ada@example.com", status="sent"
        )
        PageView.objects.create(path="/event", member=self.member, session_key="s1")

        summary = asyncio.run(si_tools.get_member_activity_summary(member_id=str(self.member.pk)))

        self.assertEqual(summary["member"]["first_name"], "Ada")
        self.assertEqual(summary["registration_count"], 1)
        self.assertEqual(summary["page_view_count"], 1)
        self.assertEqual(summary["campaign_delivery_breakdown"], [{"status": "sent", "count": 1}])
        self.assertEqual(len(summary["recent_registrations"]), 1)
        self.assertEqual(summary["recent_page_views"][0]["path"], "/event")

    def test_find_member_by_email_branch(self):
        # members.py line 52 (covered indirectly) + 50 via member_id path here.
        detail = asyncio.run(si_tools.get_member_activity_summary(email="ada@example.com"))
        self.assertEqual(detail["member"]["last_name"], "Lovelace")

    def test_find_member_without_args_returns_tool_error(self):
        # members.py line 53: ActionRequestError caught and surfaced as tool output.
        result = asyncio.run(si_tools.get_member_detail())
        self.assertIn("Tool error", result["result"])
        self.assertIn("Provide member_id or email", result["result"])

    def test_search_contact_info_phone_only_drops_emails(self):
        # members.py lines 98-100: phone filter set, email side -> none().
        result = asyncio.run(si_tools.search_contact_info(phone="2095550100"))
        self.assertEqual(result["emails"]["total"], 0)
        self.assertEqual(result["phones"]["total"], 1)
        self.assertEqual(result["phones"]["rows"][0]["phone_number"], "2095550100")

    def test_search_contact_info_subscribed_and_verified_filters(self):
        # members.py lines 101-106: subscribed + verified branches on both querysets.
        ContactEmail.objects.filter(member=self.member).update(subscribe=True, verified=True)
        result = asyncio.run(si_tools.search_contact_info(subscribed=True, verified=True))
        self.assertGreaterEqual(result["emails"]["total"], 1)
        self.assertEqual(result["phones"]["total"], 1)

        none_result = asyncio.run(si_tools.search_contact_info(subscribed=False, verified=False))
        self.assertEqual(none_result["emails"]["total"], 0)
        self.assertEqual(none_result["phones"]["total"], 0)
