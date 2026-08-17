"""Security regression tests for MemberAdmin authorization.

Covers two confirmed privilege-escalation findings:

* The custom ``impersonate`` admin URL was wrapped only in ``admin_site.admin_view``
  (is_staff only) — any staff member could mint a login token for a superuser.
* ``is_staff`` and ``admin_apps`` were freely editable on the Member change form,
  so a non-superuser admin could grant themselves every app / staff status.
"""

from django.contrib import admin
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, ImpersonationToken, Member


def _staff(admin_apps=None, **kwargs):
    member = Member.objects.create_user(password="StrongPass123!", is_staff=True, is_active=True, **kwargs)
    if admin_apps is not None:
        member.admin_apps = admin_apps
        member.save(update_fields=["admin_apps"])
    return member


class ImpersonateAuthorizationTests(TestCase):
    """The impersonate URL must enforce authn-app access and refuse to mint a
    token for a privileged (staff/superuser) account."""

    def setUp(self):
        cache.clear()
        self.superuser = Member.objects.create_superuser(
            password="StrongPass123!", first_name="Super", last_name="User", is_active=True
        )
        self.regular_target = Member.objects.create_user(
            password="StrongPass123!", first_name="Reg", last_name="Ular", is_active=True
        )

    def tearDown(self):
        cache.clear()

    def _url(self, target):
        return reverse("admin:authn_member_impersonate", args=[target.pk])

    def test_non_authn_staff_cannot_impersonate_superuser(self):
        attacker = _staff(admin_apps=["event"], first_name="Low", last_name="Priv")
        self.client.force_login(attacker)
        # Django converts the view's PermissionDenied into a 403 response.
        self.assertEqual(self.client.post(self._url(self.superuser)).status_code, 403)
        self.assertFalse(ImpersonationToken.objects.filter(member=self.superuser).exists())

    def test_authn_admin_cannot_impersonate_superuser(self):
        authn_admin = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        self.client.force_login(authn_admin)
        self.assertEqual(self.client.post(self._url(self.superuser)).status_code, 403)
        self.assertFalse(ImpersonationToken.objects.filter(member=self.superuser).exists())

    def test_authn_admin_cannot_impersonate_other_staff(self):
        authn_admin = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        other_staff = _staff(admin_apps=["mail"], first_name="Other", last_name="Staff")
        self.client.force_login(authn_admin)
        self.assertEqual(self.client.post(self._url(other_staff)).status_code, 403)
        self.assertFalse(ImpersonationToken.objects.filter(member=other_staff).exists())

    def test_authn_admin_can_impersonate_regular_member(self):
        authn_admin = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        self.client.force_login(authn_admin)
        response = self.client.post(self._url(self.regular_target))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/impersonate-login#token=", response["Location"])
        self.assertTrue(ImpersonationToken.objects.filter(member=self.regular_target).exists())

    def test_superuser_can_impersonate_regular_member(self):
        self.client.force_login(self.superuser)
        response = self.client.post(self._url(self.regular_target))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ImpersonationToken.objects.filter(member=self.regular_target).exists())

    def test_superuser_cannot_impersonate_another_superuser(self):
        # Even I2G Master may not impersonate another privileged account.
        other_super = Member.objects.create_superuser(
            password="StrongPass123!", first_name="Other", last_name="Master", is_active=True
        )
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.post(self._url(other_super)).status_code, 403)
        self.assertFalse(ImpersonationToken.objects.filter(member=other_super).exists())


