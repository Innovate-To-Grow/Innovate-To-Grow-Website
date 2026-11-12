"""The one-step member import never destroys data.

Regression tests for the silent data-loss paths of "Update Existing Members": blank cells deleting every secondary
email or phone, a named secondary deleting the others, a new phone overwriting the old one (and inheriting
"verified"), the flag cells re-subscribing or un-verifying, and the Active column flipping members.
"""

from io import BytesIO
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.export_excel import export_members_to_excel
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.parsing import PHONE_VERIFIED_IGNORED

from .import_sheets import FULL_HEADERS, PHONE_VERIFIED_HEADERS, build_sheet, full_row


class _ImportCase(TestCase):
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(
            password="StrongPass123!", first_name="Ada", last_name="Lovelace", is_active=True
        )
        self.primary = ContactEmail.objects.create(
            member=self.member, email_address="ada@example.com", email_type="primary", verified=True, subscribe=True
        )

    def _email(self, address, email_type="secondary", member=None, **flags):
        return ContactEmail.objects.create(
            member=self.member if member is None else member, email_address=address, email_type=email_type, **flags
        )

    def _phone(self, number, member=None, **flags):
        return ContactPhone.objects.create(
            member=self.member if member is None else member, phone_number=number, region="1-US", **flags
        )

    def _update(self, cells=None, headers=None, primary="ada@example.com"):
        if headers is None:
            sheet = build_sheet(FULL_HEADERS, [full_row(primary, cells)])
        else:
            sheet = build_sheet(headers, [cells])
        return import_members_from_excel(sheet, update_existing=True)

    def _other_member(self, first="Grace", last="Hopper", email="grace@example.com"):
        other = Member.objects.create_user(password="StrongPass123!", first_name=first, last_name=last)
        self._email(email, email_type="primary", member=other, verified=True)
        return other


