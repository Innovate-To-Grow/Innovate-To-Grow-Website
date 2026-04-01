import datetime

from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase

from event.models import Event, EventRegistration, Question, Ticket
from event.tests.helpers import make_event, make_member, make_ticket


def _make_question(event, text="What is your role?", **kwargs):
    return Question.objects.create(event=event, text=text, **kwargs)


# ---------- Event ----------


class EventModelTest(TestCase):
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

    def test_is_live_defaults_to_false(self):
        event = make_event()
        self.assertFalse(event.is_live)

    def test_soft_delete_excludes_from_default_manager(self):
        event = make_event()
        event.delete()
        self.assertEqual(Event.objects.count(), 0)

    def test_soft_delete_visible_via_all_objects(self):
        event = make_event()
        event.delete()
        self.assertEqual(Event.all_objects.count(), 1)

    def test_cascade_deletes_tickets_and_questions(self):
        event = make_event()
        make_ticket(event)
        _make_question(event)
        event.hard_delete()
        self.assertEqual(Ticket.all_objects.count(), 0)
        self.assertEqual(Question.all_objects.count(), 0)


# ---------- Ticket ----------


class TicketModelTest(TestCase):
    def setUp(self):
        self.event = make_event()

    def test_str_includes_event_name_and_ticket_name(self):
        ticket = make_ticket(self.event, name="VIP")
        self.assertEqual(str(ticket), f"{self.event.name} - VIP")

    def test_barcode_auto_generated(self):
        ticket = make_ticket(self.event)
        self.assertTrue(len(ticket.barcode) > 0)

    def test_barcode_is_unique(self):
        t1 = make_ticket(self.event, name="A")
        t2 = make_ticket(self.event, name="B")
        self.assertNotEqual(t1.barcode, t2.barcode)

    def test_ordering_by_order_then_name(self):
        t_b = make_ticket(self.event, name="Beta", order=1)
        t_a = make_ticket(self.event, name="Alpha", order=0)
        self.assertEqual(list(self.event.tickets.all()), [t_a, t_b])

    def test_price_default_is_zero(self):
        ticket = make_ticket(self.event)
        self.assertEqual(ticket.price, 0)

    def test_quantity_default_is_zero(self):
        ticket = make_ticket(self.event)
        self.assertEqual(ticket.quantity, 0)

    def test_barcode_format_constant(self):
        self.assertEqual(Ticket.BARCODE_FORMAT, "PDF417")


# ---------- Question ----------


class QuestionModelTest(TestCase):
    def setUp(self):
        self.event = make_event()

    def test_str_truncates_at_50_chars(self):
        long_text = "A" * 80
        q = _make_question(self.event, text=long_text)
        self.assertEqual(str(q), f"{self.event.name} - {long_text[:50]}")

    def test_str_full_text_under_50(self):
        q = _make_question(self.event, text="Short question")
        self.assertEqual(str(q), f"{self.event.name} - Short question")

    def test_ordering_by_order_field(self):
        q2 = _make_question(self.event, text="Second", order=2)
        q1 = _make_question(self.event, text="First", order=1)
        self.assertEqual(list(self.event.questions.all()), [q1, q2])

    def test_is_required_default_false(self):
        q = _make_question(self.event)
        self.assertFalse(q.is_required)


# ---------- EventRegistration ----------


class EventRegistrationModelTest(TestCase):
    def setUp(self):
        self.member = make_member(first_name="Jane", last_name="Doe")
        self.event = make_event()
        self.ticket = make_ticket(self.event)

    def _make_registration(self, **kwargs):
        defaults = {"member": self.member, "event": self.event, "ticket": self.ticket}
        defaults.update(kwargs)
        return EventRegistration.objects.create(**defaults)

    def test_str_uses_attendee_name_when_present(self):
        reg = self._make_registration(attendee_first_name="Jane", attendee_last_name="Doe")
        self.assertIn("Jane Doe", str(reg))

    def test_str_falls_back_to_member_email(self):
        member_no_name = make_member(username="noname", email="noname@example.com", first_name="", last_name="")
        reg = self._make_registration(member=member_no_name)
        # save() falls back: first_name -> username -> email; last_name -> ""
        self.assertIn("noname", str(reg))

    def test_ticket_code_auto_generated(self):
        reg = self._make_registration()
        self.assertTrue(len(reg.ticket_code) > 0)

    def test_ticket_code_starts_with_i2g(self):
        reg = self._make_registration()
        self.assertTrue(reg.ticket_code.startswith("I2G-"))

    def test_ticket_code_unique(self):
        r1 = self._make_registration()
        member2 = make_member(username="user2", email="user2@example.com")
        r2 = self._make_registration(member=member2)
        self.assertNotEqual(r1.ticket_code, r2.ticket_code)

    def test_attendee_name_property(self):
        reg = self._make_registration(attendee_first_name="John", attendee_last_name="Smith")
        self.assertEqual(reg.attendee_name, "John Smith")

    def test_attendee_name_property_strips_whitespace(self):
        member_no_last = make_member(username="nolast", email="nolast@example.com", first_name="John", last_name="")
        reg = self._make_registration(member=member_no_last, attendee_first_name="John", attendee_last_name="")
        self.assertEqual(reg.attendee_name, "John")

    def test_barcode_payload_format(self):
        reg = self._make_registration()
        expected = f"I2G|EVENT|{self.event.slug}|{reg.ticket_code}"
        self.assertEqual(reg.barcode_payload, expected)

    def test_save_populates_attendee_first_name_from_member(self):
        reg = self._make_registration()
        self.assertEqual(reg.attendee_first_name, "Jane")

    def test_save_populates_attendee_last_name_from_member(self):
        reg = self._make_registration()
        self.assertEqual(reg.attendee_last_name, "Doe")

    def test_save_populates_attendee_email_from_member(self):
        reg = self._make_registration()
        self.assertEqual(reg.attendee_email, "test@example.com")

    def test_save_first_name_fallback_to_username(self):
        member = make_member(username="fallbackuser", email="fb@example.com", first_name="", last_name="")
        reg = self._make_registration(member=member)
        self.assertEqual(reg.attendee_first_name, "fallbackuser")

    def test_save_first_name_fallback_to_email(self):
        member = make_member(username="emailfallback", email="emailonly@example.com", first_name="", last_name="")
        # Clear username after creation to simulate edge case
        member.username = ""
        member.save(update_fields=["username"])
        reg = self._make_registration(member=member)
        self.assertEqual(reg.attendee_first_name, "emailonly@example.com")

    def test_save_does_not_overwrite_explicit_attendee_fields(self):
        reg = self._make_registration(attendee_first_name="Custom", attendee_last_name="Name")
        self.assertEqual(reg.attendee_first_name, "Custom")
        self.assertEqual(reg.attendee_last_name, "Name")

    def test_unique_constraint_per_member_per_event(self):
        self._make_registration()
        with self.assertRaises(IntegrityError):
            self._make_registration()

    def test_ordering_by_created_at_descending(self):
        member2 = make_member(username="user2", email="user2@example.com")
        r1 = self._make_registration()
        r2 = self._make_registration(member=member2)
        regs = list(EventRegistration.objects.all())
        self.assertEqual(regs, [r2, r1])

    def test_question_answers_default_is_empty_list(self):
        reg = self._make_registration()
        self.assertEqual(reg.question_answers, [])

    def test_ticket_protect_prevents_deletion(self):
        reg = self._make_registration()
        with self.assertRaises(ProtectedError):
            reg.ticket.hard_delete()
