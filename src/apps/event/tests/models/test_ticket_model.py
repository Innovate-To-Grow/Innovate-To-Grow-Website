from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.event.models import EventRegistration, Ticket
from apps.event.tests.helpers import make_event, make_member, make_ticket
from apps.event.tests.models.test_models import _make_question


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

    def test_barcode_format_constant(self):
        self.assertEqual(Ticket.BARCODE_FORMAT, "PDF417")


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
        member_no_name = make_member(email="noname@example.com", first_name="", last_name="")
        reg = self._make_registration(member=member_no_name)
        # save() falls back: first_name -> email; last_name -> ""
        self.assertIn("noname@example.com", str(reg))

    def test_ticket_code_auto_generated(self):
        reg = self._make_registration()
        self.assertTrue(len(reg.ticket_code) > 0)

    def test_ticket_code_starts_with_i2g(self):
        reg = self._make_registration()
        self.assertTrue(reg.ticket_code.startswith("I2G-"))

    def test_ticket_code_unique(self):
        r1 = self._make_registration()
        member2 = make_member(email="user2@example.com")
        r2 = self._make_registration(member=member2)
        self.assertNotEqual(r1.ticket_code, r2.ticket_code)

    def test_attendee_name_property(self):
        reg = self._make_registration(attendee_first_name="John", attendee_last_name="Smith")
        self.assertEqual(reg.attendee_name, "John Smith")

    def test_attendee_name_property_strips_whitespace(self):
        member_no_last = make_member(email="nolast@example.com", first_name="John", last_name="")
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

    def test_save_first_name_fallback_to_email(self):
        member = make_member(email="emailonly@example.com", first_name="", last_name="")
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
        member2 = make_member(email="user2@example.com")
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
            reg.ticket.delete()

    def test_save_keeps_secondary_email_blank_when_collecting(self):
        self.event.allow_secondary_email = True
        self.event.save()
        ContactEmail.objects.create(member=self.member, email_address="sec@example.com", email_type="secondary")
        reg = self._make_registration()
        self.assertEqual(reg.attendee_secondary_email, "")
        self.assertFalse(reg.secondary_email_verified)

    def test_save_does_not_auto_populate_secondary_email_when_flag_off(self):
        ContactEmail.objects.create(member=self.member, email_address="sec@example.com", email_type="secondary")
        reg = self._make_registration()
        self.assertEqual(reg.attendee_secondary_email, "")

    def test_save_preserves_explicit_secondary_email(self):
        self.event.allow_secondary_email = True
        self.event.save()
        ContactEmail.objects.create(member=self.member, email_address="sec@example.com", email_type="secondary")
        reg = self._make_registration(attendee_secondary_email="custom@example.com")
        self.assertEqual(reg.attendee_secondary_email, "custom@example.com")