class SecondaryEmailIsNeverDeletedTests(_ImportCase):
    def test_blank_secondary_cell_keeps_every_secondary(self):
        self._email("one@example.com", verified=True)
        self._email("two@example.com")

        result = self._update()

        self.assertEqual(result.updated_count, 1)
        self.assertEqual(
            set(self.member.contact_emails.filter(email_type="secondary").values_list("email_address", flat=True)),
            {"one@example.com", "two@example.com"},
        )
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Row 2: Secondary Email is blank; kept", result.warnings[0])
        self.assertIn("one@example.com", result.warnings[0])
        self.assertIn("two@example.com", result.warnings[0])
        self.assertEqual(result.warnings[0].member_id, str(self.member.pk))

    def test_missing_secondary_column_keeps_secondaries_without_a_note(self):
        self._email("one@example.com")

        result = self._update(
            ["ada@example.com", "Ada", "Lovelace"], headers=["Primary Email", "First Name", "Last Name"]
        )

        self.assertTrue(self.member.contact_emails.filter(email_address="one@example.com").exists())
        self.assertEqual(result.warnings, [])

    def test_naming_one_secondary_keeps_the_others(self):
        """Export -> re-import wrote one secondary and used to delete the member's others."""
        self._email("one@example.com", verified=True)
        self._email("two@example.com")

        result = self._update({"Secondary Email": "two@example.com"})

        self.assertEqual(
            set(self.member.contact_emails.filter(email_type="secondary").values_list("email_address", flat=True)),
            {"one@example.com", "two@example.com"},
        )
        self.assertEqual(result.warnings, [])

    def test_new_secondary_is_added_and_the_previous_one_becomes_other(self):
        old = self._email("old@example.com", verified=True)

        result = self._update({"Secondary Email": "new@example.com"})

        old.refresh_from_db()
        self.assertEqual(old.email_type, "other")
        self.assertTrue(old.verified)
        new = ContactEmail.objects.get(email_address="new@example.com")
        self.assertEqual(
            (new.member, new.email_type, new.verified, new.subscribe), (self.member, "secondary", False, True)
        )
        self.assertEqual(result.warnings, [])
        self.assertEqual(
            result.details[0]["changes"],
            [
                "Adds new@example.com as the secondary email (unverified, subscribed); the previous secondary "
                'old@example.com becomes "other"'
            ],
        )

    def test_new_secondary_starts_unverified_whatever_the_sheet_says(self):
        result = self._update({"Secondary Email": "new@example.com", "Secondary Verified": "TRUE"})

        self.assertFalse(ContactEmail.objects.get(email_address="new@example.com").verified)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("new@example.com is added unverified", result.warnings[0])

    def test_secondary_owned_by_another_member_is_never_moved(self):
        other = self._other_member()
        theirs = self._email("shared@example.com", member=other, verified=True)
        mine = self._email("mine@example.com")

        result = self._update({"Secondary Email": "shared@example.com"})

        theirs.refresh_from_db()
        mine.refresh_from_db()
        self.assertEqual((theirs.member, theirs.email_type), (other, "secondary"))
        self.assertEqual((mine.member, mine.email_type), (self.member, "secondary"))
        self.assertEqual(
            result.warnings,
            [
                f"Row 2: Secondary Email shared@example.com belongs to Grace Hopper (member {other.pk}); not added "
                "(an import never moves a contact from one member to another)"
            ],
        )

    def test_unlinked_secondary_is_attached_unverified(self):
        """A contact email with no member loses nothing by being attached; it starts unverified (plan §4.2)."""
        unlinked = ContactEmail.objects.create(member=None, email_address="loose@example.com", verified=True)

        result = self._update({"Secondary Email": "loose@example.com", "Secondary Verified": "TRUE"})

        unlinked.refresh_from_db()
        self.assertEqual((unlinked.member, unlinked.email_type, unlinked.verified), (self.member, "secondary", False))
        self.assertIn("Attaches loose@example.com (a contact email with no member)", result.details[0]["changes"][0])
        self.assertIn("loose@example.com is added unverified", result.warnings[0])

    def test_secondary_equal_to_the_primary_is_ignored(self):
        self._email("one@example.com")

        result = self._update({"Secondary Email": "ADA@example.com"})

        self.assertTrue(self.member.contact_emails.filter(email_address="one@example.com").exists())
        self.assertEqual(result.warnings, ["Row 2: Secondary Email is the same as the Primary Email; ignored"])

    def test_invalid_secondary_is_ignored(self):
        result = self._update({"Secondary Email": "not an email"})

        self.assertFalse(ContactEmail.objects.filter(email_address="not an email").exists())
        self.assertEqual(
            result.warnings, ["Row 2: Secondary Email 'not an email' is not a valid email address; ignored"]
        )

    def test_secondary_matching_case_only_duplicates_is_not_added(self):
        other = self._other_member()
        self._email("Twin@example.com", member=other)
        self._email("twin@example.com", email_type="other", member=other)

        result = self._update({"Secondary Email": "TWIN@example.com"})

        self.assertFalse(self.member.contact_emails.filter(email_address__iexact="twin@example.com").exists())
        self.assertIn("matches 2 contact emails that differ only in letter case; not added", result.warnings[0])

    def test_flags_of_an_existing_secondary_apply_only_in_the_safe_direction(self):
        """FALSE unsubscribes (an opt-out); un-verifying is a risky change that needs its tick."""
        secondary = self._email("one@example.com", verified=True, subscribe=True)

        result = self._update(
            {"Secondary Email": "one@example.com", "Secondary Verified": "FALSE", "Secondary Subscribed": "FALSE"}
        )

        secondary.refresh_from_db()
        self.assertEqual((secondary.verified, secondary.subscribe), (True, False))
        self.assertEqual(
            result.warnings,
            [
                "Row 2: Secondary Verified is FALSE, but one@example.com is verified; left verified (un-verifying "
                "needs its tick)"
            ],
        )

    def test_new_secondary_of_a_member_unsubscribed_everywhere_stays_unsubscribed(self):
        self.primary.subscribe = False
        self.primary.save(update_fields=["subscribe"])

        result = self._update({"Secondary Email": "new@example.com", "Secondary Subscribed": "TRUE"})

        self.assertFalse(ContactEmail.objects.get(email_address="new@example.com").subscribe)
        self.assertIn("new@example.com is added unsubscribed", result.warnings[0])
        self.assertIn("re-subscribing needs the person's consent", result.warnings[0])

    def test_new_secondary_of_a_member_unsubscribed_everywhere_is_unsubscribed_silently_on_a_blank_cell(self):
        self.primary.subscribe = False
        self.primary.save(update_fields=["subscribe"])

        result = self._update({"Secondary Email": "new@example.com"})

        self.assertFalse(ContactEmail.objects.get(email_address="new@example.com").subscribe)
        self.assertEqual(result.warnings, [])

    def test_new_secondary_of_a_subscribed_member_follows_the_sheet(self):
        result = self._update({"Secondary Email": "new@example.com", "Secondary Subscribed": "No"})

        self.assertFalse(ContactEmail.objects.get(email_address="new@example.com").subscribe)
        self.assertEqual(result.warnings, [])