class MemberToolingAuthorizationTests(TestCase):
    """The member import/export/template custom URLs expose or create PII member
    records, so they must require authn-app access — not merely is_staff."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_non_authn_staff_cannot_export_members(self):
        attacker = _staff(admin_apps=["event"], first_name="Low", last_name="Priv")
        self.client.force_login(attacker)
        resp = self.client.get(reverse("admin:authn_member_export_excel"))
        self.assertEqual(resp.status_code, 403)

    def test_non_authn_staff_cannot_open_import(self):
        attacker = _staff(admin_apps=["event"], first_name="Low", last_name="Priv")
        self.client.force_login(attacker)
        self.assertEqual(self.client.get(reverse("admin:authn_member_import_excel")).status_code, 403)

    def test_non_authn_staff_cannot_download_template(self):
        attacker = _staff(admin_apps=["event"], first_name="Low", last_name="Priv")
        self.client.force_login(attacker)
        self.assertEqual(self.client.get(reverse("admin:authn_member_import_template")).status_code, 403)

    def test_authn_admin_can_export_members(self):
        authn_admin = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        self.client.force_login(authn_admin)
        resp = self.client.get(reverse("admin:authn_member_export_excel"))
        self.assertEqual(resp.status_code, 200)


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


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class PrivilegedTargetProtectionTests(TestCase):
    """A non-superuser with the ``authn`` grant must not be able to take over a privileged account.

    ``BaseModelAdmin``'s permissions are per-app and object-independent, which left two routes open:
    the password-reset view inherited from ``UserAdmin``, and attaching a verified contact record
    (a working admin sign-in factor) to a staff or superuser member.
    """

    def setUp(self):
        cache.clear()
        self.attacker = _staff(admin_apps=["authn"], first_name="Authn", last_name="Admin")
        ContactEmail.objects.create(
            member=self.attacker, email_address="authnadmin@example.com", email_type="primary", verified=True
        )
        self.master = Member.objects.create_superuser(
            password="StrongPass123!", first_name="I2G", last_name="Master", is_active=True
        )
        ContactEmail.objects.create(
            member=self.master, email_address="master@example.com", email_type="primary", verified=True
        )
        self.regular = Member.objects.create_user(
            password="StrongPass123!", first_name="Reg", last_name="Ular", is_active=True
        )
        self.client.force_login(self.attacker)

    def tearDown(self):
        cache.clear()

    @staticmethod
    def _password_url(target):
        return f"/admin/authn/member/{target.pk}/password/"

    def test_cannot_reset_a_superuser_password(self):
        old_hash = self.master.password

        response = self.client.get(self._password_url(self.master))

        self.assertEqual(response.status_code, 403)
        self.master.refresh_from_db()
        self.assertEqual(self.master.password, old_hash)

    def test_cannot_post_a_new_superuser_password(self):
        old_hash = self.master.password

        response = self.client.post(
            self._password_url(self.master),
            {"password1": "Pwned!12345", "password2": "Pwned!12345"},
        )

        self.assertEqual(response.status_code, 403)
        self.master.refresh_from_db()
        self.assertEqual(self.master.password, old_hash)

    def test_can_reset_a_regular_member_password(self):
        old_hash = self.regular.password

        response = self.client.post(
            self._password_url(self.regular),
            {"password1": "BrandNew!12345", "password2": "BrandNew!12345"},
        )

        self.assertEqual(response.status_code, 302)
        self.regular.refresh_from_db()
        self.assertNotEqual(self.regular.password, old_hash)

    def test_can_reset_own_password(self):
        old_hash = self.attacker.password

        response = self.client.post(
            self._password_url(self.attacker),
            {"password1": "MyOwnNew!12345", "password2": "MyOwnNew!12345"},
        )

        self.assertEqual(response.status_code, 302)
        self.attacker.refresh_from_db()
        self.assertNotEqual(self.attacker.password, old_hash)

    def test_superuser_can_reset_another_superuser_password(self):
        self.client.force_login(self.master)
        other = Member.objects.create_superuser(
            password="StrongPass123!", first_name="Other", last_name="Master", is_active=True
        )
        old_hash = other.password

        response = self.client.post(
            self._password_url(other), {"password1": "Rotated!12345", "password2": "Rotated!12345"}
        )

        self.assertEqual(response.status_code, 302)
        other.refresh_from_db()
        self.assertNotEqual(other.password, old_hash)

    def test_cannot_attach_a_verified_contact_email_to_a_superuser(self):
        response = self.client.post(
            "/admin/authn/contactemail/add/",
            {
                "member": str(self.master.pk),
                "email_address": "attacker@evil.test",
                "email_type": "secondary",
                "verified": "on",
                "subscribe": "on",
                "_save": "1",
            },
        )

        self.assertEqual(response.status_code, 200)  # re-rendered with a validation error
        self.assertFalse(ContactEmail.objects.filter(email_address="attacker@evil.test").exists())

    def test_can_attach_a_contact_email_to_a_regular_member(self):
        response = self.client.post(
            "/admin/authn/contactemail/add/",
            {
                "member": str(self.regular.pk),
                "email_address": "ok@example.test",
                "email_type": "secondary",
                "subscribe": "on",
                "_save": "1",
            },
        )

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        self.assertTrue(ContactEmail.objects.filter(email_address="ok@example.test").exists())

    def test_a_superuser_contact_email_renders_read_only(self):
        """View access is still granted, so Django renders the view-only form: no Save, no inputs."""
        row = ContactEmail.objects.create(
            member=self.master, email_address="master.alt@example.com", email_type="secondary", verified=False
        )

        response = self.client.get(f"/admin/authn/contactemail/{row.pk}/change/")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('name="_save"', content)
        self.assertNotIn('name="email_address"', content)
        self.assertNotIn('name="verified"', content)

    def test_cannot_post_a_change_to_a_superuser_contact_email(self):
        row = ContactEmail.objects.create(
            member=self.master, email_address="master.alt3@example.com", email_type="secondary", verified=False
        )

        response = self.client.post(
            f"/admin/authn/contactemail/{row.pk}/change/",
            {
                "member": str(self.master.pk),
                "email_address": "master.alt3@example.com",
                "email_type": "secondary",
                "verified": "on",
                "_save": "1",
            },
        )

        self.assertEqual(response.status_code, 403)
        row.refresh_from_db()
        self.assertFalse(row.verified)

    def test_mark_verified_action_skips_privileged_owners(self):
        protected = ContactEmail.objects.create(
            member=self.master, email_address="master.alt2@example.com", email_type="secondary", verified=False
        )
        allowed = ContactEmail.objects.create(
            member=self.regular, email_address="reg.alt@example.com", email_type="secondary", verified=False
        )

        self.client.post(
            "/admin/authn/contactemail/",
            {
                "action": "mark_verified",
                "_selected_action": [str(protected.pk), str(allowed.pk)],
                "index": "0",
            },
        )

        protected.refresh_from_db()
        allowed.refresh_from_db()
        self.assertFalse(protected.verified)
        self.assertTrue(allowed.verified)

    def test_cannot_deactivate_a_superuser_via_the_bulk_action(self):
        self.client.post(
            "/admin/authn/member/",
            {
                "action": "deactivate_members",
                "_selected_action": [str(self.master.pk), str(self.regular.pk)],
                "index": "0",
            },
        )

        self.master.refresh_from_db()
        self.regular.refresh_from_db()
        self.assertTrue(self.master.is_active)
        self.assertFalse(self.regular.is_active)

    def test_is_active_is_readonly_for_a_privileged_target(self):
        model_admin = admin.site._registry[Member]
        request = RequestFactory().get("/")
        request.user = self.attacker

        self.assertIn("is_active", model_admin.get_readonly_fields(request, self.master))
        self.assertNotIn("is_active", model_admin.get_readonly_fields(request, self.regular))


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
