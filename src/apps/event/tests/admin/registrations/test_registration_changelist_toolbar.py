import datetime

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from apps.event.admin.registration import EventRegistrationAdmin
from apps.event.admin.registration.changelist import (
    SemesterListFilter,
    semester_bounds,
    semester_choices,
    semester_label,
    semester_value,
)
from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket

URL = "/admin/event/eventregistration/"


class SemesterHelpersTest(SimpleTestCase):
    def test_semester_value_splits_the_year_at_july(self):
        self.assertEqual(semester_value(datetime.date(2026, 1, 1)), "2026-spring")
        self.assertEqual(semester_value(datetime.date(2026, 6, 30)), "2026-spring")
        self.assertEqual(semester_value(datetime.date(2026, 7, 1)), "2026-fall")
        self.assertEqual(semester_value(datetime.date(2026, 12, 31)), "2026-fall")

    def test_label(self):
        self.assertEqual(semester_label("2026-fall"), "Fall 2026")
        self.assertEqual(semester_label("2025-spring"), "Spring 2025")

    def test_bounds(self):
        self.assertEqual(semester_bounds("2026-fall"), (datetime.date(2026, 7, 1), datetime.date(2026, 12, 31)))
        self.assertEqual(semester_bounds("2026-spring"), (datetime.date(2026, 1, 1), datetime.date(2026, 6, 30)))

    def test_bounds_refuse_anything_else(self):
        for value in (None, "", "fall", "2026", "2026-winter", "abcd-fall", "0-fall", "99999-fall", "-1-fall"):
            with self.subTest(value=value):
                self.assertIsNone(semester_bounds(value))

    def test_choices_are_unique_and_newest_first(self):
        dates = [
            datetime.date(2025, 12, 12),
            datetime.date(2026, 5, 8),
            datetime.date(2026, 12, 11),
            datetime.date(2026, 12, 12),
        ]
        self.assertEqual(
            semester_choices(dates),
            [("2026-fall", "Fall 2026"), ("2026-spring", "Spring 2026"), ("2025-fall", "Fall 2025")],
        )


class RegistrationChangelistConfigTest(SimpleTestCase):
    def test_semester_and_event_filters(self):
        self.assertEqual(EventRegistrationAdmin.list_filter, (SemesterListFilter, "event", "ticket"))

    def test_search_covers_attendee_ticket_and_event_name(self):
        self.assertEqual(
            set(EventRegistrationAdmin.search_fields),
            {
                "attendee_first_name",
                "attendee_last_name",
                "attendee_email",
                "attendee_secondary_email",
                "attendee_phone",
                "attendee_organization",
                "ticket_code",
                "event__name",
            },
        )

    def test_list_display_is_compact(self):
        # Eleven columns made the table ~1,680px wide, so the Event column sat off-screen below 1,440px.
        self.assertEqual(
            EventRegistrationAdmin.list_display, ("ticket_code", "attendee", "event", "ticket", "created_at")
        )


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class RegistrationChangelistToolbarTest(TestCase):
    def setUp(self):
        cache.clear()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.fall_2026 = make_event(name="Innovate to Grow Fall 2026", date=datetime.date(2026, 12, 11))
        self.spring_2026 = make_event(name="Innovate to Grow Spring 2026", date=datetime.date(2026, 5, 8))
        self.fall_2025 = make_event(name="Innovate to Grow Fall 2025", date=datetime.date(2025, 12, 12))
        self.registrations = {}
        for index, event in enumerate((self.fall_2026, self.spring_2026, self.fall_2025)):
            member = make_member(email=f"attendee{index}@example.com")
            self.registrations[event.pk] = make_registration(
                member, event, make_ticket(event), attendee_first_name="Alex", attendee_last_name=f"Doe{index}"
            )

    def _result_events(self, response):
        self.assertEqual(response.status_code, 200)
        return {registration.event.name for registration in response.context["cl"].result_list}

    def test_changelist_renders_search_and_both_filter_selects(self):
        response = self.client.get(URL)

        self.assertContains(response, 'id="changelist-search"')
        self.assertContains(response, 'id="searchbar"')
        self.assertContains(response, 'name="q"')
        self.assertContains(response, 'name="semester"')
        self.assertContains(response, 'name="event__id__exact"')
        self.assertContains(response, '<option value="2026-fall">Fall 2026</option>')
        self.assertContains(response, '<option value="2025-fall">Fall 2025</option>')
        self.assertContains(response, f'<option value="{self.fall_2026.pk}">Innovate to Grow Fall 2026</option>')
        self.assertContains(response, "event/css/event_admin/registration_changelist.css")
        self.assertContains(response, "event/js/registration_changelist_toolbar.js")
        self.assertNotContains(response, 'class="i2g-reg-toolbar__clear"')

    def test_filter_by_semester(self):
        response = self.client.get(URL, {"semester": "2026-fall"})

        self.assertEqual(self._result_events(response), {"Innovate to Grow Fall 2026"})
        self.assertContains(response, '<option value="2026-fall" selected>Fall 2026</option>')
        self.assertContains(response, 'class="i2g-reg-toolbar__clear"')

    def test_filter_by_event(self):
        response = self.client.get(URL, {"event__id__exact": str(self.fall_2026.pk)})

        self.assertEqual(self._result_events(response), {"Innovate to Grow Fall 2026"})
        self.assertContains(
            response, f'<option value="{self.fall_2026.pk}" selected>Innovate to Grow Fall 2026</option>'
        )

    def test_search_by_event_name(self):
        response = self.client.get(URL, {"q": "Fall 2026"})

        self.assertEqual(self._result_events(response), {"Innovate to Grow Fall 2026"})

    def test_search_by_attendee_still_works(self):
        response = self.client.get(URL, {"q": "Doe1"})

        self.assertEqual(self._result_events(response), {"Innovate to Grow Spring 2026"})

    def test_unknown_semester_is_ignored(self):
        response = self.client.get(URL, {"semester": "2026-winter"})

        self.assertEqual(len(self._result_events(response)), 3)

    def test_other_query_parameters_are_kept_and_the_page_is_dropped(self):
        ticket = self.registrations[self.fall_2026.pk].ticket
        response = self.client.get(URL, {"ticket__id__exact": str(ticket.pk), "o": "1", "p": "1"})

        toolbar = response.context["registration_toolbar"]
        self.assertEqual(toolbar["hidden"], [("ticket__id__exact", str(ticket.pk)), ("o", "1")])
        self.assertContains(response, f'<input type="hidden" name="ticket__id__exact" value="{ticket.pk}">')
