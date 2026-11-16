from apps.authn.models import ContactPhone
from apps.authn.services.members.import_.parsing import PHONE_VERIFIED_IGNORED
from apps.authn.tests.services.members.import_safety.test_import_members_safety import _ImportCase

from ..import_sheets import PHONE_VERIFIED_HEADERS, full_row


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
