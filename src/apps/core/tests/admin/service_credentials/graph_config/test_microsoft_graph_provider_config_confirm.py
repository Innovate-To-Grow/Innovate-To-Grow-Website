import datetime
import json

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.admin.confirmation.diff import compute_change_diff, compute_delete_diff
from apps.core.admin.confirmation.post_data import extract_sensitive_post_data
from apps.core.admin.service_credentials.microsoft_graph import (
    MicrosoftGraphProviderConfigForm,
)
from apps.core.admin.service_credentials.microsoft_graph_panel import expiry_badge, store_name
from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.tests.admin.service_credentials.graph_config.test_microsoft_graph_admin import (
    CLIENT_ID,
    SESSION_KEY,
    config_values,
    form_data,
)
from apps.core.tests.graph_helpers import create_graph_config, private_key_lines
from apps.event.tests.helpers import make_superuser


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class MicrosoftGraphProviderConfigConfirmTest(TestCase):
    """Type-to-confirm sees only public values: nothing is masked, and nothing is stashed in the secrets cache."""

    def setUp(self):
        cache.clear()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = create_graph_config(**config_values(is_active=True))
        self.change_url = reverse("admin:core_microsoftgraphproviderconfig_change", args=[self.config.pk])
        self.confirm_url = reverse("admin:core_microsoftgraphproviderconfig_confirm_change")
        self.confirmation_word = MicrosoftGraphProviderConfig._meta.verbose_name

    def tearDown(self):
        cache.clear()

    def test_a_change_post_carries_no_sensitive_value(self):
        self.assertEqual(extract_sensitive_post_data(form_data(is_active="on", _save="Save")), {})

    def test_diffs_show_every_field_in_the_clear_without_key_material(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(name="Renamed"), instance=self.config)
        self.assertTrue(form.is_valid(), form.errors)

        change = json.dumps(compute_change_diff(MicrosoftGraphProviderConfig, self.config.pk, form))
        delete = json.dumps(compute_delete_diff(self.config))

        self.assertIn("Renamed", change)
        self.assertIn(CLIENT_ID, delete)
        for line in private_key_lines():
            self.assertNotIn(line, change + delete)

    def test_confirmed_change_saves_the_config(self):
        response = self.client.post(self.change_url, form_data(is_active="on", name="Renamed", _save="Save"))
        self.assertEqual(response["Location"], self.confirm_url)
        pending = self.client.session[SESSION_KEY]
        self.assertNotIn("PRIVATE", json.dumps(pending))

        confirmed = self.client.post(
            self.confirm_url, {"confirmation_word": self.confirmation_word, "token": pending["token"]}
        )

        self.assertEqual(confirmed.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.name, "Renamed")
        self.assertIsNotNone(self.config.current_certificate)


class CertificatePanelHelperTests(SimpleTestCase):
    def certificate(self, *, days_left=None, starts_in_days=-1):
        now = timezone.now()
        return MicrosoftGraphCertificate(
            not_before=now + datetime.timedelta(days=starts_in_days),
            not_after=now + datetime.timedelta(days=days_left, hours=1),
        )

    @override_settings(GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS=60, GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS=14)
    def test_the_expiry_badge_follows_the_configured_thresholds(self):
        for days_left, expected in (
            (365, ("Expires in 365 days", "success")),
            (61, ("Expires in 61 days", "success")),
            (60, ("Expires in 60 days", "warning")),
            (15, ("Expires in 15 days", "warning")),
            (14, ("Expires in 14 days", "danger")),
            (1, ("Expires in 1 day", "danger")),
            (0, ("Expires within a day", "danger")),
        ):
            with self.subTest(days_left=days_left):
                self.assertEqual(expiry_badge(self.certificate(days_left=days_left)), expected)
        self.assertEqual(expiry_badge(self.certificate(days_left=-2)), ("Expired", "danger"))
        self.assertEqual(expiry_badge(self.certificate(days_left=30, starts_in_days=1)), ("Not valid yet", "danger"))

    @override_settings(GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS=90, GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS=30)
    def test_other_thresholds_come_from_settings(self):
        self.assertEqual(expiry_badge(self.certificate(days_left=80))[1], "warning")
        self.assertEqual(expiry_badge(self.certificate(days_left=30))[1], "danger")

    def test_the_store_is_named_from_the_pinned_reference(self):
        arn = "arn:aws:secretsmanager:us-west-2:111122223333:secret:itg/backend/microsoft-graph/certificate-key-AbCdEf"
        self.assertEqual(store_name(arn), "AWS Secrets Manager")
        self.assertEqual(store_name("local-file:itg/backend/x"), "the local file store (development only)")
        self.assertEqual(store_name("memory:itg/backend/x"), "the in-memory store (tests only)")
        self.assertEqual(store_name("unknown"), "the credential store")
