"""Which contact inlines the member admin shows, and to whom."""

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail

from .inline_helpers import Member


@override_settings(ROOT_URLCONF="config.routing.urls")
class MemberAdminInlineVisibilityTest(TestCase):
    """Inline sections render for every Admin (one made with ``is_staff`` only as well as a superuser), and the page
    is closed to a member who is not an Admin."""

    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.superuser = Member.objects.create_superuser(
            password="super123",
            first_name="Super",
            last_name="User",
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

    def test_admin_sees_inlines(self):
        """An Admin made with ``is_staff`` only sees the inlines: no per-model Django permissions are needed."""
        self.client.force_login(self.staff_user)
        resp = self.client.get(self._change_url())
        self._assert_inlines_visible(resp)

    def test_a_member_who_is_not_an_admin_is_sent_to_the_admin_login(self):
        self.client.force_login(self.target_member)
        resp = self.client.get(self._change_url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])

    # --- Full page composition ---------------------------------------------------------------
    #
    # Regression cover for the report that one member's change page showed only "Personal Info"
    # and could not be edited while another's showed both contact inlines. The page must compose
    # identically for every member and every authorised admin, and must never grow with the size
    # of the stored profile_image — the whole base64 value used to be inlined into an <img src> as
    # the last field of "Personal Info", so everything after it (the remaining fieldsets, both
    # inline groups and the only Save button) was lost whenever the response was truncated.

    def _assert_change_page_composition(self, response):
        self._assert_inlines_visible(response)
        for prefix in ("contact_emails", "contact_phones"):
            self.assertContains(response, f'name="{prefix}-TOTAL_FORMS"')
            self.assertContains(response, f'name="{prefix}-INITIAL_FORMS"')
        for field in ("first_name", "middle_name", "last_name", "organization", "title"):
            self.assertContains(response, f'name="{field}"')
        self.assertContains(response, 'name="profile_image"')
        self.assertContains(response, 'type="file"')
        # The submit row lives after the inlines in unfold's change_form.html.
        self.assertContains(response, 'name="_save"')

    def test_change_page_composition_for_superuser(self):
        self.client.force_login(self.superuser)
        self._assert_change_page_composition(self.client.get(self._change_url()))

    def test_change_page_composition_for_admin(self):
        self.client.force_login(self.staff_user)
        self._assert_change_page_composition(self.client.get(self._change_url()))

    def test_change_page_composition_for_member_without_contacts(self):
        """Both inlines use extra=0, so a member with no rows must still get both groups."""
        bare = Member.objects.create_user(password="bare123", first_name="No", last_name="Contacts", is_active=True)
        self.client.force_login(self.superuser)

        resp = self.client.get(f"/admin/authn/member/{bare.pk}/change/")

        self._assert_change_page_composition(resp)
        self.assertContains(resp, 'id="id_contact_emails-INITIAL_FORMS"')

    def test_change_page_composition_for_member_with_a_large_profile_image(self):
        self.target_member.profile_image = "data:image/png;base64," + ("A" * 2_000_000)
        self.target_member.save(update_fields=["profile_image"])
        self.client.force_login(self.superuser)

        resp = self.client.get(self._change_url())

        self._assert_change_page_composition(resp)

    def test_change_page_never_inlines_the_profile_image(self):
        self.target_member.profile_image = "data:image/png;base64," + ("A" * 2_000_000)
        self.target_member.save(update_fields=["profile_image"])
        self.client.force_login(self.superuser)

        resp = self.client.get(self._change_url())

        self.assertNotContains(resp, "data:image/png;base64")
        self.assertContains(resp, f"/admin/authn/member/{self.target_member.pk}/profile-image/")
        # The page must not scale with the stored image.
        self.assertLess(len(resp.content), 1_000_000)

    def test_change_page_size_is_independent_of_the_stored_image(self):
        self.client.force_login(self.superuser)
        without = len(self.client.get(self._change_url()).content)

        self.target_member.profile_image = "data:image/png;base64," + ("A" * 2_000_000)
        self.target_member.save(update_fields=["profile_image"])
        with_image = len(self.client.get(self._change_url()).content)

        # Only the preview <img> and the remove checkbox are added.
        self.assertLess(with_image - without, 2_000)

    def test_add_page_omits_the_profile_image_field(self):
        self.client.force_login(self.superuser)

        resp = self.client.get("/admin/authn/member/add/")

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'name="profile_image"')
        self.assertContains(resp, 'name="password1"')
