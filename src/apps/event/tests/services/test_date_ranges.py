import datetime

from django.test import SimpleTestCase

from apps.event.services import format_event_date_range


class FormatEventDateRangeTest(SimpleTestCase):
    def test_single_day_is_shown_once(self):
        result = format_event_date_range(datetime.date(2026, 5, 10), datetime.date(2026, 5, 10))

        self.assertEqual(result, "May 10, 2026")

    def test_same_month_range_collapses_repeated_month_and_year(self):
        result = format_event_date_range(datetime.date(2026, 5, 10), datetime.date(2026, 5, 12))

        self.assertEqual(result, "May 10–12, 2026")

    def test_cross_month_range_keeps_both_months(self):
        result = format_event_date_range(datetime.date(2026, 5, 31), datetime.date(2026, 6, 2))

        self.assertEqual(result, "May 31–June 2, 2026")

    def test_cross_year_range_keeps_both_years(self):
        result = format_event_date_range(datetime.date(2026, 12, 31), datetime.date(2027, 1, 2))

        self.assertEqual(result, "December 31, 2026–January 2, 2027")

    def test_end_before_start_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "Event end date cannot be earlier than its start date."):
            format_event_date_range(datetime.date(2026, 5, 11), datetime.date(2026, 5, 10))
