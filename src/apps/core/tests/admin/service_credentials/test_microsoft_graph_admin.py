"""Django admin for MicrosoftGraphProviderConfig: no credential inputs, the certificate panel, read-only Entra
application fields, delete rules, access control and confirm-on-save."""

import datetime
import json

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.admin.common.base import BaseModelAdmin
from apps.core.admin.mixins.confirm_on_save_utils import (
    compute_change_diff,
    compute_delete_diff,
    extract_sensitive_post_data,
    is_sensitive_field,
)
from apps.core.admin.service_credentials.microsoft_graph import (
    APPLICATION_FIELDS,
    GRAPH_FORM_FIELDS,
    NO_CERTIFICATE,
    MicrosoftGraphProviderConfigAdmin,
    MicrosoftGraphProviderConfigForm,
)
from apps.core.admin.service_credentials.microsoft_graph_panel import expiry_badge, store_name
from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.tests.graph_helpers import create_graph_config, install_test_certificate, private_key_lines
from apps.event.tests.helpers import make_admin, make_superuser

TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_CLIENT_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
MAILBOX = "sender@example.com"
SESSION_KEY = "_admin_pending_change_core_microsoftgraphproviderconfig"


def config_values(**overrides):
    values = {"name": "Mail", "tenant_id": TENANT_ID, "client_id": CLIENT_ID, "mailbox": MAILBOX}
    return values | overrides


def form_data(**overrides):
    data = {
        "name": "Mail",
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "mailbox": MAILBOX,
        # The mailbox scope inline's management form, submitted with no rows.
        "mailbox_scopes-TOTAL_FORMS": "0",
        "mailbox_scopes-INITIAL_FORMS": "0",
        "mailbox_scopes-MIN_NUM_FORMS": "0",
        "mailbox_scopes-MAX_NUM_FORMS": "1000",
    }
    return data | overrides


class MicrosoftGraphProviderConfigFormTest(TestCase):
    def test_the_form_has_no_credential_input(self):
        form = MicrosoftGraphProviderConfigForm()

        self.assertEqual(tuple(form.fields), GRAPH_FORM_FIELDS)
        for name in form.fields:
            with self.subTest(name=name):
                self.assertFalse(is_sensitive_field(name, form))

    def test_model_validation_errors_appear_on_their_fields(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(tenant_id="common", client_id="x", mailbox="x"))

        self.assertFalse(form.is_valid())
        self.assertEqual(sorted(form.errors), ["client_id", "mailbox", "tenant_id"])

    def test_standby_can_replace_the_active_config_without_disabling_it_first(self):
        create_graph_config(**config_values(name="Active", is_active=True))
        standby = create_graph_config(**config_values(name="Standby"))
        form = MicrosoftGraphProviderConfigForm(data=form_data(name="Standby", is_active="on"), instance=standby)

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertEqual(MicrosoftGraphProviderConfig.load(), standby)

    def test_the_application_cannot_change_while_a_certificate_is_installed(self):
        config = create_graph_config(**config_values())
        form = MicrosoftGraphProviderConfigForm(data=form_data(client_id=OTHER_CLIENT_ID), instance=config)

        self.assertFalse(form.is_valid())
        self.assertIn("Remove the installed certificates", form.errors["client_id"][0])

        config.certificates.update(state=MicrosoftGraphCertificate.State.REMOVED)
        form = MicrosoftGraphProviderConfigForm(data=form_data(client_id=OTHER_CLIENT_ID), instance=config)
        self.assertTrue(form.is_valid(), form.errors)


