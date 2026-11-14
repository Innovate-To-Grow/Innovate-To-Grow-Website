from apps.authn.models import ContactEmail
from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_member, make_staff


class DenylistTests(CliApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="deny@example.com")
        _, self.raw = issue_token(self.staff)

    def _records_url(self, app_label, model_name):
        return f"/admin-api/records/{app_label}/{model_name}/"

    def test_read_denied_models_are_400(self):
        denied = [
            ("admin", "logentry"),
            ("sessions", "session"),
            ("auth", "group"),
            ("core", "awscredentialconfig"),
            ("system_intelligence", "chatmessage"),
            ("cms", "cmspage"),
        ]
        for app_label, model_name in denied:
            with self.subTest(model=f"{app_label}.{model_name}"):
                response = self.client.get(self._records_url(app_label, model_name), **self.auth(self.raw))
                self.assertEqual(response.status_code, 400)

    def test_cli_extra_denied_models_are_400(self):
        denied = [
            ("cli_admin", "cliauthorizationcode"),
            ("cli_admin", "cliaccesstoken"),
            ("cli_admin", "cliauditlog"),
            ("authn", "impersonationtoken"),
            ("authn", "admininvitation"),
            ("mail", "loginlinktoken"),
        ]
        for app_label, model_name in denied:
            with self.subTest(model=f"{app_label}.{model_name}"):
                response = self.client.get(self._records_url(app_label, model_name), **self.auth(self.raw))
                self.assertEqual(response.status_code, 400)

    def test_authn_app_is_fully_denied_for_read_and_write(self):
        # The whole identity/auth app is off-limits to the CLI (read AND write).
        for app_label, model_name in (("authn", "member"), ("authn", "contactemail")):
            with self.subTest(model=f"{app_label}.{model_name}"):
                self.assertEqual(
                    self.client.get(self._records_url(app_label, model_name), **self.auth(self.raw)).status_code, 400
                )

    def test_contactemail_retarget_account_takeover_is_blocked(self):
        # Regression: creating a verified ContactEmail re-pointed at a victim would
        # enable a password-less reset takeover. It must be rejected outright.
        victim = make_member(email="victim@example.com")
        response = self.client.post(
            self._records_url("authn", "contactemail"),
            {
                "member_id": str(victim.pk),
                "email_address": "attacker@evil.com",
                "email_type": "secondary",
                "verified": True,
            },
            format="json",
            **self.auth(self.raw),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ContactEmail.objects.filter(email_address="attacker@evil.com").exists())

    def test_member_reactivation_and_field_escalation_blocked(self):
        target = make_member(email="target@example.com", is_active=False)
        url = f"/admin-api/records/authn/member/{target.pk}/"
        for field, value in (("is_active", True), ("is_staff", True), ("is_superuser", True), ("password", "x")):
            with self.subTest(field=field):
                self.assertEqual(
                    self.client.patch(url, {field: value}, format="json", **self.auth(self.raw)).status_code, 400
                )
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertFalse(target.is_staff)
        self.assertFalse(target.is_superuser)
