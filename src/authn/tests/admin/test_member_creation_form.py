from django.test import TestCase

from authn.admin.members.forms import MemberCreationForm
from authn.models import Member


class MemberCreationFormPasswordTest(TestCase):
    def test_empty_passwords_valid_and_sets_unusable_password(self):
        form = MemberCreationForm(
            {
                "first_name": "No",
                "last_name": "Password",
                "password1": "",
                "password2": "",
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user: Member = form.save()
        self.assertIsNotNone(user.pk)
        self.assertFalse(user.has_usable_password())

    def test_mismatched_passwords_invalid(self):
        form = MemberCreationForm(
            {
                "first_name": "A",
                "last_name": "B",
                "password1": "onepassword123",
                "password2": "otherpassword123",
                "is_active": "on",
            }
        )
        self.assertFalse(form.is_valid())

    def test_matching_passwords_sets_usable(self):
        form = MemberCreationForm(
            {
                "first_name": "A",
                "last_name": "B",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.has_usable_password())
