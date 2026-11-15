import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import BackgroundJob
from apps.event.models import EventRegistration, Question, Ticket
from apps.event.tests.helpers import make_event, make_member


# force_authenticate is invisible to the request limiter (it reads the bearer token), so with it switched on every
# request here would count as one anonymous source against member-send's flood ceiling, across the whole module.
class _EventRegistrationCreateViewCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member(first_name="Jane", last_name="Doe")
        self.event = make_event(registration_open=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")

    def _post(self, data=None, authenticate=True):
        if authenticate:
            self.client.force_authenticate(self.member)
        if data is None:
            data = {"event_slug": self.event.slug, "ticket_id": str(self.ticket.pk)}
        data.setdefault("attendee_first_name", "Jane")
        data.setdefault("attendee_last_name", "Doe")
        return self.client.post("/event/registrations/", data, format="json")


@override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
class EventRegistrationCreateViewTest(_EventRegistrationCreateViewCase):
    def test_unauthenticated_returns_401(self):
        response = self._post(authenticate=False)
        self.assertEqual(response.status_code, 401)

    def test_event_not_found_returns_404(self):
        response = self._post({"event_slug": "nonexistent", "ticket_id": str(self.ticket.pk)})
        self.assertEqual(response.status_code, 404)

    def test_closed_event_returns_404(self):
        self.event.registration_open = False
        self.event.save(update_fields=["registration_open", "updated_at"])
        response = self._post()
        self.assertEqual(response.status_code, 404)

    def test_invalid_ticket_returns_400(self):
        response = self._post({"event_slug": self.event.slug, "ticket_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 400)

    def test_ticket_from_wrong_event_returns_400(self):
        other_event = make_event(name="Other", slug="other")
        other_ticket = Ticket.objects.create(event=other_event, name="VIP")
        response = self._post({"event_slug": self.event.slug, "ticket_id": str(other_ticket.pk)})
        self.assertEqual(response.status_code, 400)

    def test_successful_registration_returns_201(self):
        response = self._post()
        self.assertEqual(response.status_code, 201)

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_registration_and_delivery_jobs_commit_together(self):
        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])

        response = self._post()

        self.assertEqual(response.status_code, 201)
        registration = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertSetEqual(
            set(
                BackgroundJob.objects.filter(
                    payload__registration_id=str(registration.pk),
                ).values_list("kind", flat=True)
            )
            | set(
                BackgroundJob.objects.filter(
                    kind="event.registration_sheet_sync",
                    payload__event_id=str(self.event.pk),
                ).values_list("kind", flat=True)
            ),
            {"event.registration_sheet_sync", "event.ticket_email"},
        )

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_job_insert_failure_rolls_back_registration(self):
        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])
        self.client.raise_request_exception = False

        with patch(
            "apps.core.services.background_jobs.enqueue_job",
            side_effect=RuntimeError("outbox unavailable"),
        ):
            response = self._post()

        self.assertEqual(response.status_code, 500)
        self.assertFalse(EventRegistration.objects.filter(member=self.member, event=self.event).exists())
        self.assertEqual(BackgroundJob.objects.filter(kind="event.registration_sheet_sync").count(), 1)
        self.assertFalse(BackgroundJob.objects.filter(kind="event.ticket_email").exists())

    @patch(
        "apps.event.views.registration.create_support.notifications.start_in_process_task",
        side_effect=lambda target, *args, **_kwargs: target(*args),
    )
    @patch("apps.event.services.ticket.mail.send_ticket_email", side_effect=Exception("SMTP error"))
    def test_ticket_email_failure_logs_stack_trace_and_still_registers(self, _mock_send, start_task):
        with patch("apps.event.views.registration.logger.warning") as warning:
            with self.captureOnCommitCallbacks(execute=True):
                response = self._post()

        self.assertEqual(response.status_code, 201)
        start_task.assert_called_once()
        self.assertTrue(start_task.call_args.kwargs["best_effort_start"])
        warning.assert_called_once_with("Failed to send initial ticket email", exc_info=True)

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    @patch("apps.core.services.helpers.in_process.threading.Thread")
    def test_ticket_thread_start_failure_does_not_break_committed_registration(self, thread_class):
        thread_class.return_value.start.side_effect = RuntimeError("can't start new thread")

        with self.assertLogs("apps.core.services.helpers.in_process", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                response = self._post()

        self.assertEqual(response.status_code, 201)
        registration = EventRegistration.objects.get(member=self.member, event=self.event)
        self.assertIn("could not be started", registration.ticket_email_error)

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    def test_durable_sheet_job_does_not_delay_ticket_start(self):
        self.event.registration_sheet_id = "sheet-id"
        self.event.save(update_fields=["registration_sheet_id", "updated_at"])

        with (
            patch(
                "apps.event.views.registration.create_support.notifications.start_in_process_task",
                return_value=MagicMock(),
            ) as start_task,
            patch("apps.event.services.registration_sheet_sync.append._schedule_in_process_sync") as start_sync,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self._post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(BackgroundJob.objects.filter(kind="event.registration_sheet_sync").count(), 1)
        start_task.assert_called_once()
        start_sync.assert_called_once()

    def test_response_contains_registration_payload(self):
        response = self._post()
        self.assertIn("id", response.data)
        self.assertIn("ticket_code", response.data)
        self.assertIn("barcode_image", response.data)

    def test_duplicate_registration_returns_409(self):
        self._post()
        response = self._post()
        self.assertEqual(response.status_code, 409)
        self.assertIn("already registered", response.data["detail"])

    def test_duplicate_registration_includes_existing_payload(self):
        self._post()
        response = self._post()
        self.assertIn("registration", response.data)
        self.assertIn("id", response.data["registration"])

    def test_member_can_register_for_two_different_open_events(self):
        first = self._post()
        other_event = make_event(name="Other Open Event", slug="other-open-event", registration_open=True)
        other_ticket = Ticket.objects.create(event=other_event, name="VIP")
        second = self._post({"event_slug": other_event.slug, "ticket_id": str(other_ticket.pk)})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(EventRegistration.objects.filter(member=self.member).count(), 2)

    def test_required_question_missing_answer_returns_400(self):
        Question.objects.create(event=self.event, text="Required Q", is_required=True)
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Answer required", response.data["detail"])
