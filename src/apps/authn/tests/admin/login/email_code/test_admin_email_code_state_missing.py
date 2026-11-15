from __future__ import annotations

from django.test import TestCase, override_settings


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminEmailCodeStateMissingTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    def test_code_step_without_email_state_falls_back_to_email(self):
        """email_code.py:112-113 — code step with empty email/member_id clears session, shows email form."""
        session = self.client.session
        session["admin_login_step"] = "code"
        session["admin_login_email"] = ""
        session.save()

        response = self.client.post(
            "/admin/login/",
            {"code": "123456"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], "email")
        self.assertNotIn("admin_login_step", self.client.session)
