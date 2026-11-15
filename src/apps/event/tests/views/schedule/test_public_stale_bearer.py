"""A stale stored session must not break the public event endpoints.

The SPA sends whatever access token local storage holds with every request, and DRF authenticates before it
checks permissions. The schedule and project reads never look at the caller, so they run no authentication. The
registration reads report the caller's own registration, so they honour a valid token and treat a bad one as
anonymous.
"""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.authn.tests.stale_bearer import (
    assert_stale_bearer_reads_as_anonymous,
    stale_bearer_headers,
    valid_bearer_header,
)
from apps.event.models import CurrentProject, CurrentProjectSchedule, EventRegistration, Ticket
from apps.event.services import sync_schedule
from apps.event.tests.helpers import make_event, make_member, sample_projects_records, sample_tracks_records


class PublicScheduleEndpointsStaleBearerTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def assert_reads_as_anonymous(self, url):
        assert_stale_bearer_reads_as_anonymous(self, lambda **extra: self.client.get(url, **extra))

    def test_schedule_without_a_configured_schedule(self):
        self.assert_reads_as_anonymous("/event/schedule/")

    def test_schedule(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        sync_schedule(config, tracks_records=sample_tracks_records(), projects_records=sample_projects_records())

        self.assert_reads_as_anonymous("/event/schedule/")

    def test_current_projects_without_a_configured_schedule(self):
        self.assert_reads_as_anonymous("/event/projects/")

    def test_current_projects(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        CurrentProject.objects.create(schedule=config, project_title="Fall Project", team_number="T1")

        self.assert_reads_as_anonymous("/event/projects/")


class RegistrationReadsStaleBearerTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.event = make_event(registration_open=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.member = make_member()
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)

    def test_options_stale_bearer_reads_as_anonymous(self):
        assert_stale_bearer_reads_as_anonymous(
            self, lambda **extra: self.client.get("/event/registration-options/", **extra)
        )

    def test_events_stale_bearer_reads_as_anonymous(self):
        assert_stale_bearer_reads_as_anonymous(
            self, lambda **extra: self.client.get("/event/registration-events/", **extra)
        )

    def test_options_stale_bearer_has_no_registration(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                response = self.client.get("/event/registration-options/", HTTP_AUTHORIZATION=header)

                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.data["registration"])

    def test_options_valid_bearer_sees_own_registration(self):
        response = self.client.get("/event/registration-options/", HTTP_AUTHORIZATION=valid_bearer_header(self.member))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["registration"]["id"], str(self.registration.pk))

    def test_events_valid_bearer_sees_own_registration(self):
        response = self.client.get("/event/registration-events/", HTTP_AUTHORIZATION=valid_bearer_header(self.member))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["registration"]["id"], str(self.registration.pk))

    def test_events_stale_bearer_has_no_registration(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                response = self.client.get("/event/registration-events/", HTTP_AUTHORIZATION=header)

                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.data[0]["registration"])
