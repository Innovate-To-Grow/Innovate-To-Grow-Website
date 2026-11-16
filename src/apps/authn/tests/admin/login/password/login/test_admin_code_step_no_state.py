from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail
from apps.authn.tests.admin.login.password.login.test_admin_login_edge_cases import LOGIN_URL, Member


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminCodeStepNoStateTest(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_user(
            password="testpass123", first_name="Staff", last_name="Admin", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.staff, email_address="admin@example.com", email_type="primary", verified=True
        )

    def test_get_code_step_renders_when_session_in_code(self):
        # Drive the session into the "code" step, then GET (view.py line 41 branch).
        session = self.client.session
        session["admin_login_step"] = "code"
        session["admin_login_email"] = "admin@example.com"
        session["admin_login_member_id"] = str(self.staff.pk)
        session.save()
        resp = self.client.get(LOGIN_URL)
        self.assertEqual(resp.status_code, 200)
