from django.test import override_settings

from apps.event.models import Event, Question, Ticket
from apps.event.tests.admin.events.test_event_admin_views import _EventAdminCase
from apps.event.tests.helpers import (
    make_event,
)


class EventAdminTest(_EventAdminCase):
    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_saving_loaded_copy_uses_final_edited_deleted_and_added_inline_rows(self):
        source = make_event(name="Editable Copy Source", registration_open=True)
        source_tickets = [
            Ticket.objects.create(event=source, name="General", order=1),
            Ticket.objects.create(event=source, name="VIP", order=2),
            Ticket.objects.create(event=source, name="Student", order=3),
        ]
        source_questions = [
            Question.objects.create(event=source, text="Role?", is_required=True, order=1),
            Question.objects.create(event=source, text="Dietary needs?", order=2),
        ]
        source_ticket_snapshot = list(source.tickets.values("pk", "name", "order", "barcode"))
        source_question_snapshot = list(source.questions.values("pk", "text", "is_required", "order"))
        self.client.get(f"/admin/event/event/add/?copy_from={source.pk}")

        response = self.client.post(
            f"/admin/event/event/add/?copy_from={source.pk}",
            self._copy_post_data(
                name="Reviewed Copy",
                slug="reviewed-copy",
                ticket_rows=[
                    {"name": "General Admission", "order": 10},
                    {"name": "VIP", "order": 2, "DELETE": True},
                    {"name": "Student", "order": 3},
                    {"name": "Sponsor", "order": 4},
                ],
                question_rows=[
                    {"text": "Your role?", "is_required": False, "order": 5},
                    {"text": "Dietary needs?", "order": 2, "DELETE": True},
                    {"text": "Accessibility needs?", "is_required": True, "order": 3},
                ],
            ),
        )

        self.assertEqual(response.status_code, 302)
        copied = Event.objects.get(slug="reviewed-copy")
        self.assertEqual(
            list(copied.tickets.values_list("name", "order")),
            [("Student", 3), ("Sponsor", 4), ("General Admission", 10)],
        )
        self.assertEqual(
            list(copied.questions.values_list("text", "is_required", "order")),
            [("Accessibility needs?", True, 3), ("Your role?", False, 5)],
        )
        source_ticket_ids = {ticket.pk for ticket in source_tickets}
        source_ticket_barcodes = {ticket.barcode for ticket in source_tickets}
        source_question_ids = {question.pk for question in source_questions}
        self.assertTrue(source_ticket_ids.isdisjoint(copied.tickets.values_list("pk", flat=True)))
        self.assertTrue(source_ticket_barcodes.isdisjoint(copied.tickets.values_list("barcode", flat=True)))
        self.assertTrue(source_question_ids.isdisjoint(copied.questions.values_list("pk", flat=True)))
        source.refresh_from_db()
        self.assertTrue(source.registration_open)
        self.assertEqual(list(source.tickets.values("pk", "name", "order", "barcode")), source_ticket_snapshot)
        self.assertEqual(
            list(source.questions.values("pk", "text", "is_required", "order")),
            source_question_snapshot,
        )

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_post_uses_loaded_snapshot_when_source_was_deleted_after_get(self):
        source = make_event(name="Ephemeral Copy Source")
        source_id = source.pk
        Ticket.objects.create(event=source, name="Snapshot Ticket", order=2)
        Question.objects.create(event=source, text="Snapshot question?", is_required=True, order=3)
        self.assertEqual(self.client.get(f"/admin/event/event/add/?copy_from={source_id}").status_code, 200)
        source.delete()

        response = self.client.post(
            f"/admin/event/event/add/?copy_from={source_id}",
            self._copy_post_data(
                name="Saved Detached Snapshot",
                slug="saved-detached-snapshot",
                ticket_rows=[{"name": "Snapshot Ticket", "order": 2}],
                question_rows=[{"text": "Snapshot question?", "is_required": True, "order": 3}],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm-change", response.url)
        pending = self.client.session["_admin_pending_change_event_event"]
        response = self.client.post(
            response.url,
            {"token": pending["token"], "confirmation_word": "event"},
        )
        self.assertEqual(response.status_code, 302)
        copied = Event.objects.get(slug="saved-detached-snapshot")
        self.assertEqual(list(copied.tickets.values_list("name", flat=True)), ["Snapshot Ticket"])
        self.assertEqual(list(copied.questions.values_list("text", flat=True)), ["Snapshot question?"])
        self.assertFalse(Event.objects.filter(pk=source_id).exists())
