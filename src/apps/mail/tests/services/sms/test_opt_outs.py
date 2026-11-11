"""The SMS opt-out list: lookups, the changes staff and AWS make to it, the once-only unsubscribe of the members'
phones (never undone), and its place in core's send check."""

from datetime import UTC, datetime

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.authn.models import ContactPhone
from apps.core.services.aws import sms_opt_outs as core_opt_outs
from apps.core.services.aws.sms_errors import SmsOptedOut
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import SmsOptOut
from apps.mail.services.sms import opt_outs

from .policy_helpers import add_phone, opt_out

NUMBER = "+12095550101"


class NormalizePhoneTests(SimpleTestCase):
    def test_numbers_the_site_can_text_become_e164(self):
        cases = {
            "+12095550101": NUMBER,
            "(209) 555-0101": NUMBER,
            "209.555.0101": NUMBER,
            "12095550101": NUMBER,
            " +1 209 555 0101 ": NUMBER,
            "+447700900123": "+447700900123",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(opt_outs.normalize_phone(value), expected)

    def test_anything_else_is_empty(self):
        for value in ("", None, "555-0101", "abc", "+0123", "22095550101", "+1 209"):
            with self.subTest(value=value):
                self.assertEqual(opt_outs.normalize_phone(value), "")

    def test_only_us_numbers_map_to_contact_phones(self):
        self.assertEqual(opt_outs.us_national_digits(NUMBER), "2095550101")
        self.assertEqual(opt_outs.us_national_digits("+447700900123"), "")


class OptOutListTests(TestCase):
    def setUp(self):
        self.member = make_member(email="ada@example.com", first_name="Ada")
        self.phone = add_phone(self.member, "2095550101")

    def test_lookups_see_only_active_rows(self):
        opt_out(NUMBER)
        opt_out("+12095550102", cleared_at=timezone.now())
        self.assertTrue(opt_outs.is_opted_out("(209) 555-0101"))
        self.assertFalse(opt_outs.is_opted_out("+12095550102"))
        self.assertFalse(opt_outs.is_opted_out("not a number"))
        self.assertEqual(opt_outs.opted_out_numbers([NUMBER, "+12095550102", ""]), frozenset({NUMBER}))
        self.assertEqual(opt_outs.opted_out_numbers([]), frozenset())

    def test_split_keeps_order_and_names_the_skipped(self):
        opt_out(NUMBER)
        rows = [{"phone": "+12095550199"}, {"phone": NUMBER}, {"phone": "+12095550198"}]
        kept, skipped = opt_outs.split_opted_out(rows)
        self.assertEqual(kept, [rows[0], rows[2]])
        self.assertEqual(skipped, [rows[1]])

    def test_a_send_refusal_adds_the_number_and_unsubscribes_its_phone_once(self):
        opt_outs.record_refusal(NUMBER)

        row = SmsOptOut.objects.get(phone_number=NUMBER)
        self.assertEqual(row.source, SmsOptOut.Source.SEND_REFUSAL)
        self.assertIsNotNone(row.contacts_unsubscribed_at)
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.subscribe)
        self.assertTrue(self.phone.verified)

        # The member subscribes again while the opt-out stands: a later refusal does not undo their choice.
        ContactPhone.objects.filter(pk=self.phone.pk).update(subscribe=True)
        opt_outs.record_refusal(NUMBER)
        self.phone.refresh_from_db()
        self.assertTrue(self.phone.subscribe)
        self.assertEqual(SmsOptOut.objects.count(), 1)

    def test_a_refusal_reopens_a_number_that_had_opted_back_in(self):
        row = opt_out(
            NUMBER, cleared_at=timezone.now(), cleared_reason="START", contacts_unsubscribed_at=timezone.now()
        )
        opt_outs.record_refusal(NUMBER)
        row.refresh_from_db()
        self.assertIsNone(row.cleared_at)
        self.assertEqual((row.source, row.cleared_reason), (SmsOptOut.Source.SEND_REFUSAL, ""))
        self.assertIsNotNone(row.contacts_unsubscribed_at)

    def test_a_refusal_for_no_number_changes_nothing(self):
        opt_outs.record_refusal("")
        self.assertFalse(SmsOptOut.objects.exists())

    def test_unsubscribing_skips_cleared_and_foreign_numbers(self):
        cleared = opt_out(NUMBER, cleared_at=timezone.now())
        self.assertEqual(opt_outs.unsubscribe_contact_phones(cleared), 0)
        foreign = opt_out("+447700900123")
        self.assertEqual(opt_outs.unsubscribe_contact_phones(foreign), 0)
        foreign.refresh_from_db()
        self.assertIsNotNone(foreign.contacts_unsubscribed_at)
        self.phone.refresh_from_db()
        self.assertTrue(self.phone.subscribe)

    def test_staff_add_and_lift_their_own_opt_outs_only(self):
        staff = make_superuser()
        row = opt_outs.add_staff_opt_out("(209) 555-0101", note="Asked by email", actor=staff)
        self.assertEqual((row.source, row.note, row.created_by), (SmsOptOut.Source.STAFF, "Asked by email", staff))
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.subscribe)

        self.assertTrue(opt_outs.lift_staff_opt_out(row, actor=staff))
        row.refresh_from_db()
        self.assertIsNotNone(row.cleared_at)
        self.assertFalse(opt_outs.lift_staff_opt_out(row, actor=staff))
        # Lifting never subscribes the phone again.
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.subscribe)

        aws_row = opt_out("+12095550102")
        self.assertFalse(opt_outs.lift_staff_opt_out(aws_row, actor=staff))
        with self.assertRaises(ValueError):
            opt_outs.add_staff_opt_out("12", note="", actor=staff)

    def test_matching_contact_phones_names_the_members(self):
        matches = opt_outs.matching_contact_phones([NUMBER, "+12095550102", "+447700900123"])
        self.assertEqual(list(matches), [NUMBER])
        self.assertEqual(matches[NUMBER][0].member, self.member)


class SendCheckTests(TestCase):
    """Mail registers the list in core's send check (``MailConfig.ready``), so every send path honours it."""

    def test_the_registered_list_refuses_an_opted_out_destination(self):
        self.assertIs(core_opt_outs._hooks["is_opted_out"], opt_outs.is_opted_out)
        self.assertIs(core_opt_outs._hooks["record_refusal"], opt_outs.record_refusal)
        opt_out(NUMBER, opted_out_at=datetime(2026, 11, 1, tzinfo=UTC))
        with self.assertRaises(SmsOptedOut):
            core_opt_outs.refuse_if_opted_out(NUMBER)
        core_opt_outs.refuse_if_opted_out("+12095550102")
