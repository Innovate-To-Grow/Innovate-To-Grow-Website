"""Members → Import pages with every kind of row at once: each conflict renders, and the bulk controls work."""

from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, Member, MemberImportBatch
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload

UUID_HEADERS = ["Member UUID", *HEADERS]


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class EveryConflictPageTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.master = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Master")
        self.client.force_login(self.master)
        self.neil = self.member("Neil", "Parkhi", "neil@home.example")
        self.email(self.neil, "neil@work.example", verified=True)
        self.grace = self.member("Grace", "Hopper", "grace@example.com")
        self.email(self.grace, "Twin@Example.com", email_type="other")
        ContactEmail.objects.create(member=None, email_address="twin@example.com")
        ContactEmail.objects.create(member=None, email_address="orphan@example.com")
        self.staff = self.member("Staff", "Person", "staff@example.com", is_staff=True)
        self.email(self.ada, "ada.old@example.com", verified=True)

    def _rows(self):
        def uuid_row(member_uuid, primary, **cells):
            return [member_uuid, *row(primary, **cells)]

        return [
            uuid_row("", "neil@work.example", First_Name="Neil", Last_Name="Parkhi"),  # 2: C7
            uuid_row("", "neil@home.example", First_Name="Neil", Last_Name="Parkhi", Organization="X"),  # 3: C1 with 2
            uuid_row("", "twin@example.com", First_Name="Tw", Last_Name="In"),  # 4: C3
            uuid_row(str(self.ada.pk), "grace@example.com"),  # 5: C4
            uuid_row(
                "00000000-0000-4000-8000-000000000000", "new@example.com", First_Name="New", Last_Name="One"
            ),  # 6: C5
            uuid_row("", "grace@example.com", First_Name="Someone", Last_Name="Else"),  # 7: C6
            uuid_row("", "orphan@example.com", First_Name="Or", Last_Name="Phan"),  # 8: C8
            uuid_row("", "ada@example.com", Secondary_Email="", Active="No", Organization="Acme"),  # 9: ready + risky
            uuid_row("", "", First_Name="No", Last_Name="Address"),  # 10: invalid
            uuid_row("", "fresh@example.com", First_Name="Fresh", Last_Name="Person"),  # 11: create
        ]

    def _stage(self):
        response = self.client.post(
            reverse("admin:authn_member_import_excel"),
            {"excel_file": upload(UUID_HEADERS, self._rows()), "mode": "update_existing"},
        )
        self.assertEqual(response.status_code, 302)
        return MemberImportBatch.objects.get()

    def test_every_conflict_is_detected_and_rendered(self):
        batch = self._stage()

        conflicts = dict(batch.rows.values_list("row_number", "conflict"))
        self.assertEqual(
            conflicts,
            {
                2: "duplicate_in_sheet",
                3: "duplicate_in_sheet",
                4: "ambiguous_address",
                5: "uuid_email_mismatch",
                6: "uuid_not_found",
                7: "name_differs",
                8: "unlinked_address",
                9: "",
                10: "",
                11: "",
            },
        )
        page = self.client.get(reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.assertEqual(page.status_code, 200)
        for text in (
            "C1 · The same person appears more than once in the sheet",
            "C3 · The address exists more than once, differing only in letter case",
            "C4 · The Member UUID and the Primary Email point to different members",
            "C5 · The Member UUID matches nobody",
            "C6 · Found by email, but the name is different",
            "C8 · The address exists, but with no member",
            "Member UUID column found: rows are matched by Member UUID first.",
            "Remove secondary ada.old@example.com (the Secondary Email cell is blank)",
            "Deactivate the member",
            "Missing primary email",
            "Creates the member Fresh Person",
            "Claim the unlinked record twin@example.com for a new member",
            "Another record of this address belongs to a member; merge the duplicates first",
        ):
            with self.subTest(text=text):
                self.assertContains(page, text)

    def test_bulk_choices_ticks_and_the_whole_flow(self):
        batch = self._stage()
        review = reverse("admin:authn_member_import_review", args=[batch.pk])
        base = {"version": 0, "ready-9": "update", "ready-11": "create", "ticks-9": "1"}

        response = self.client.post(
            review, {**base, "bulk-duplicate_in_sheet": "use_first", "action": "bulk:duplicate_in_sheet"}
        )
        self.assertRedirects(response, review)
        self.assertEqual(
            dict(batch.rows.filter(row_number__in=[2, 3]).values_list("row_number", "choice")),
            {2: "use_row", 3: "skip"},
        )

        self.client.post(review, {**base, "version": 1, "action": "tickall:R1"})
        ada_row = batch.rows.get(row_number=9)
        self.assertEqual(len(ada_row.ticks), 1)
        self.assertTrue(ada_row.ticks[0].startswith("R1:"))

        self.client.post(review, {**base, "version": 2, "tick-9": ada_row.ticks, "action": "continue"})
        confirm = reverse("admin:authn_member_import_confirm", args=[batch.pk])
        page = self.client.get(confirm)
        self.assertContains(page, "Contact emails deleted (1)")
        self.assertContains(page, "Row 9: secondary ada.old@example.com")
        self.assertContains(page, "C1 · The same person appears more than once in the sheet: 1 use this row, 1 skip")

        batch.refresh_from_db()
        response = self.client.post(confirm, {"version": batch.choices_version})

        self.assertRedirects(response, reverse("admin:authn_member_import_result", args=[batch.pk]))
        self.assertFalse(ContactEmail.objects.filter(email_address="ada.old@example.com").exists())
        self.neil.refresh_from_db()
        self.assertEqual(self.neil.organization, None)  # row 2 (C7, keep roles) was used; it has no Organization
        self.assertTrue(Member.objects.filter(first_name="Fresh").exists())
        self.ada.refresh_from_db()
        self.assertTrue(self.ada.is_active)  # R7 was not ticked
        result = self.client.get(reverse("admin:authn_member_import_result", args=[batch.pk]))
        self.assertContains(result, "Removes secondary ada.old@example.com")
        self.assertContains(result, "Skipped by choice")

    def test_skip_every_row_that_needs_a_decision(self):
        batch = self._stage()
        review = reverse("admin:authn_member_import_review", args=[batch.pk])
        self.client.post(
            review, {"version": 0, "bulk-duplicate_in_sheet": "use_first", "action": "bulk:duplicate_in_sheet"}
        )

        self.client.post(review, {"version": 1, "action": "skipall"})

        choices = set(batch.rows.filter(status="needs_decision").values_list("choice", flat=True))
        self.assertEqual(choices, {"skip"})

    def test_a_bulk_choice_a_group_does_not_offer_is_refused(self):
        batch = self._stage()
        review = reverse("admin:authn_member_import_review", args=[batch.pk])

        response = self.client.post(
            review, {"version": 0, "bulk-name_differs": "update_same_person", "action": "bulk:name_differs"}
        )

        self.assertRedirects(response, review)
        batch.refresh_from_db()
        self.assertEqual(batch.choices_version, 0)
        self.assertEqual(batch.rows.get(row_number=7).choice, "skip")
