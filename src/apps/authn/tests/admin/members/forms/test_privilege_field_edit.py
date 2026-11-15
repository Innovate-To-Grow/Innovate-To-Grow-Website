from django.contrib import admin
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from apps.authn.models import ContactEmail, Member
from apps.authn.tests.admin.members.security.test_member_admin_security import _staff


class PrivilegeFieldEditTests(TestCase):
    """``is_staff`` and ``admin_apps`` may be edited only by superusers; for
    everyone else they are read-only and excluded from the bound form, so a
    submitted value cannot escalate privileges."""

    def setUp(self):
        self.model_admin = admin.site._registry[Member]
        # A concrete instance so UserAdmin returns the *change* form (obj=None
        # would yield the add form, which omits these fields regardless).
        self.target = Member.objects.create_user(
            password="StrongPass123!", first_name="Edit", last_name="Target", is_staff=True, is_active=True
        )

    def _request(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return request

    def test_privilege_fields_readonly_for_non_superuser(self):
        request = self._request(Member(is_superuser=False, is_staff=True, is_active=True))
        readonly = self.model_admin.get_readonly_fields(request, self.target)
        self.assertIn("is_staff", readonly)
        self.assertIn("admin_apps", readonly)

    def test_privilege_fields_editable_for_superuser(self):
        request = self._request(Member(is_superuser=True, is_staff=True, is_active=True))
        readonly = self.model_admin.get_readonly_fields(request, self.target)
        self.assertNotIn("is_staff", readonly)
        self.assertNotIn("admin_apps", readonly)

    def test_non_superuser_form_cannot_bind_privilege_fields(self):
        # If the fields are absent from the bound form, a POST can never set them.
        request = self._request(Member(is_superuser=False, is_staff=True, is_active=True))
        form_class = self.model_admin.get_form(request, obj=self.target, change=True)
        self.assertNotIn("is_staff", form_class.base_fields)
        self.assertNotIn("admin_apps", form_class.base_fields)

    def test_superuser_form_can_bind_privilege_fields(self):
        request = self._request(Member(is_superuser=True, is_staff=True, is_active=True))
        form_class = self.model_admin.get_form(request, obj=self.target, change=True)
        self.assertIn("is_staff", form_class.base_fields)
        self.assertIn("admin_apps", form_class.base_fields)

    def test_superuser_status_is_bound_by_no_admin_form(self):
        # An app grant gives full control of that app's configuration, never superuser status: no Member form (add or
        # change, superuser or not) offers ``is_superuser``.
        for is_superuser in (False, True):
            request = self._request(Member(is_superuser=is_superuser, is_staff=True, is_active=True))
            for obj in (self.target, None):
                with self.subTest(superuser=is_superuser, change=obj is not None):
                    form_class = self.model_admin.get_form(request, obj=obj, change=obj is not None)
                    self.assertNotIn("is_superuser", form_class.base_fields)


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class PrivilegeFieldPostTests(TestCase):
    """End-to-end: a non-superoperator cannot widen their own privileges by
    POSTing is_staff / admin_apps to their own change page."""

    def setUp(self):
        cache.clear()
        self.attacker = _staff(admin_apps=["authn"], first_name="Self", last_name="Escalate")
        ContactEmail.objects.create(
            member=self.attacker, email_address="attacker@example.com", email_type="primary", verified=True
        )
        self.client.force_login(self.attacker)

    def tearDown(self):
        cache.clear()

    def test_post_cannot_grant_extra_apps_or_staff(self):
        url = f"/admin/authn/member/{self.attacker.pk}/change/"
        # Scrape the rendered form, then inject escalation values the read-only
        # form never offered.
        get_resp = self.client.get(url)
        self.assertEqual(get_resp.status_code, 200)
        # The privilege fields must not render as editable inputs.
        content = get_resp.content.decode()
        self.assertNotIn('name="admin_apps"', content)

        data = {
            "first_name": "Self",
            "last_name": "Escalate",
            "is_active": "on",
            "is_staff": "on",
            "admin_apps": ["cms", "mail", "event", "authn"],
            "contact_emails-TOTAL_FORMS": "0",
            "contact_emails-INITIAL_FORMS": "0",
            "contact_emails-MIN_NUM_FORMS": "0",
            "contact_emails-MAX_NUM_FORMS": "1000",
            "contact_phones-TOTAL_FORMS": "0",
            "contact_phones-INITIAL_FORMS": "0",
            "contact_phones-MIN_NUM_FORMS": "0",
            "contact_phones-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        self.client.post(url, data)
        self.attacker.refresh_from_db()
        # The injected escalation values were ignored: app grant unchanged.
        self.assertEqual(self.attacker.admin_apps, ["authn"])

    def test_post_cannot_grant_superuser_status(self):
        url = f"/admin/authn/member/{self.attacker.pk}/change/"
        data = {
            "first_name": "Self",
            "last_name": "Escalate",
            "is_active": "on",
            "is_superuser": "on",
            "contact_emails-TOTAL_FORMS": "0",
            "contact_emails-INITIAL_FORMS": "0",
            "contact_emails-MIN_NUM_FORMS": "0",
            "contact_emails-MAX_NUM_FORMS": "1000",
            "contact_phones-TOTAL_FORMS": "0",
            "contact_phones-INITIAL_FORMS": "0",
            "contact_phones-MIN_NUM_FORMS": "0",
            "contact_phones-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }

        self.client.post(url, data)

        self.attacker.refresh_from_db()
        self.assertFalse(self.attacker.is_superuser)
        self.assertEqual(self.attacker.admin_apps, ["authn"])