class MicrosoftGraphProviderConfigAdminTest(TestCase):
    def setUp(self):
        self.user = make_superuser()
        self.model_admin = MicrosoftGraphProviderConfigAdmin(MicrosoftGraphProviderConfig, AdminSite())

    def request(self):
        request = RequestFactory().get("/")
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_is_registered_with_the_admin_site(self):
        self.assertIsInstance(admin.site._registry[MicrosoftGraphProviderConfig], MicrosoftGraphProviderConfigAdmin)

    def test_status_badge_for_active_and_inactive_configs(self):
        self.assertEqual(
            self.model_admin.status_badge(MicrosoftGraphProviderConfig(is_active=True)), ("Active", "success")
        )
        self.assertEqual(
            self.model_admin.status_badge(MicrosoftGraphProviderConfig(is_active=False)), ("Inactive", "danger")
        )

    def test_certificate_columns_show_the_current_certificate_or_say_none_is_installed(self):
        config = create_graph_config(**config_values(), certificate=False)
        for method in ("certificate_thumbprint", "certificate_valid_until"):
            with self.subTest(method):
                self.assertEqual(getattr(self.model_admin, method)(config), NO_CERTIFICATE)

        current = install_test_certificate(config)
        install_test_certificate(config, state=MicrosoftGraphCertificate.State.PREVIOUS)

        self.assertEqual(self.model_admin.certificate_thumbprint(config), current.sha1_thumbprint)
        self.assertEqual(self.model_admin.certificate_valid_until(config), current.not_after)

    def test_the_entra_application_is_read_only_while_a_certificate_is_installed(self):
        config = create_graph_config(**config_values(), certificate=False)
        self.assertFalse(set(APPLICATION_FIELDS) & set(self.model_admin.get_readonly_fields(self.request(), config)))

        for state in (MicrosoftGraphCertificate.State.PREVIOUS, MicrosoftGraphCertificate.State.CURRENT):
            install_test_certificate(config, state=state)
            with self.subTest(state):
                readonly = self.model_admin.get_readonly_fields(self.request(), config)
                self.assertTrue(set(APPLICATION_FIELDS) <= set(readonly))
        config.certificates.update(state=MicrosoftGraphCertificate.State.REMOVED)
        self.assertFalse(set(APPLICATION_FIELDS) & set(self.model_admin.get_readonly_fields(self.request(), config)))
        self.assertFalse(set(APPLICATION_FIELDS) & set(self.model_admin.get_readonly_fields(self.request(), None)))

    def test_delete_permission_is_denied_only_for_the_active_config(self):
        active = create_graph_config(**config_values(name="Active", is_active=True))
        inactive = create_graph_config(**config_values(name="Inactive"))

        self.assertFalse(self.model_admin.has_delete_permission(self.request(), active))
        self.assertTrue(self.model_admin.has_delete_permission(self.request(), inactive))
        self.assertTrue(self.model_admin.has_delete_permission(self.request(), None))

    def test_delete_selected_is_not_offered(self):
        # The stock admin offers it to this superuser, so its absence is down to the admin class.
        stock = BaseModelAdmin(MicrosoftGraphProviderConfig, AdminSite())
        self.assertIn("delete_selected", stock.get_actions(self.request()))

        self.assertNotIn("delete_selected", self.model_admin.get_actions(self.request()))

    def test_no_listed_filtered_or_searchable_name_looks_like_a_secret(self):
        for setting in (self.model_admin.list_display, self.model_admin.list_filter, self.model_admin.search_fields):
            for name in setting:
                with self.subTest(name=name):
                    self.assertFalse(is_sensitive_field(name))


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MicrosoftGraphProviderConfigAdminPagesTest(TestCase):
    def setUp(self):
        cache.clear()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = create_graph_config(**config_values(is_active=True))
        self.certificate = self.config.current_certificate
        self.changelist_url = reverse("admin:core_microsoftgraphproviderconfig_changelist")
        self.add_url = reverse("admin:core_microsoftgraphproviderconfig_add")
        self.change_url = reverse("admin:core_microsoftgraphproviderconfig_change", args=[self.config.pk])
        self.delete_url = reverse("admin:core_microsoftgraphproviderconfig_delete", args=[self.config.pk])

    def post_data(self, **overrides):
        return form_data(is_active="on", _save="Save") | overrides

    def assert_no_key_material(self, response):
        self.assertNotContains(response, "PRIVATE KEY")
        for line in private_key_lines():
            self.assertNotContains(response, line)

    def test_changelist_lists_configs_with_their_thumbprint_and_no_bulk_delete(self):
        create_graph_config(**config_values(name="Standby", mailbox="standby@example.com"), certificate=False)

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MAILBOX)
        self.assertContains(response, "standby@example.com")
        self.assertContains(response, self.certificate.sha1_thumbprint)
        self.assertContains(response, NO_CERTIFICATE)
        self.assertNotContains(response, "delete_selected")
        self.assert_no_key_material(response)

    def test_add_page_renders_no_credential_input(self):
        response = self.client.get(self.add_url)

        self.assertEqual(response.status_code, 200)
        for name in GRAPH_FORM_FIELDS:
            self.assertContains(response, f'name="{name}"')
        for name in ("client_secret", "private_key", "certificate", "auth_method"):
            self.assertNotContains(response, f'name="{name}"')
        self.assertNotContains(response, 'type="password"')

    def test_change_page_shows_the_certificate_panel_and_never_key_material(self):
        previous = install_test_certificate(self.config, state=MicrosoftGraphCertificate.State.PREVIOUS)

        response = self.client.get(self.change_url)

        self.assertEqual(response.status_code, 200)
        for value in (
            self.certificate.sha1_thumbprint,
            self.certificate.sha256_fingerprint,
            self.certificate.serial_number,
            self.certificate.subject,
            # In the site's time zone, as the admin shows every date, with the zone named.
            f"{timezone.localtime(self.certificate.not_after):%Y-%m-%d %H:%M %Z}",
            f'Stored in the in-memory store (tests only), version <span class="break-all font-mono">'
            f"{self.certificate.store_version_id}",
            "Thumbprint (SHA-1, as shown in Entra)",
            "Expires in ",
            "Previous certificate (kept for rollback)",
            previous.sha1_thumbprint,
        ):
            self.assertContains(response, value)
        self.assertNotContains(response, 'name="tenant_id"')
        self.assertNotContains(response, 'name="client_id"')
        self.assert_no_key_material(response)

    def test_without_a_certificate_the_panel_says_so_and_the_application_is_editable(self):
        standby = create_graph_config(**config_values(name="Standby"), certificate=False)

        response = self.client.get(reverse("admin:core_microsoftgraphproviderconfig_change", args=[standby.pk]))

        self.assertContains(response, "None installed: Microsoft Graph cannot send or read mail")
        self.assertContains(response, 'name="tenant_id"')
        self.assertContains(response, 'name="client_id"')

    def test_valid_change_is_saved_and_keeps_the_certificate(self):
        response = self.client.post(self.change_url, self.post_data(name="Renamed"))

        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.name, "Renamed")
        self.assertEqual(self.config.current_certificate, self.certificate)
        self.assertTrue(self.config.is_active)
        entry = LogEntry.objects.get(object_id=str(self.config.pk))
        self.assertNotIn("PRIVATE", entry.get_change_message())

    def test_a_posted_application_change_under_the_certificate_is_ignored(self):
        response = self.client.post(self.change_url, self.post_data(client_id=OTHER_CLIENT_ID, name="Renamed"))

        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual((self.config.name, self.config.client_id), ("Renamed", CLIENT_ID))

    def test_add_creates_an_inactive_config_without_a_certificate(self):
        response = self.client.post(self.add_url, form_data(name="Standby", _save="Save"))

        self.assertEqual(response.status_code, 302)
        created = MicrosoftGraphProviderConfig.objects.get(name="Standby")
        self.assertFalse(created.is_active)
        self.assertIsNone(created.current_certificate)
        self.config.refresh_from_db()
        self.assertTrue(self.config.is_active)

    def test_activating_a_standby_through_the_admin_deactivates_the_active_config(self):
        standby = create_graph_config(**config_values(name="Standby"))
        url = reverse("admin:core_microsoftgraphproviderconfig_change", args=[standby.pk])

        response = self.client.post(url, self.post_data(name="Standby"))

        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        standby.refresh_from_db()
        self.assertFalse(self.config.is_active)
        self.assertTrue(standby.is_active)

    def test_active_config_cannot_be_deleted(self):
        self.assertEqual(self.client.get(self.delete_url).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url, {"post": "yes"}).status_code, 403)

        self.assertTrue(MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).exists())

    def test_inactive_config_can_be_deleted_with_its_certificate_rows(self):
        standby = create_graph_config(**config_values(name="Standby"))
        url = reverse("admin:core_microsoftgraphproviderconfig_delete", args=[standby.pk])

        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.filter(pk=standby.pk).exists())
        self.assertFalse(MicrosoftGraphCertificate.objects.filter(config_id=standby.pk).exists())

    def test_only_staff_granted_the_core_app_can_reach_the_config(self):
        urls = (self.changelist_url, self.add_url, self.change_url)

        self.client.force_login(make_admin(apps=["cms"], email="cms-editor@example.com"))
        for url in urls:
            with self.subTest(grant="cms", url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(self.change_url, self.post_data(mailbox="attacker@example.com"))
        self.assertEqual(response.status_code, 403)
        self.config.refresh_from_db()
        self.assertEqual(self.config.mailbox, MAILBOX)

        self.client.force_login(make_admin(apps=["core"], email="core-admin@example.com"))
        for url in urls:
            with self.subTest(grant="core", url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


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
