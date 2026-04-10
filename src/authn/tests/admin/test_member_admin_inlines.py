"""
Tests that Contact Email / Contact Phone inlines are visible to
staff users on the Member change page regardless of explicit model
permissions.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from authn.models import ContactEmail

Member = get_user_model()


@override_settings(ROOT_URLCONF="core.urls")
class MemberAdminInlineVisibilityTest(TestCase):
    """Inline sections must render for every staff user, not just superusers."""

    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.superuser = Member.objects.create_superuser(
            password="super123",
            is_staff=True,
            is_active=True,
        )
        ContactEmail.objects.create(
            member=self.superuser,
            email_address="super@example.com",
            email_type="primary",
            verified=True,
        )

        self.staff_user = Member.objects.create_user(
            password="staff123",
            is_staff=True,
            is_active=True,
        )
        ContactEmail.objects.create(
            member=self.staff_user,
            email_address="staff@example.com",
            email_type="primary",
            verified=True,
        )

        self.target_member = Member.objects.create_user(
            password="target123",
            first_name="Target",
            last_name="User",
            is_active=True,
        )
        ContactEmail.objects.create(
            member=self.target_member,
            email_address="target@example.com",
            email_type="primary",
            verified=True,
        )

    # noinspection PyPep8Naming,PyMethodMayBeStatic
    def tearDown(self):
        cache.clear()

    def _change_url(self):
        return f"/admin/authn/member/{self.target_member.pk}/change/"

    def _assert_inlines_visible(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "contact_emails-group")
        self.assertContains(response, "contact_phones-group")
        self.assertContains(response, "Contact Emails")
        self.assertContains(response, "Contact Phones")

    def test_superuser_sees_inlines(self):
        self.client.force_login(self.superuser)
        resp = self.client.get(self._change_url())
        self._assert_inlines_visible(resp)

    def test_staff_user_without_explicit_perms_sees_inlines(self):
        """Before the fix, this test would fail because the staff user
        lacked authn.view_contactemail / authn.add_contactemail etc."""
        self.client.force_login(self.staff_user)
        resp = self.client.get(self._change_url())
        self._assert_inlines_visible(resp)
