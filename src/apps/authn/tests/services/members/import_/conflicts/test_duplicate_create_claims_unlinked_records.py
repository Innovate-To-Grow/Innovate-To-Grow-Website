from apps.authn.models import ContactEmail, Member
from apps.authn.tests.services.members.import_.conflicts.test_duplicate_create import _DuplicateCreateCase
from apps.authn.tests.services.members.import_.helpers import row


class DuplicateCreateTests(_DuplicateCreateCase):
    def test_claims_of_unlinked_records_that_differ_only_in_letter_case(self):
        # Legacy duplicates: the unique constraint is case-sensitive, so two unlinked records can hold one address.
        # Every row naming it is ambiguous (C3) and may claim either record; claiming both made two members.
        upper = ContactEmail.objects.create(member=None, email_address="Lab@example.com", email_type="primary")
        lower = ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        batch = self.stage(
            [
                row("lab@example.com", First_Name="Lab", Last_Name="One", Primary_Verified="TRUE"),
                row("lab@example.com", First_Name="Lab", Last_Name="Two", Primary_Verified="TRUE"),
            ],
            self.admin,
        )
        self.assertEqual([r.conflict for r in batch.rows.order_by("row_number")], ["ambiguous_address"] * 2)
        self.choose(batch, {2: (f"create_claim:{upper.pk}", []), 3: (f"create_claim:{lower.pk}", [])})

        result = self.confirm(batch)

        sentence = (
            "Rows 2 and 3 would all create a new member with lab@example.com. Choose one of them and skip the others."
        )
        self.assertEqual((result.status, result.message), ("refused", sentence))
        self.assertEqual(self.problems(batch), [sentence])
        self.assertFalse(Member.objects.filter(first_name="Lab").exists())
        self.assertEqual(
            ContactEmail.objects.filter(member__isnull=True, email_address__iexact="lab@example.com").count(), 2
        )

    def test_two_claims_of_one_unlinked_record_get_one_sentence(self):
        upper = ContactEmail.objects.create(member=None, email_address="Lab@example.com", email_type="primary")
        ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        batch = self.stage(
            [
                row("lab@example.com", First_Name="Lab", Last_Name="One"),
                row("lab@example.com", First_Name="Lab", Last_Name="Two"),
            ],
            self.admin,
        )
        self.choose(batch, {2: (f"create_claim:{upper.pk}", []), 3: (f"create_claim:{upper.pk}", [])})

        result = self.confirm(batch)

        sentence = (
            "Rows 2 and 3 would all change the contact email lab@example.com. Choose one of them and skip the others."
        )
        self.assertEqual((result.status, result.message), ("refused", sentence))
        self.assertEqual(self.problems(batch), [sentence])
