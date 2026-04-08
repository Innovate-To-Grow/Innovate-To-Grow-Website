import datetime

from django.test import TestCase

from event.services.calendar import build_google_calendar_url, generate_ics


class GenerateIcsTest(TestCase):
    def test_all_day_event(self):
        ics = generate_ics(
            event_uid="abc-123",
            event_name="Demo Day",
            event_date=datetime.date(2026, 5, 10),
            event_location="UC Merced",
            event_description="Annual showcase",
        )
        self.assertIn("DTSTART;VALUE=DATE:20260510", ics)
        self.assertIn("DTEND;VALUE=DATE:20260511", ics)
        self.assertIn("SUMMARY:Demo Day", ics)
        self.assertIn("LOCATION:UC Merced", ics)
        self.assertIn("DESCRIPTION:Annual showcase", ics)
        self.assertIn("UID:abc-123@i2g.ucmerced.edu", ics)
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("END:VCALENDAR", ics)

    def test_no_description(self):
        ics = generate_ics(
            event_uid="xyz",
            event_name="Test",
            event_date=datetime.date(2026, 1, 1),
            event_location="Online",
        )
        self.assertNotIn("DESCRIPTION", ics)

    def test_special_characters_escaped(self):
        ics = generate_ics(
            event_uid="esc",
            event_name="A, B; C",
            event_date=datetime.date(2026, 3, 15),
            event_location="Room 1; Floor 2",
        )
        self.assertIn("SUMMARY:A\\, B\\; C", ics)
        self.assertIn("LOCATION:Room 1\\; Floor 2", ics)


class BuildGoogleCalendarUrlTest(TestCase):
    def test_url_format(self):
        url = build_google_calendar_url(
            event_name="Demo Day",
            event_date=datetime.date(2026, 5, 10),
            event_location="UC Merced",
            event_description="Showcase",
        )
        self.assertIn("calendar.google.com/calendar/render", url)
        self.assertIn("text=Demo%20Day", url)
        self.assertIn("dates=20260510%2F20260511", url)
        self.assertIn("location=UC%20Merced", url)
        self.assertIn("details=Showcase", url)
