import uuid

from django.contrib.admin.models import LogEntry
from django.test import Client, override_settings

from .fixtures import SwitchFixture, switch_url, types


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SwitchPermissionTests(SwitchFixture):
    def test_a_member_who_is_not_an_admin_is_sent_to_the_admin_login(self):
        self.client.force_login(self.outsider)

        responses = [
            self.client.get(switch_url(self.jane)),
            self.apply(self.jane, self.secondary, fingerprint="x"),
            # Same answer for a member that does not exist, so the page does not tell which ids do.
            self.client.get(f"/admin/authn/member/{uuid.uuid4()}/switch-primary/"),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 302)
            self.assertIn("/admin/login/", response["Location"])
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")

    def test_the_post_needs_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.master)
        fingerprint = client.get(switch_url(self.jane, self.secondary)).context["fingerprint"]

        response = client.post(switch_url(self.jane), {"to": str(self.secondary.pk), "fingerprint": fingerprint})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")

    def test_a_helper_may_switch_a_regular_member(self):
        self.client.force_login(self.helper)

        response = self.apply(self.jane, self.secondary)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(types(self.jane)["jane.work@example.com"], "primary")
        self.assertEqual(LogEntry.objects.filter(user=self.helper).count(), 3)

    def test_an_admin_may_switch_another_admins_account(self):
        self.client.force_login(self.helper)

        self.assertEqual(self.client.get(switch_url(self.staffer)).status_code, 200)
        response = self.apply(self.staffer, self.staffer_backup)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(types(self.staffer)["sam.home@example.com"], "primary")
        self.assertEqual(LogEntry.objects.filter(user=self.helper).count(), 3)

    def test_a_helper_may_switch_their_own_account_and_is_told_where_codes_go(self):
        self.client.force_login(self.helper)

        page = self.client.get(switch_url(self.helper, self.helper_backup))
        self.assertContains(page, "This is your own account: your next admin sign-in code goes to hal.home@example.com")

        self.assertEqual(self.apply(self.helper, self.helper_backup).status_code, 302)
        self.assertEqual(types(self.helper)["hal.home@example.com"], "primary")

    def test_signed_out_visitors_are_sent_to_the_admin_login(self):
        self.client.logout()

        response = self.client.get(switch_url(self.jane))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
