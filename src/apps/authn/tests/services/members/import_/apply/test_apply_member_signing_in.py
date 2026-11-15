from unittest.mock import patch

from django.utils import timezone

from apps.authn.models import ContactEmail, Member
from apps.authn.services.members.import_ import contacts as contacts_module
from apps.authn.services.members.import_.contacts import ContactWriteError
from apps.authn.tests.services.members.import_.apply.test_apply import _ApplyCase
from apps.authn.tests.services.members.import_.helpers import row


class ApplyTests(_ApplyCase):
    def test_a_member_signing_in_does_not_make_the_review_stale(self):
        Member.objects.filter(pk=self.ada.pk).update(last_login=timezone.now())

        self.assertEqual(self.confirm(self.batch).status, "applied")

    def test_a_warning_that_changed_since_the_review_sends_its_row_back(self):
        # A review staged under an older rule showed no warning on row 3; the apply's fresh analysis sets its Secondary
        # Email aside (V8). The row goes back to review instead of applying a plan nobody saw.
        ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        rows = [
            row("one@example.com", First_Name="One", Secondary_Email="lab@example.com"),
            row("two@example.com", First_Name="Two", Secondary_Email="lab@example.com"),
        ]
        batch = self.stage(rows, self.admin)
        batch.rows.filter(row_number=3).update(warnings=[])

        result = self.confirm(batch)

        self.assertEqual((result.status, result.rows), ("stale", [3]))
        self.assertFalse(Member.objects.filter(first_name__in=["One", "Two"]).exists())
        stale = batch.rows.get(row_number=3)
        self.assertEqual((stale.choice, stale.changed_since_review), ("skip", True))
        self.assertEqual([warning["code"] for warning in stale.warnings], ["V8"])
        self.assertFalse(batch.rows.get(row_number=2).changed_since_review)

    def test_choices_with_a_problem_are_refused(self):
        batch = self.stage(
            [row("ada@example.com", Organization="A"), row("ADA@example.com", Organization="B")], self.admin
        )
        self.choose(batch, {2: ("use_row", []), 3: ("use_row", [])})

        result = self.confirm(batch)

        self.assertEqual(
            (result.status, result.message),
            (
                "refused",
                f"Rows 2 and 3 would all change Ada Lovelace (member {self.ada.pk}). Choose one of them and skip the "
                "others.",
            ),
        )
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)

    @patch(
        "apps.authn.services.members.import_.review.apply.execute.contacts.add_phone",
        side_effect=ContactWriteError("the number was taken after the review"),
    )
    def test_a_row_that_fails_to_write_rolls_everything_back(self, _add_phone):
        batch = self.stage(
            [
                row("nina@example.com", First_Name="Nina", Last_Name="New"),
                row("ada@example.com", Phone_Number="2095550199"),
            ],
            self.admin,
        )

        result = self.confirm(batch)

        self.assertEqual(
            (result.status, result.message, result.rows), ("error", "Row 3: the number was taken after the review", [3])
        )
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())
        self.assertEqual(batch.status, "review")
        self.assertEqual(batch.last_error, "Nothing was imported. Row 3: the number was taken after the review")
        self.assertEqual(
            (batch.activity[-1]["action"], batch.activity[-1]["detail"]),
            ("error", "Row 3: the number was taken after the review"),
        )

    def test_a_database_error_sends_the_batch_back_to_review(self):
        """An address another request stored after the re-read trips the unique constraint: nothing is written."""
        add_email = contacts_module.add_email

        def racing_add_email(member, data):
            ContactEmail.objects.create(member=None, email_address=data["address"])  # the other request's insert
            add_email(member, data)

        batch = self.stage(
            [
                row("nina@example.com", First_Name="Nina", Last_Name="New"),
                row("ada@example.com", Organization="Engines", Secondary_Email="ada.new@example.com"),
            ],
            self.admin,
        )

        with (
            patch("apps.authn.services.members.import_.review.apply.execute.contacts.add_email", racing_add_email),
            self.assertLogs("apps.authn.services.members.import_.review.apply", level="ERROR"),
        ):
            result = self.confirm(batch)

        self.assertEqual(result.status, "error")
        self.assertTrue(result.message.startswith("A database error stopped the import (IntegrityError)"))
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())
        self.assertFalse(ContactEmail.objects.filter(email_address="ada.new@example.com").exists())
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)
        self.assertEqual(batch.status, "review")
        self.assertTrue(batch.last_error.startswith("Nothing was imported. A database error stopped the import"))
        self.assertEqual(batch.activity[-1]["action"], "error")
