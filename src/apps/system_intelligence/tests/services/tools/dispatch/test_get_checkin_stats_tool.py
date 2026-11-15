from django.test import TestCase

from apps.event.models import CheckIn, CheckInRecord
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.system_intelligence.services.query_tools.tool_modules.domains.events import get_checkin_stats


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