class PhoneIsNeverDeletedOrOverwrittenTests(_ImportCase):
    def test_blank_phone_cell_keeps_every_phone(self):
        self._phone("2095550001", verified=True)
        self._phone("2095550002")

        result = self._update()

        self.assertEqual(
            set(self.member.contact_phones.values_list("phone_number", flat=True)), {"2095550001", "2095550002"}
        )
        self.assertIn("Row 2: Phone Number is blank; kept", result.warnings[0])

    def test_blank_phone_cell_never_locks_out_a_member_who_signs_in_by_phone(self):
        self.primary.verified = False
        self.primary.save(update_fields=["verified"])
        phone = self._phone("2095550001", verified=True)

        self._update()

        phone.refresh_from_db()
        self.assertTrue(phone.verified)
        self.assertEqual(phone.member, self.member)

    def test_new_number_is_added_and_never_inherits_verified(self):
        old = self._phone("2095550001", verified=True, subscribe=True)

        result = self._update({"Phone Number": "+1 (209) 555-0002"})

        old.refresh_from_db()
        self.assertEqual((old.phone_number, old.verified, old.subscribe), ("2095550001", True, True))
        new = ContactPhone.objects.get(phone_number="2095550002")
        self.assertEqual((new.member, new.verified), (self.member, False))
        self.assertEqual(result.warnings, [])
        self.assertEqual(
            result.details[0]["changes"],
            [
                "Adds phone +12095550002 (unverified, not subscribed); keeps +12095550001 (an import never replaces "
                "a number in place)"
            ],
        )

    def test_new_number_starts_unverified_whatever_the_sheet_says(self):
        result = self._update(
            full_row(
                "ada@example.com", {"Phone Number": "+12095550002", "Phone Verified": "TRUE"}, PHONE_VERIFIED_HEADERS
            ),
            headers=PHONE_VERIFIED_HEADERS,
        )

        self.assertFalse(ContactPhone.objects.get(phone_number="2095550002").verified)
        # The column is reported once for the file; the row itself has nothing to say about it.
        self.assertEqual(result.warnings, [PHONE_VERIFIED_IGNORED])

    def test_number_owned_by_another_member_is_never_moved(self):
        other = self._other_member()
        theirs = self._phone("2095550009", member=other, verified=True)

        result = self._update({"Phone Number": "+12095550009"})

        theirs.refresh_from_db()
        self.assertEqual(theirs.member, other)
        self.assertFalse(self.member.contact_phones.exists())
        self.assertIn(f"+12095550009 belongs to Grace Hopper (member {other.pk}); not added", result.warnings[0])

    def test_unlinked_number_is_not_attached(self):
        unlinked = ContactPhone.objects.create(member=None, phone_number="2095550009", region="1-US")

        result = self._update({"Phone Number": "+12095550009"})

        unlinked.refresh_from_db()
        self.assertIsNone(unlinked.member)
        self.assertIn("Phone Number +12095550009 is a contact with no member; not added", result.warnings[0])

    def test_new_number_is_not_subscribed_when_the_members_numbers_are_all_unsubscribed(self):
        self._phone("2095550001", subscribe=False)

        result = self._update({"Phone Number": "+12095550002", "Phone Subscribed": "TRUE"})

        self.assertFalse(ContactPhone.objects.get(phone_number="2095550002").subscribe)
        self.assertTrue(any("is added unsubscribed" in note for note in result.warnings))

    def test_new_number_follows_the_sheet_for_a_member_without_phones_or_with_a_subscribed_one(self):
        self._update({"Phone Number": "+12095550002", "Phone Subscribed": "TRUE"})
        self.assertTrue(ContactPhone.objects.get(phone_number="2095550002").subscribe)

        result = self._update({"Phone Number": "+12095550003", "Phone Subscribed": "Yes"})
        self.assertTrue(ContactPhone.objects.get(phone_number="2095550003").subscribe)
        self.assertFalse(any("unsubscribed" in note for note in result.warnings))

    def test_flags_of_an_existing_number_never_resubscribe_without_a_tick(self):
        phone = self._phone("2095550001", subscribe=False)

        result = self._update({"Phone Number": "+12095550001", "Phone Subscribed": "TRUE"})

        phone.refresh_from_db()
        self.assertFalse(phone.subscribe)
        self.assertEqual(
            result.warnings,
            [
                "Row 2: Phone Subscribed is TRUE, but +12095550001 is unsubscribed; left unsubscribed (re-subscribing "
                "needs the person's consent and its tick)"
            ],
        )


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


class NoMessagesSentTests(_ImportCase):
    def test_adding_contacts_sends_no_mail_and_no_sms(self):
        self._email("old@example.com")
        self._phone("2095550001")

        with patch("apps.authn.services.sms.sns_verify._publish_sms") as sms:
            result = self._update({"Secondary Email": "new@example.com", "Phone Number": "+12095550002"})

        self.assertEqual(result.updated_count, 1)
        self.assertEqual(mail.outbox, [])
        sms.assert_not_called()
