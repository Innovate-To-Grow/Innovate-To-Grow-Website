from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.tests.services.members.import_.contact_warnings.test_secondary_email_warning import (
    _SecondaryEmailWarningCase,
)
from apps.authn.tests.services.members.import_.helpers import row
from apps.authn.tests.services.members.import_.reading.test_validation import V8_LAB


class SecondaryEmailWarningTests(_SecondaryEmailWarningCase):
    def test_a_shared_unlinked_secondary_goes_only_to_the_first_row_of_a_repeat_group(self):
        # The same person twice (C1): using row 3 instead of row 2 updates the member without the address.
        lab = ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        rows = [
            row("ada@example.com", Secondary_Email="lab@example.com"),
            row("ada@example.com", Title="Countess", Secondary_Email="lab@example.com"),
        ]

        first, second = self.analyse(rows)

        self.assertEqual((first.conflict, second.conflict), ("duplicate_in_sheet", "duplicate_in_sheet"))
        self.assertEqual(second.warnings, [{"code": "V8", "text": V8_LAB}])
        outcomes = self.apply(rows, {2: ("skip", []), 3: ("use_row", [])})
        self.assertEqual([outcome.outcome for outcome in outcomes], ["skipped", "updated"])
        self.ada.refresh_from_db()
        lab.refresh_from_db()
        self.assertEqual((self.ada.title, lab.member), ("Countess", None))

    def test_only_the_first_row_adds_a_shared_new_secondary(self):
        rows = [
            row("one@example.com", Secondary_Email="shared.new@example.com", Phone_Number="209-555-0123"),
            row("two@example.com", Secondary_Email="shared.new@example.com", Phone_Number="209-555-0123"),
        ]

        first, second = self.apply(rows)

        self.assertEqual((first.outcome, second.outcome), ("created", "created"))
        self.assertEqual(ContactEmail.objects.get(email_address="shared.new@example.com").member, first.member)
        self.assertEqual(ContactPhone.objects.get(phone_number="2095550123").member, first.member)
        self.assertEqual(
            list(second.member.contact_emails.values_list("email_address", flat=True)), ["two@example.com"]
        )
        self.assertFalse(second.member.contact_phones.exists())
