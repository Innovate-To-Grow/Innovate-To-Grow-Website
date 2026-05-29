import datetime
from unittest.mock import patch

from django.test import TestCase

from core.services.db_tools.executor import execute_tool
from core.services.db_tools.tool_modules.events import get_checkin_stats, get_event_registrations, search_events
from core.services.db_tools.tool_modules.members import count_members, search_members
from event.models import CheckIn, CheckInRecord
from event.tests.helpers import make_event, make_member, make_registration, make_ticket


class ExecuteToolDispatchTests(TestCase):
    def test_dispatches_to_registered_tool(self):
        result = execute_tool({"name": "count_members", "toolUseId": "t1", "input": {}})
        self.assertIn("Count:", result)

    def test_unknown_tool_returns_error_message(self):
        result = execute_tool({"name": "nonexistent_tool", "toolUseId": "t1", "input": {}})
        self.assertEqual(result, "Unknown tool: nonexistent_tool")

    def test_empty_name_returns_unknown(self):
        result = execute_tool({"name": "", "toolUseId": "t1", "input": {}})
        self.assertEqual(result, "Unknown tool: ")

    def test_missing_name_returns_unknown(self):
        result = execute_tool({"toolUseId": "t1", "input": {}})
        self.assertEqual(result, "Unknown tool: ")

    @patch("core.services.db_tools.executor.TOOL_REGISTRY", {"boom": lambda p: 1 / 0})
    def test_exception_returns_tool_error(self):
        result = execute_tool({"name": "boom", "toolUseId": "t1", "input": {}})
        self.assertIn("Tool error:", result)


class SearchMembersToolTests(TestCase):
    def setUp(self):
        self.alice = make_member(email="alice@corp.com", first_name="Alice", last_name="Smith")
        self.alice.organization = "WidgetCo"
        self.alice.is_staff = True
        self.alice.save()
        self.bob = make_member(email="bob@corp.com", first_name="Bob", last_name="Jones")
        self.bob.organization = "Gadgets Inc"
        self.bob.save()

    def test_returns_all_with_no_filters(self):
        result = search_members({})
        self.assertIn("Alice", result)
        self.assertIn("Bob", result)

    def test_filters_by_name(self):
        result = search_members({"name": "Alice"})
        self.assertIn("Alice", result)
        self.assertNotIn("Bob", result)

    def test_filters_by_email(self):
        result = search_members({"email": "bob@corp"})
        self.assertIn("Bob", result)
        self.assertNotIn("Alice", result)

    def test_filters_by_organization(self):
        result = search_members({"organization": "Widget"})
        self.assertIn("Alice", result)
        self.assertNotIn("Bob", result)

    def test_filters_by_is_staff(self):
        result = search_members({"is_staff": True})
        self.assertIn("Alice", result)
        self.assertNotIn("Bob", result)

    def test_filters_by_is_active_false(self):
        self.bob.is_active = False
        self.bob.save()
        result = search_members({"is_active": False})
        self.assertIn("Bob", result)
        self.assertNotIn("Alice", result)


class CountMembersToolTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="c1@test.com", first_name="C1", last_name="M")
        self.m1.is_staff = True
        self.m1.save()
        self.m2 = make_member(email="c2@test.com", first_name="C2", last_name="M")
        self.m3 = make_member(email="c3@test.com", first_name="C3", last_name="M")
        self.m3.is_active = False
        self.m3.save()

    def test_counts_all(self):
        result = count_members({})
        self.assertIn("Count:", result)
        self.assertIn("3", result)

    def test_counts_staff_only(self):
        result = count_members({"is_staff": True})
        self.assertEqual(result, "Count: 1")

    def test_counts_active_only(self):
        result = count_members({"is_active": True})
        self.assertEqual(result, "Count: 2")


class SearchEventsToolTests(TestCase):
    def setUp(self):
        self.e1 = make_event(name="Spring Showcase", date=datetime.date(2025, 4, 10))
        self.e2 = make_event(name="Fall Expo", date=datetime.date(2025, 10, 20), is_live=True)

    def test_returns_all_with_no_filters(self):
        result = search_events({})
        self.assertIn("Spring Showcase", result)
        self.assertIn("Fall Expo", result)

    def test_filters_by_name(self):
        result = search_events({"name": "Spring"})
        self.assertIn("Spring Showcase", result)
        self.assertNotIn("Fall Expo", result)

    def test_filters_by_is_live(self):
        result = search_events({"is_live": True})
        self.assertIn("Fall Expo", result)
        self.assertNotIn("Spring Showcase", result)

    def test_filters_by_date_range(self):
        result = search_events({"date_from": "2025-06-01"})
        self.assertIn("Fall Expo", result)
        self.assertNotIn("Spring Showcase", result)


class GetEventRegistrationsToolTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="r1@test.com", first_name="Reg", last_name="One")
        self.event = make_event(name="Demo Day")
        self.ticket = make_ticket(self.event)
        make_registration(self.m1, self.event, self.ticket, attendee_email="r1@test.com", attendee_first_name="Reg")

    def test_returns_registrations_for_event_name(self):
        result = get_event_registrations({"event_name": "Demo"})
        self.assertIn("Reg", result)

    def test_returns_registrations_for_event_id(self):
        result = get_event_registrations({"event_id": str(self.event.pk)})
        self.assertIn("Reg", result)

    def test_count_only_returns_count(self):
        result = get_event_registrations({"event_name": "Demo", "count_only": True})
        self.assertEqual(result, "Registration count: 1")


class GetCheckinStatsToolTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="ci1@test.com", first_name="Ci", last_name="One")
        self.event = make_event(name="Hackathon")
        self.ticket = make_ticket(self.event)
        self.reg = make_registration(self.m1, self.event, self.ticket)
        self.checkin = CheckIn.objects.create(event=self.event, name="Front Desk")
        CheckInRecord.objects.create(check_in=self.checkin, registration=self.reg)

    def test_returns_total_checkins(self):
        result = get_checkin_stats({"event_name": "Hackathon"})
        self.assertIn("Total check-ins: 1", result)

    def test_groups_by_station(self):
        result = get_checkin_stats({"event_name": "Hackathon"})
        self.assertIn("Front Desk", result)

    def test_empty_for_unknown_event(self):
        result = get_checkin_stats({"event_name": "Nonexistent"})
        self.assertIn("Total check-ins: 0", result)
