import datetime

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.event.models import Event, Question, Ticket
from apps.event.tests.helpers import make_event, make_ticket


def _make_question(event, text="What is your role?", **kwargs):
    return Question.objects.create(event=event, text=text, **kwargs)


# ---------- Event ----------


class EventModelTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_str_returns_name(self):
        event = make_event(name="Spring Showcase")
        self.assertEqual(str(event), "Spring Showcase")

    def test_auto_slug_on_save(self):
        event = make_event(name="Demo Day 2025")
        self.assertEqual(event.slug, "demo-day-2025")

    def test_slug_preserved_when_already_set(self):
        event = make_event(name="Demo Day", slug="custom-slug")
        self.assertEqual(event.slug, "custom-slug")

    def test_ordering_by_date_descending(self):
        e1 = make_event(name="Old", date=datetime.date(2024, 1, 1))
        e2 = make_event(name="New", date=datetime.date(2025, 1, 1))
        self.assertEqual(list(Event.objects.all()), [e2, e1])

    def test_registration_open_defaults_to_false(self):
        event = make_event()
        self.assertFalse(event.registration_open)

    def test_multiple_events_can_be_open_for_registration(self):
        first = make_event(name="First", registration_open=True)
        second = make_event(name="Second", registration_open=True)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.registration_open)
        self.assertTrue(second.registration_open)

    def test_save_defaults_missing_end_date_to_start_date(self):
        event = Event.objects.create(
            name="Legacy-compatible Event",
            date=datetime.date(2025, 8, 1),
            end_date=None,
            location="Test Venue",
            description="A test event.",
        )
        self.assertEqual(event.end_date, event.date)

    def test_effective_end_date_falls_back_to_start_date(self):
        event = make_event()
        Event.objects.filter(pk=event.pk).update(end_date=None)
        event.refresh_from_db()
        self.assertIsNone(event.end_date)
        self.assertEqual(event.effective_end_date, event.date)

    def test_full_clean_normalizes_transitional_null_end_date_on_existing_event(self):
        event = make_event()
        Event.objects.filter(pk=event.pk).update(end_date=None)
        event.refresh_from_db()

        event.full_clean()

        self.assertEqual(event.end_date, event.date)

    def test_delete_removes_from_database(self):
        event = make_event()
        event.delete()
        self.assertEqual(Event.objects.count(), 0)

    def test_cascade_deletes_tickets_and_questions(self):
        event = make_event()
        make_ticket(event)
        _make_question(event)
        event.delete()
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(Question.objects.count(), 0)

    def test_clean_rejects_verify_phone_without_collect_phone(self):
        event = Event(
            name="Invalid phone options",
            date=datetime.date(2025, 6, 15),
            end_date=datetime.date(2025, 6, 15),
            location="Test Venue",
            description="A test event.",
            collect_phone=False,
            verify_phone=True,
        )
        with self.assertRaises(ValidationError) as ctx:
            event.clean()
        self.assertIn("verify_phone", ctx.exception.message_dict)

    def test_clean_allows_verify_phone_with_collect_phone(self):
        event = make_event(collect_phone=True, verify_phone=True)
        event.clean()  # should not raise

    def test_clean_allows_no_verify_no_collect(self):
        event = make_event()
        event.clean()  # should not raise

    def test_clean_rejects_end_date_before_start_date(self):
        event = Event(
            name="Invalid date range",
            date=datetime.date(2025, 6, 16),
            end_date=datetime.date(2025, 6, 15),
            location="Test Venue",
            description="A test event.",
        )
        with self.assertRaises(ValidationError) as ctx:
            event.clean()
        self.assertIn("end_date", ctx.exception.message_dict)

    def test_database_rejects_verify_phone_without_prompt(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_event(name="Invalid database phone options", collect_phone=False, verify_phone=True)

    def test_new_event_contact_options_default_to_off(self):
        event = make_event()
        for field in (
            "collect_phone",
            "verify_phone",
            "require_phone",
            "allow_secondary_email",
            "verify_secondary_email",
            "require_secondary_email",
        ):
            self.assertFalse(getattr(event, field), field)

    def test_contact_settings_model_and_database_reject_dependent_options_without_collection(self):
        for field in ("verify_phone", "require_phone", "verify_secondary_email", "require_secondary_email"):
            with self.subTest(field=field):
                event = Event(**{field: True})
                with self.assertRaises(ValidationError) as raised:
                    event.clean()
                self.assertIn(field, raised.exception.message_dict)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    make_event(name=f"Invalid {field}", **{field: True})

    def test_all_contact_setting_combinations_are_valid(self):
        for collect, verify, required in (
            (False, False, False),
            (True, False, False),
            (True, True, False),
            (True, False, True),
            (True, True, True),
        ):
            with self.subTest(collect=collect, verify=verify, required=required):
                event = make_event(
                    name=f"Contact settings {collect} {verify} {required}",
                    collect_phone=collect,
                    verify_phone=verify,
                    require_phone=required,
                    allow_secondary_email=collect,
                    verify_secondary_email=verify,
                    require_secondary_email=required,
                )
                event.full_clean()


# ---------- Ticket ----------


# ---------- Question ----------


# ---------- EventRegistration ----------
