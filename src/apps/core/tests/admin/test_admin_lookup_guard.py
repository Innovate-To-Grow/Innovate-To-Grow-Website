"""``BaseModelAdmin.lookup_allowed``: a changelist filter on a secret-looking field is a 400, never a count oracle."""

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.admin.common.base import BaseModelAdmin
from apps.core.admin.mixins.confirm_on_save_utils import SENSITIVE_FIELD_RE
from apps.core.models import AWSCredentialConfig, SMTPProviderConfig
from apps.core.tests.graph_helpers import create_graph_config
from apps.event.tests.helpers import make_admin, make_superuser

PROBES = {
    "core_microsoftgraphproviderconfig": ("private_key__regex=.", "client_secret__contains=a", "PASSWORD=x"),
    "core_smtpproviderconfig": ("password__startswith=e", "password=existing-secret"),
    "core_awscredentialconfig": ("secret_access_key__startswith=t", "secret_access_key__regex=^t"),
}


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SensitiveLookupTests(TestCase):
    def setUp(self):
        cache.clear()
        create_graph_config(name="Graph", certificate=False)
        SMTPProviderConfig.objects.create(
            name="SMTP", host="smtp.example.com", username="mailer", password="existing-secret"
        )
        AWSCredentialConfig.objects.create(name="AWS", access_key_id="test-key", secret_access_key="test-secret")

    def test_secret_lookups_are_refused_for_superusers_and_core_staff(self):
        for user in (make_superuser(), make_admin(apps=["core"], email="core@example.com")):
            self.client.force_login(user)
            for prefix, probes in PROBES.items():
                url = reverse(f"admin:{prefix}_changelist")
                for probe in probes:
                    with self.subTest(user=user.is_superuser, url=url, probe=probe):
                        self.assertEqual(self.client.get(f"{url}?{probe}").status_code, 400)

    def test_ordinary_filters_still_work(self):
        self.client.force_login(make_superuser())
        for prefix in PROBES:
            with self.subTest(prefix):
                url = reverse(f"admin:{prefix}_changelist")
                self.assertEqual(self.client.get(f"{url}?is_active__exact=0").status_code, 200)
                self.assertEqual(self.client.get(f"{url}?q=example").status_code, 200)

    def test_only_the_first_segment_of_the_lookup_is_judged(self):
        model_admin = BaseModelAdmin(SMTPProviderConfig, AdminSite())
        request = RequestFactory().get("/")

        self.assertFalse(model_admin.lookup_allowed("password", "x", request))
        self.assertFalse(model_admin.lookup_allowed("password__isnull", "x", request))
        self.assertTrue(model_admin.lookup_allowed("is_active__exact", "1", request))


class RegisteredAdminFilterTests(TestCase):
    def test_no_project_admin_filters_on_a_name_the_guard_refuses(self):
        """Every declared filter keeps working: none of them starts with a secret-looking name."""
        for model, model_admin in admin.site._registry.items():
            if not isinstance(model_admin, BaseModelAdmin):
                continue
            for entry in (*model_admin.list_filter, model_admin.date_hierarchy):
                name = entry[0] if isinstance(entry, tuple | list) else entry
                name = getattr(name, "parameter_name", name)
                if isinstance(name, str):
                    with self.subTest(model=model._meta.label, filter=name):
                        self.assertIsNone(SENSITIVE_FIELD_RE.search(name.split("__", 1)[0]))
