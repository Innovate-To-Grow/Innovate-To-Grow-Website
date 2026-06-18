from django.test import TestCase

from apps.event.admin.registration.forms import EventRegistrationAdminForm
from apps.event.models import EventRegistration
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket


class EventRegistrationAdminFormCleanTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Form Event", collect_phone=True)
        self.ticket = make_ticket(self.event, name="GA")
        self.member = make_member(email="form-member@example.com")

    def _base_data(self, **overrides):
        data = {
            "member": str(self.member.pk),
            "event": str(self.event.pk),
            "ticket": str(self.ticket.pk),
            "attendee_first_name": "",
            "attendee_last_name": "",
            "attendee_email": "",
            "attendee_secondary_email": "",
            "attendee_phone": "",
            "attendee_organization": "",
            "phone_verified": "",
            "question_answers": "[]",
        }
        data.update(overrides)
        return data

    def test_clean_rejects_ticket_from_other_event(self):
        other_event = make_event(name="Other Event")
        other_ticket = make_ticket(other_event, name="VIP")
        form = EventRegistrationAdminForm(data=self._base_data(ticket=str(other_ticket.pk)))

        self.assertFalse(form.is_valid())
        self.assertIn("ticket", form.errors)
        self.assertIn("does not belong", form.errors["ticket"][0])

    def test_clean_rejects_duplicate_member_event(self):
        make_registration(self.member, self.event, self.ticket)
        form = EventRegistrationAdminForm(data=self._base_data())

        # The form's clean() detects the duplicate and raises a member error; the
        # model's unique_together validation also fires. Either way the form is
        # invalid and references the duplicate. We assert the duplicate is reported.
        self.assertFalse(form.is_valid())
        all_errors = " ".join(msg for messages in form.errors.values() for msg in messages)
        self.assertTrue(
            "already registered" in all_errors or "already exists" in all_errors,
            msg=f"Unexpected errors: {dict(form.errors)}",
        )

    def test_clean_duplicate_branch_when_instance_has_no_pk(self):
        # UUID primary keys are populated at construction, so for a genuine "add"
        # we must clear the pk to exercise the form's own duplicate-member guard
        # (the branch that raises the "already registered" member error).
        make_registration(self.member, self.event, self.ticket)
        instance = EventRegistration()
        instance.pk = None
        form = EventRegistrationAdminForm(data=self._base_data(), instance=instance)

        self.assertFalse(form.is_valid())
        self.assertIn("member", form.errors)
        self.assertIn("already registered", form.errors["member"][0])

    def test_clean_question_answers_blank_becomes_empty_list(self):
        form = EventRegistrationAdminForm(data=self._base_data(question_answers=""))
        form.is_valid()
        self.assertEqual(form.cleaned_data.get("question_answers"), [])

    def test_clean_question_answers_rejects_non_list(self):
        form = EventRegistrationAdminForm(data=self._base_data(question_answers='{"a": 1}'))
        self.assertFalse(form.is_valid())
        self.assertIn("question_answers", form.errors)
        self.assertIn("JSON list", form.errors["question_answers"][0])

    def test_clean_question_answers_accepts_list(self):
        form = EventRegistrationAdminForm(
            data=self._base_data(question_answers='[{"question_id": "1", "question_text": "Q", "answer": "A"}]')
        )
        form.is_valid()
        self.assertEqual(
            form.cleaned_data.get("question_answers"),
            [{"question_id": "1", "question_text": "Q", "answer": "A"}],
        )

    def test_clean_attendee_phone_empty_passes(self):
        form = EventRegistrationAdminForm(data=self._base_data(attendee_phone=""))
        form.is_valid()
        self.assertEqual(form.cleaned_data.get("attendee_phone"), "")

    def test_clean_attendee_phone_rejects_invalid(self):
        form = EventRegistrationAdminForm(data=self._base_data(attendee_phone="abc"))
        self.assertFalse(form.is_valid())
        self.assertIn("attendee_phone", form.errors)

    def test_clean_attendee_phone_accepts_valid(self):
        form = EventRegistrationAdminForm(data=self._base_data(attendee_phone="5551234567"))
        form.is_valid()
        self.assertEqual(form.cleaned_data.get("attendee_phone"), "5551234567")

    def test_clean_attendee_phone_accepts_us_e164(self):
        # Regression: the admin form previously validated with a "0-GENERIC" sentinel region
        # whose country code "0" never stripped the +1, rejecting valid US E.164 numbers.
        form = EventRegistrationAdminForm(data=self._base_data(attendee_phone="+12095765113"))
        form.is_valid()
        self.assertEqual(form.cleaned_data.get("attendee_phone"), "+12095765113")

    def test_init_limits_ticket_queryset_for_existing_instance(self):
        registration = make_registration(self.member, self.event, self.ticket)
        other_event = make_event(name="Excluded Event")
        excluded_ticket = make_ticket(other_event, name="Excluded")

        form = EventRegistrationAdminForm(instance=registration)

        ticket_qs = form.fields["ticket"].queryset
        self.assertIn(self.ticket, ticket_qs)
        self.assertNotIn(excluded_ticket, ticket_qs)

    def test_clean_with_no_member_or_event_does_not_crash(self):
        # Form bound with missing required fields still runs clean() without raising.
        form = EventRegistrationAdminForm(data={"question_answers": "[]"})
        self.assertFalse(form.is_valid())
        self.assertNotIn(EventRegistration, form.errors)
