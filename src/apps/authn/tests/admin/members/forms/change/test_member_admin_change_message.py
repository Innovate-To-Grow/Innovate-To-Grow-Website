from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail
from apps.authn.tests.admin.members.forms.change.test_member_admin_confirm_on_save import Member
from apps.authn.tests.helpers import PNG_1PX_DATA_URI, png_upload, scrape_admin_form


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class MemberAdminChangeMessageTest(TestCase):
    """The admin log must not claim the profile image changed when it did not.

    ``ModelAdmin.construct_change_message`` reads ``form.changed_data``, so the always-dirty
    ``profile_image`` made every member save record "Changed Profile Image." — the reported symptom.
    """

    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.superuser = Member.objects.create_superuser(
            password="super123", first_name="Super", last_name="User", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.superuser, email_address="super2@example.com", email_type="primary", verified=True
        )
        self.target = Member.objects.create_user(
            password="target123",
            first_name="Target",
            last_name="User",
            is_active=True,
            profile_image=PNG_1PX_DATA_URI,
        )
        ContactEmail.objects.create(
            member=self.target, email_address="target2@example.com", email_type="primary", verified=True
        )
        self.client.force_login(self.superuser)

    # noinspection PyPep8Naming,PyMethodMayBeStatic
    def tearDown(self):
        cache.clear()

    def _change_url(self):
        return f"/admin/authn/member/{self.target.pk}/change/"

    def _latest_message(self):
        from django.contrib.admin.models import CHANGE, LogEntry

        entry = LogEntry.objects.filter(object_id=str(self.target.pk), action_flag=CHANGE).latest("action_time")
        return entry.get_change_message()

    def test_change_message_lists_only_really_changed_fields(self):
        response = self.client.post(
            self._change_url(), scrape_admin_form(self.client, self._change_url(), {"title": "Dean"})
        )

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        message = self._latest_message()
        self.assertIn("Title", message)
        self.assertNotIn("Profile Image", message)

    def test_save_with_no_edits_logs_no_fields_changed(self):
        response = self.client.post(self._change_url(), scrape_admin_form(self.client, self._change_url()))

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        self.assertEqual(self._latest_message(), "No fields changed.")

    def test_uploading_an_image_does_log_the_change(self):
        data = scrape_admin_form(self.client, self._change_url())

        response = self.client.post(self._change_url(), data | {"profile_image": png_upload()})

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        self.assertIn("Profile Image", self._latest_message())
