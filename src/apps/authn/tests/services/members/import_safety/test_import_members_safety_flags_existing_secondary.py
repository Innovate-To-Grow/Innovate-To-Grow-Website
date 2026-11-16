from apps.authn.models import ContactEmail
from apps.authn.tests.services.members.import_safety.test_import_members_safety import _ImportCase


class SecondaryEmailIsNeverDeletedTests(_ImportCase):
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
