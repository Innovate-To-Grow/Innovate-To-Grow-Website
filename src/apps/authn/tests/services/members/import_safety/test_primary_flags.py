from io import BytesIO
from unittest.mock import patch

from django.core import mail

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.export.excel import export_members_to_excel
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.workbook.parsing import PHONE_VERIFIED_IGNORED
from apps.authn.tests.services.members.import_safety.test_import_members_safety import _ImportCase

from ..import_sheets import FULL_HEADERS, build_sheet, full_row


class PrimaryFlagsTests(_ImportCase):
    def test_subscribed_true_never_resubscribes(self):
        self.primary.subscribe = False
        self.primary.save(update_fields=["subscribe"])

        result = self._update({"Primary Subscribed": "TRUE"})

        self.primary.refresh_from_db()
        self.assertFalse(self.primary.subscribe)
        self.assertEqual(
            result.warnings,
            [
                "Row 2: Primary Subscribed is TRUE, but ada@example.com is unsubscribed; left unsubscribed "
                "(re-subscribing needs the person's consent and its tick)"
            ],
        )

    def test_subscribed_false_unsubscribes(self):
        result = self._update({"Primary Subscribed": "FALSE"})

        self.primary.refresh_from_db()
        self.assertFalse(self.primary.subscribe)
        self.assertEqual(result.warnings, [])

    def test_verified_false_never_unverifies(self):
        result = self._update({"Primary Verified": "No"})

        self.primary.refresh_from_db()
        self.assertTrue(self.primary.verified)
        self.assertIn("Primary Verified is FALSE, but ada@example.com is verified; left verified", result.warnings[0])

    def test_verified_true_never_verifies_without_its_tick(self):
        """A verified address is a sign-in factor: only a ticked review (R9) marks one verified."""
        self.primary.verified = False
        self.primary.save(update_fields=["verified"])

        result = self._update({"Primary Verified": "Yes"})

        self.primary.refresh_from_db()
        self.assertFalse(self.primary.verified)
        self.assertIn(
            "Primary Verified is TRUE, but ada@example.com is unverified; left unverified", result.warnings[0]
        )

    def test_unrecognised_text_keeps_the_stored_flag(self):
        """ "N/A" used to read as FALSE and unsubscribe the address."""
        result = self._update({"Primary Subscribed": "N/A", "Primary Verified": "x"})

        self.primary.refresh_from_db()
        self.assertTrue(self.primary.subscribe)
        self.assertTrue(self.primary.verified)
        self.assertEqual(
            result.warnings,
            [
                "Row 2: Primary Verified cell 'x' is not TRUE or FALSE; it was ignored",
                "Row 2: Primary Subscribed cell 'N/A' is not TRUE or FALSE; it was ignored",
            ],
        )


class ActiveColumnTests(_ImportCase):
    def test_active_no_does_not_deactivate_an_existing_member(self):
        result = self._update({"Active": "No"})

        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Row 2: Active is FALSE, but the member is active; left active", result.warnings[0])

    def test_active_yes_neither_reactivates_nor_ends_an_unfinished_signup(self):
        Member.objects.filter(pk=self.member.pk).update(is_active=False, registration_pending=True)

        result = self._update({"Active": "Yes"})

        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertTrue(self.member.registration_pending)
        self.assertIn("self-service sign-up is unfinished; an import never activates it", result.warnings[0])

    def test_unchanged_active_cell_is_silent(self):
        result = self._update({"Active": "Yes"})

        self.assertEqual(result.warnings, [])

    def test_active_column_still_applies_to_new_members(self):
        result = import_members_from_excel(build_sheet(FULL_HEADERS, [full_row("new@example.com", {"Active": "No"})]))

        self.assertEqual(result.created_count, 1)
        self.assertFalse(ContactEmail.objects.get(email_address="new@example.com").member.is_active)


class RoundTripTests(_ImportCase):
    def _snapshot(self):
        # ``updated_at`` included: an unchanged row must not be written at all.
        emails = sorted(
            ContactEmail.objects.values_list(
                "pk", "member_id", "email_address", "email_type", "verified", "subscribe", "updated_at"
            )
        )
        phones = sorted(
            ContactPhone.objects.values_list(
                "pk", "member_id", "phone_number", "region", "verified", "subscribe", "updated_at"
            )
        )
        members = sorted(
            Member.objects.values_list(
                "pk",
                "first_name",
                "last_name",
                "middle_name",
                "title",
                "organization",
                "is_active",
                "is_staff",
                "registration_pending",
                "updated_at",
            )
        )
        return emails, phones, members

    def test_export_then_reimport_writes_nothing_and_reports_only_the_ignored_phone_verified_column(self):
        # Ada: two secondaries (the export writes only one), a verified phone.
        self._email("one@example.com", verified=True)
        self._email("two@example.com", subscribe=True)
        self._phone("2095550001", verified=True)
        Member.objects.filter(pk=self.member.pk).update(organization="Acme", title="Engineer")
        # Unsubscribed and unverified, with an "other" address.
        quiet = Member.objects.create_user(password="StrongPass123!", first_name="Quiet", last_name="One")
        self._email("quiet@example.com", email_type="primary", member=quiet, verified=False, subscribe=False)
        self._email("quiet-other@example.com", email_type="other", member=quiet, subscribe=False)
        # An unfinished sign-up, and a staff member (the importer is not an I2G Master).
        pending = Member.objects.create_user(password="StrongPass123!", first_name="Pen", last_name="Ding")
        Member.objects.filter(pk=pending.pk).update(is_active=False, registration_pending=True)
        self._email("pending@example.com", email_type="primary", member=pending)
        staff = Member.objects.create_user(password="StrongPass123!", first_name="Staff", last_name="Er", is_staff=True)
        self._email("staff@example.com", email_type="primary", member=staff, verified=True)
        # A phone-only member: the export has no Primary Email for them.
        phone_only = Member.objects.create_user(password="StrongPass123!", first_name="Phone", last_name="Only")
        self._phone("2095550099", member=phone_only, verified=True)

        export = export_members_to_excel(Member.objects.order_by("first_name"))
        before = self._snapshot()

        with patch("apps.authn.services.sms.sns_verify._publish_sms") as sms:
            result = import_members_from_excel(BytesIO(export), update_existing=True, allow_privilege_fields=False)

        self.assertEqual(self._snapshot(), before)
        # The staff member's row is skipped: without a permission check, only an I2G Master changes staff accounts.
        self.assertEqual(result.updated_count, 3)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(len(result.errors), 2)
        self.assertTrue(any("Missing primary email" in error for error in result.errors))
        self.assertTrue(any("You do not have permission to update Staff Er" in error for error in result.errors))
        # The export writes a Phone Verified column; the import says once that it ignored it, and nothing else.
        self.assertEqual(result.warnings, [PHONE_VERIFIED_IGNORED])
        self.assertEqual(mail.outbox, [])
        sms.assert_not_called()
