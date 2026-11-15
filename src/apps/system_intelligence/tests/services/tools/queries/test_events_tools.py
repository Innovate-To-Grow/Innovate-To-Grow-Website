from django.test import TestCase

from apps.system_intelligence.services.query_tools.tool_modules.domains.events import (
    get_checkin_stats,
    get_event_registrations,
    search_events,
)
from apps.system_intelligence.services.query_tools.tool_modules.domains.mail import (
    get_campaign_stats,
    search_email_campaigns,
)


class EventsToolsTest(TestCase):
    def _make_event(self, name="Demo Day", date="2025-06-15", end_date=None):
        from apps.event.models import Event

        return Event.objects.create(
            name=name,
            slug=name.lower().replace(" ", "-"),
            date=date,
            end_date=end_date or date,
            location="Hall",
        )

    def _make_registration(self, event, email="ann@example.com"):
        from apps.authn.models import Member
        from apps.event.models import EventRegistration, Ticket

        member = Member.objects.create(first_name="Ann", last_name="Lee", organization="Acme")
        ticket = Ticket.objects.create(event=event, name="General", order=1)
        return EventRegistration.objects.create(
            member=member,
            event=event,
            ticket=ticket,
            attendee_first_name="Ann",
            attendee_last_name="Lee",
            attendee_email=email,
        )

    def test_search_events_filters(self):
        self._make_event()
        result = search_events({"name": "Demo", "date_from": "2000-01-01", "date_to": "2999-01-01"})
        self.assertIn("Demo Day", result)
        self.assertIn('"end_date": "2025-06-15"', result)
        self.assertNotIn('"is_live"', result)

    def test_search_events_date_window_matches_overlapping_event_ranges(self):
        self._make_event("Overlapping", date="2025-05-30", end_date="2025-06-03")
        self._make_event("Before", date="2025-05-01", end_date="2025-05-31")
        self._make_event("After", date="2025-06-02", end_date="2025-06-10")

        result = search_events({"date_from": "2025-06-01", "date_to": "2025-06-01"})

        self.assertIn("Overlapping", result)
        self.assertNotIn("Before", result)
        self.assertNotIn("After", result)

    def test_search_events_resolves_transitional_null_end_date(self):
        from apps.event.models import Event

        event = self._make_event("Legacy task Event", date="2025-06-01")
        Event.objects.filter(pk=event.pk).update(end_date=None)

        result = search_events({"date_from": "2025-06-01", "date_to": "2025-06-01"})

        self.assertIn("Legacy task Event", result)
        self.assertIn('"end_date": "2025-06-01"', result)

    def test_search_events_filters_by_registration_open(self):
        from apps.event.models import Event

        self._make_event()
        Event.objects.create(
            name="Open Day",
            slug="open-day",
            date="2025-07-15",
            end_date="2025-07-15",
            location="Hall",
            registration_open=True,
        )

        result = search_events({"registration_open": True})

        self.assertIn("Open Day", result)
        self.assertNotIn("Demo Day", result)

    def test_get_event_registrations_count_only(self):
        event = self._make_event()
        self._make_registration(event)
        result = get_event_registrations({"event_name": "Demo", "count_only": True})
        self.assertEqual(result, "Registration count: 1")

    def test_get_event_registrations_rows(self):
        event = self._make_event()
        self._make_registration(event)
        result = get_event_registrations({"event_id": str(event.pk)})
        self.assertIn("ann@example.com", result)

    def test_get_checkin_stats(self):
        event = self._make_event()
        registration = self._make_registration(event)
        from apps.event.models import CheckIn, CheckInRecord

        check_in = CheckIn.objects.create(event=event, name="Main Door")
        CheckInRecord.objects.create(check_in=check_in, registration=registration)
        result = get_checkin_stats({"event_name": "Demo"})
        self.assertIn("Total check-ins: 1", result)
        self.assertIn("Main Door", result)

    def test_get_checkin_stats_by_event_id(self):
        event = self._make_event()
        registration = self._make_registration(event)
        from apps.event.models import CheckIn, CheckInRecord

        check_in = CheckIn.objects.create(event=event, name="Side Door")
        CheckInRecord.objects.create(check_in=check_in, registration=registration)
        result = get_checkin_stats({"event_id": str(event.pk)})
        self.assertIn("Total check-ins: 1", result)
        self.assertIn("Side Door", result)


class MailToolsTest(TestCase):
    def _make_campaign(self, name="Spring Blast"):
        from apps.mail.models import EmailCampaign

        return EmailCampaign.objects.create(name=name, subject="Hi", status="draft")

    def test_search_email_campaigns(self):
        self._make_campaign()
        result = search_email_campaigns({"name": "Spring", "status": "draft", "subject": "Hi"})
        self.assertIn("Spring Blast", result)

    def test_campaign_stats_not_found(self):
        result = get_campaign_stats({"campaign_name": "nonexistent"})
        self.assertEqual(result, "No campaign found matching the criteria.")

    def test_campaign_stats_found(self):
        campaign = self._make_campaign()
        from apps.mail.models import RecipientLog

        RecipientLog.objects.create(campaign=campaign, status="sent")
        result = get_campaign_stats({"campaign_id": str(campaign.pk)})
        self.assertIn("Campaign: Spring Blast", result)
        self.assertIn("Delivery breakdown", result)
