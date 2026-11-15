import uuid

from django.test import override_settings

from apps.event.models import CheckIn, Event, Question, Ticket
from apps.event.tests.admin.events.test_event_admin_views import _EventAdminCase
from apps.event.tests.helpers import (
    make_event,
)


class EventAdminTest(_EventAdminCase):
    def test_add_form_loads_multiple_ticket_types_and_questions_in_order(self):
        source = make_event(name="Multiple Children Source")
        Ticket.objects.create(event=source, name="VIP", order=30)
        Ticket.objects.create(event=source, name="General", order=10)
        Ticket.objects.create(event=source, name="Student", order=20)
        Question.objects.create(event=source, text="Optional note?", order=8)
        Question.objects.create(event=source, text="Required role?", is_required=True, order=2)

        response = self.client.get(f"/admin/event/event/add/?copy_from={source.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3 Ticket types")
        self.assertContains(response, "2 Questions")
        inline_forms = {inline.opts.model: inline.formset.forms for inline in response.context["inline_admin_formsets"]}
        self.assertEqual(
            [form.initial for form in inline_forms[Ticket]],
            [
                {"name": "General", "order": 10},
                {"name": "Student", "order": 20},
                {"name": "VIP", "order": 30},
            ],
        )
        self.assertEqual(
            [form.initial for form in inline_forms[Question]],
            [
                {"text": "Required role?", "is_required": True, "order": 2},
                {"text": "Optional note?", "is_required": False, "order": 8},
            ],
        )

    def test_add_form_loads_source_with_zero_ticket_types_and_questions(self):
        source = make_event(name="Empty Children Source")

        response = self.client.get(f"/admin/event/event/add/?copy_from={source.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0 Ticket types")
        self.assertContains(response, "0 Questions")
        inline_forms = {inline.opts.model: inline.formset.forms for inline in response.context["inline_admin_formsets"]}
        self.assertEqual(inline_forms[Ticket], [])
        self.assertEqual(inline_forms[Question], [])

    def test_add_form_rejects_missing_copy_source(self):
        deleted_source = make_event(name="Deleted Copy Source")
        deleted_source_id = deleted_source.pk
        deleted_source.delete()

        for source_id in ("not-a-valid-id", str(uuid.uuid4()), str(deleted_source_id)):
            with self.subTest(source_id=source_id):
                response = self.client.get(f"/admin/event/event/add/?copy_from={source_id}")
                self.assertEqual(response.status_code, 404)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_saving_loaded_copy_creates_new_children_and_resets_operational_data(self):
        source = make_event(
            name="Save Source Event",
            registration_open=True,
            allow_secondary_email=True,
            collect_phone=True,
            verify_phone=True,
            require_phone=True,
            verify_secondary_email=True,
            require_secondary_email=True,
            registration_sheet_id="source-sheet",
            registration_sheet_gid=42,
        )
        source_ticket = Ticket.objects.create(event=source, name="General Admission", order=1)
        source_question = Question.objects.create(event=source, text="Role?", is_required=True, order=2)
        CheckIn.objects.create(event=source, name="Source entrance")

        response = self.client.post(
            f"/admin/event/event/add/?copy_from={source.pk}",
            {
                "name": "New Copied Event",
                "slug": "new-copied-event",
                "date": "2026-10-01",
                "end_date": "2026-10-03",
                "location": source.location,
                "description": source.description,
                "allow_secondary_email": "on",
                "collect_phone": "on",
                "verify_phone": "on",
                "require_phone": "on",
                "verify_secondary_email": "on",
                "require_secondary_email": "on",
                "ticket_login_validity_days": "30",
                "ticket_login_reusable": "on",
                "registration_sheet_id": "",
                "registration_sheet_gid": "",
                "tickets-TOTAL_FORMS": "1",
                "tickets-INITIAL_FORMS": "0",
                "tickets-MIN_NUM_FORMS": "0",
                "tickets-MAX_NUM_FORMS": "1000",
                "tickets-0-name": source_ticket.name,
                "tickets-0-order": str(source_ticket.order),
                "questions-TOTAL_FORMS": "1",
                "questions-INITIAL_FORMS": "0",
                "questions-MIN_NUM_FORMS": "0",
                "questions-MAX_NUM_FORMS": "1000",
                "questions-0-text": source_question.text,
                "questions-0-is_required": "on",
                "questions-0-order": str(source_question.order),
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        copied = Event.objects.get(slug="new-copied-event")
        self.assertFalse(copied.registration_open)
        self.assertTrue(copied.allow_secondary_email)
        self.assertTrue(copied.collect_phone)
        self.assertTrue(copied.verify_phone)
        self.assertTrue(copied.require_phone)
        self.assertTrue(copied.verify_secondary_email)
        self.assertTrue(copied.require_secondary_email)
        self.assertEqual(copied.ticket_login_validity_days, source.ticket_login_validity_days)
        self.assertEqual(copied.ticket_login_reusable, source.ticket_login_reusable)
        self.assertEqual(copied.registration_sheet_id, "")
        self.assertIsNone(copied.registration_sheet_gid)
        self.assertEqual(copied.registration_sheet_sync_count, 0)
        self.assertEqual(copied.registration_sheet_sync_error, "")
        self.assertEqual(copied.check_ins.count(), 0)
        copied_ticket = copied.tickets.get(name=source_ticket.name)
        copied_question = copied.questions.get(text=source_question.text)
        self.assertNotEqual(copied_ticket.pk, source_ticket.pk)
        self.assertNotEqual(copied_ticket.barcode, source_ticket.barcode)
        self.assertNotEqual(copied_question.pk, source_question.pk)
        source.refresh_from_db()
        self.assertTrue(source.registration_open)
        self.assertEqual(source.registration_sheet_id, "source-sheet")
