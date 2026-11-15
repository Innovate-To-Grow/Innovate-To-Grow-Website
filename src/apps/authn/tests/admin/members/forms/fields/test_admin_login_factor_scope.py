from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.authn.tests.admin.members.security.privileged.test_member_admin_security import _staff


class AdminLoginFactorScopeTests(TestCase):
    """Only the primary contact email may receive an admin login code."""

    def setUp(self):
        cache.clear()
        self.staff = _staff(admin_apps=["authn"], first_name="Staff", last_name="Member")
        ContactEmail.objects.create(
            member=self.staff, email_address="primary@example.com", email_type="primary", verified=True
        )

    def tearDown(self):
        cache.clear()

    def test_primary_email_is_accepted(self):
        from apps.authn.forms.admin_login import AdminEmailForm

        form = AdminEmailForm(data={"email": "primary@example.com"})

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["member"], self.staff)

    def test_verified_secondary_email_is_rejected(self):
        from apps.authn.forms.admin_login import AdminEmailForm

        ContactEmail.objects.create(
            member=self.staff, email_address="secondary@example.com", email_type="secondary", verified=True
        )

        form = AdminEmailForm(data={"email": "secondary@example.com"})

        self.assertFalse(form.is_valid())
