"""What the review reads for a sheet (``load_snapshot``), the part each row keeps, and the fingerprint the apply checks.

Addresses match ignoring case, but case-only duplicates stay separate records. The fingerprint hashes values, so a
queryset ``.update()`` (which skips ``auto_now``) is caught, while a member signing in does not count as a change.
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_.parsing import parse_row
from apps.authn.services.members.import_.review.lookup import (
    EmailRecord,
    MemberRecord,
    address_key,
    fingerprint,
    load_snapshot,
    row_slice,
    snapshot_from_slice,
    us_phone,
)
from apps.authn.tests.services.members.import_.helpers import ImportTestCase


def parsed(number=2, **cells):
    return parse_row(number, cells)


class SnapshotTests(ImportTestCase):
    def test_addresses_match_ignoring_case(self):
        values = parsed(primary_email="Ada@EXAMPLE.com")

        snapshot = load_snapshot([values])

        self.assertEqual(address_key("  Ada@EXAMPLE.com "), "ada@example.com")
        self.assertEqual([record.address for record in snapshot.email_records("ADA@example.COM")], ["ada@example.com"])
        self.assertEqual(snapshot.email_records(None), [])

    def test_case_only_duplicates_stay_separate_in_creation_order(self):
        second = self.email(self.ada, "DUP@example.com")
        first = ContactEmail.objects.create(member=None, email_address="dup@example.com")
        ContactEmail.objects.filter(pk=first.pk).update(created_at=second.created_at - timedelta(seconds=1))

        snapshot = load_snapshot([parsed(primary_email="Dup@Example.com")])

        self.assertEqual([r.id for r in snapshot.email_records("dup@example.com")], [str(first.pk), str(second.pk)])
        self.assertEqual([r.member for r in snapshot.email_records("dup@example.com")], [None, str(self.ada.pk)])

    def test_owners_are_read_with_every_contact(self):
        work = self.email(self.ada, "ada.work@example.com", verified=True)
        mobile = self.phone(self.ada, "2095550101", verified=True)
        grace = self.member("Grace", "Hopper", "grace@example.com")

        snapshot = load_snapshot([parsed(primary_email="ada@example.com", secondary_email="grace@example.com")])

        ada = snapshot.members[str(self.ada.pk)]
        self.assertEqual(set(snapshot.members), {str(self.ada.pk), str(grace.pk)})
        self.assertEqual({email.address for email in ada.emails}, {"ada@example.com", "ada.work@example.com"})
        self.assertEqual([phone.id for phone in ada.phones], [str(mobile.pk)])
        self.assertEqual(ada.email(str(work.pk)).type, "secondary")
        self.assertIsNone(ada.email("missing"))
        self.assertIsInstance(snapshot.objects[str(self.ada.pk)], Member)
        self.assertEqual(ada.verified_contacts(), {email.id for email in ada.emails} | {str(mobile.pk)})

    def test_phone_numbers_and_member_uuids(self):
        mobile = self.phone(self.ada, "2095550101")
        unknown = str(uuid.uuid4())
        rows = [
            parsed(primary_email="x@example.com", phone_number="(209) 555-0101", member_uuid=str(self.ada.pk)),
            parsed(3, primary_email="y@example.com", phone_number="12345", member_uuid=unknown),
        ]

        snapshot = load_snapshot(rows)

        self.assertEqual(list(snapshot.phones), ["2095550101"])
        self.assertEqual(snapshot.phones["2095550101"].id, str(mobile.pk))
        self.assertEqual(snapshot.phones["2095550101"].e164, "+12095550101")
        self.assertEqual(snapshot.uuids, {str(self.ada.pk): str(self.ada.pk), unknown: None})
        self.assertIn(str(self.ada.pk), snapshot.members)

    @patch("apps.authn.services.members.import_.review.lookup.CHUNK", 1)
    def test_lookups_run_in_chunks_without_losing_records(self):
        grace = self.member("Grace", "Hopper", "grace@example.com")
        self.phone(self.ada, "2095550101")
        self.phone(grace, "2095550102")
        rows = [
            parsed(primary_email="ada@example.com", phone_number="2095550101", member_uuid=str(grace.pk)),
            parsed(3, primary_email="grace@example.com", phone_number="2095550102", member_uuid=str(self.ada.pk)),
            parsed(4, primary_email="new@example.com", secondary_email="ADA@example.com"),
        ]

        snapshot = load_snapshot(rows)

        self.assertEqual(set(snapshot.emails), {"ada@example.com", "grace@example.com"})
        self.assertEqual(set(snapshot.phones), {"2095550101", "2095550102"})
        self.assertEqual(set(snapshot.members), {str(self.ada.pk), str(grace.pk)})
        self.assertEqual(set(snapshot.uuids.values()), {str(self.ada.pk), str(grace.pk)})

    def test_us_phone(self):
        cases = {
            "+12095550101": ("2095550101", "1-US"),
            "+2095550101": ("2095550101", "1-US"),
            "+1234567890": None,
            "+442079460958": None,
            "": None,
            None: None,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(us_phone(raw), expected)


class RowSliceTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.values = parsed(primary_email="ada@example.com", phone_number="2095550199", member_uuid=str(uuid.uuid4()))

    def current(self) -> str:
        return fingerprint(row_slice(load_snapshot([self.values]), self.values))

    def test_a_slice_holds_only_what_its_row_read(self):
        self.member("Grace", "Hopper", "grace@example.com")

        data = row_slice(load_snapshot([self.values, parsed(3, primary_email="grace@example.com")]), self.values)

        self.assertEqual(list(data["emails"]), ["ada@example.com"])
        self.assertEqual(data["phones"], {"2095550199": None})
        self.assertEqual(list(data["uuids"].values()), [None])
        self.assertEqual(list(data["members"]), [str(self.ada.pk)])

    def test_the_snapshot_is_rebuilt_from_a_slice(self):
        self.phone(self.ada, "2095550101", verified=True)
        values = parsed(primary_email="ada@example.com", phone_number="2095550101", member_uuid=str(self.ada.pk))
        snapshot = load_snapshot([values])

        rebuilt = snapshot_from_slice(row_slice(snapshot, values))

        self.assertEqual(rebuilt.members, snapshot.members)
        self.assertEqual(rebuilt.emails, snapshot.emails)
        self.assertEqual(rebuilt.phones, snapshot.phones)
        self.assertEqual(rebuilt.uuids, snapshot.uuids)
        self.assertEqual(rebuilt.objects, {})

    def test_the_fingerprint_ignores_a_sign_in_but_not_a_changed_flag(self):
        before = self.current()

        Member.objects.filter(pk=self.ada.pk).update(last_login=timezone.now())
        self.assertEqual(self.current(), before)

        ContactEmail.objects.filter(email_address="ada@example.com").update(verified=False)
        self.assertNotEqual(self.current(), before)

    def test_the_fingerprint_sees_a_number_or_an_address_that_appeared(self):
        before = self.current()

        ContactPhone.objects.create(member=None, phone_number="2095550199", region="1-US")

        self.assertNotEqual(self.current(), before)


class MemberRecordTests(ImportTestCase):
    def test_labels_roles_and_privilege(self):
        older = EmailRecord("e1", "old@example.com", "primary", "m1", True, True, created="2024-01-01T00:00:00")
        newer = EmailRecord("e2", "new@example.com", "primary", "m1", False, True, created="2025-01-01T00:00:00")
        record = MemberRecord(id="m1", emails=[newer, older])

        self.assertEqual((record.pk, record.label, record.privileged), ("m1", "Unnamed member (member m1)", False))
        self.assertEqual(record.primary, older)
        self.assertEqual(record.emails_of_type("primary"), [newer, older])
        self.assertTrue(MemberRecord(id="m2", is_superuser=True).privileged)
        self.assertIsNone(MemberRecord(id="m3").primary)
        self.assertEqual(
            MemberRecord(id="m4", first_name="Ada", middle_name="A.", last_name="King").full_name, "Ada A. King"
        )
