"""Django admin for MicrosoftGraphProviderConfig: secret handling, delete rules and confirm-on-save redaction."""

import json

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.admin.common.base import BaseModelAdmin
from apps.core.admin.mixins.confirm_on_save_utils import (
    REDACTED,
    compute_add_diff,
    compute_change_diff,
    compute_delete_diff,
    is_sensitive_field,
)
from apps.core.admin.service_credentials.microsoft_graph import (
    MicrosoftGraphProviderConfigAdmin,
    MicrosoftGraphProviderConfigForm,
)
from apps.core.models import MicrosoftGraphProviderConfig
from apps.event.tests.helpers import make_admin, make_superuser

TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_CLIENT_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
MAILBOX = "sender@example.com"
STORED_SECRET = "stored-not-a-real-secret"
NEW_SECRET = "replacement-not-a-real-secret"
SESSION_KEY = "_admin_pending_change_core_microsoftgraphproviderconfig"


def config_values(**overrides):
    values = {
        "name": "Mail",
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "auth_method": MicrosoftGraphProviderConfig.AuthMethod.CLIENT_SECRET,
        "client_secret": STORED_SECRET,
        "mailbox": MAILBOX,
    }
    return values | overrides


def form_data(**overrides):
    """Submitted admin form values; a blank secret means 'leave it alone'."""
    data = {
        "name": "Mail",
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "auth_method": "client_secret",
        "certificate": "",
        "private_key": "",
        "client_secret": "",
        "mailbox": MAILBOX,
        "messages_per_minute": "24",
        # The mailbox scope inline's management form, submitted with no rows.
        "mailbox_scopes-TOTAL_FORMS": "0",
        "mailbox_scopes-INITIAL_FORMS": "0",
        "mailbox_scopes-MIN_NUM_FORMS": "0",
        "mailbox_scopes-MAX_NUM_FORMS": "1000",
    }
    return data | overrides


class MicrosoftGraphProviderConfigFormTest(TestCase):
    def setUp(self):
        self.config = MicrosoftGraphProviderConfig.objects.create(**config_values())

    def test_blank_secret_on_edit_keeps_the_stored_secret(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(), instance=self.config)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_secret"], STORED_SECRET)
        form.save()
        self.config.refresh_from_db()
        self.assertEqual(self.config.client_secret, STORED_SECRET)

    def test_new_secret_replaces_the_stored_one(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(client_secret=NEW_SECRET), instance=self.config)

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.config.refresh_from_db()
        self.assertEqual(self.config.client_secret, NEW_SECRET)

    def test_blank_secret_on_create_stays_blank(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(name="Standby"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().client_secret, "")

    def test_activating_a_new_config_without_a_secret_is_rejected_on_the_secret_field(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(name="Next", is_active=True))

        self.assertFalse(form.is_valid())
        self.assertEqual(list(form.errors), ["client_secret"])

    def test_activating_an_existing_config_keeps_its_stored_secret(self):
        standby = MicrosoftGraphProviderConfig.objects.create(**config_values(name="Standby", client_secret="kept"))
        form = MicrosoftGraphProviderConfigForm(data=form_data(name="Standby", is_active=True), instance=standby)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().client_secret, "kept")

    def test_standby_can_replace_the_active_config_without_disabling_it_first(self):
        active = MicrosoftGraphProviderConfig.objects.create(**config_values(name="Primary", is_active=True))
        form = MicrosoftGraphProviderConfigForm(data=form_data(is_active=True), instance=self.config)

        self.assertTrue(form.is_valid(), form.errors)
        # Validation alone must leave the working configuration active.
        self.assertEqual(MicrosoftGraphProviderConfig.load(), active)
        form.save()
        active.refresh_from_db()
        self.assertFalse(active.is_active)
        self.assertEqual(MicrosoftGraphProviderConfig.load(), self.config)
        self.assertEqual(MicrosoftGraphProviderConfig.objects.filter(is_active=True).count(), 1)

    def test_model_validation_errors_appear_on_their_fields(self):
        data = form_data(
            tenant_id="common", client_id="x", mailbox="x", messages_per_minute="31", client_secret=NEW_SECRET
        )
        form = MicrosoftGraphProviderConfigForm(data=data, instance=self.config)

        self.assertFalse(form.is_valid())
        self.assertEqual(sorted(form.errors), ["client_id", "mailbox", "messages_per_minute", "tenant_id"])

    def test_stored_secret_is_not_rendered_into_the_form(self):
        rendered = str(MicrosoftGraphProviderConfigForm(instance=self.config)["client_secret"])

        self.assertIn('type="password"', rendered)
        self.assertNotIn(STORED_SECRET, rendered)

    def test_rejected_submission_does_not_echo_the_typed_secret(self):
        form = MicrosoftGraphProviderConfigForm(
            data=form_data(tenant_id="common", client_secret=NEW_SECRET), instance=self.config
        )

        self.assertFalse(form.is_valid())
        self.assertNotIn(NEW_SECRET, str(form["client_secret"]))
        self.assertNotIn(NEW_SECRET, form.as_p())

    def test_secret_field_is_optional(self):
        self.assertFalse(MicrosoftGraphProviderConfigForm().fields["client_secret"].required)

    def test_a_blank_secret_cannot_ride_along_with_a_different_application(self):
        for field, value in (("tenant_id", "contoso.onmicrosoft.com"), ("client_id", OTHER_CLIENT_ID)):
            with self.subTest(field):
                stored = MicrosoftGraphProviderConfig.objects.get(pk=self.config.pk)
                form = MicrosoftGraphProviderConfigForm(data=form_data(**{field: value}), instance=stored)

                self.assertFalse(form.is_valid())
                self.assertEqual(list(form.errors), ["client_secret"])
                self.assertIn("new application", form.errors["client_secret"][0])

    def test_a_new_secret_may_accompany_a_different_application(self):
        form = MicrosoftGraphProviderConfigForm(
            data=form_data(client_id=OTHER_CLIENT_ID, client_secret=NEW_SECRET), instance=self.config
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_secret"], NEW_SECRET)

    def test_a_blank_secret_is_fine_for_edits_that_keep_the_same_application(self):
        form = MicrosoftGraphProviderConfigForm(
            data=form_data(mailbox="other@example.com", messages_per_minute="12"), instance=self.config
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_a_new_record_is_not_held_to_the_application_rule(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(client_id=OTHER_CLIENT_ID))

        self.assertTrue(form.is_valid(), form.errors)

    def test_an_untouched_form_is_not_reported_as_changed_by_the_write_only_secret(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(), instance=self.config)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.changed_data, [])

    def test_a_submitted_secret_counts_as_a_change(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(client_secret=NEW_SECRET), instance=self.config)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.changed_data, ["client_secret"])

    def test_a_whitespace_only_secret_counts_as_blank_for_the_application_rule(self):
        for blank in (" ", "   ", "\t"):
            with self.subTest(repr(blank)):
                # A fresh instance: a ModelForm copies submitted values onto its instance even when invalid.
                stored = MicrosoftGraphProviderConfig.objects.get(pk=self.config.pk)
                form = MicrosoftGraphProviderConfigForm(
                    data=form_data(client_id=OTHER_CLIENT_ID, client_secret=blank), instance=stored
                )

                self.assertFalse(form.is_valid())
                self.assertIn("new application", form.errors["client_secret"][0])

    def test_a_whitespace_only_secret_keeps_the_stored_one_and_is_not_a_change(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(client_secret="   "), instance=self.config)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_secret"], STORED_SECRET)
        self.assertEqual(form.changed_data, [])

    def test_the_secret_field_is_labelled_for_people(self):
        self.assertEqual(MicrosoftGraphProviderConfigForm().fields["client_secret"].label, "Client Secret")


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

    def test_delete_permission_is_denied_only_for_the_active_config(self):
        active = MicrosoftGraphProviderConfig.objects.create(**config_values(name="Active", is_active=True))
        inactive = MicrosoftGraphProviderConfig.objects.create(**config_values(name="Inactive"))

        self.assertFalse(self.model_admin.has_delete_permission(self.request(), active))
        self.assertTrue(self.model_admin.has_delete_permission(self.request(), inactive))
        self.assertTrue(self.model_admin.has_delete_permission(self.request(), None))

    def test_delete_selected_is_not_offered(self):
        # The stock admin offers it to this superuser, so its absence is down to the admin class.
        stock = BaseModelAdmin(MicrosoftGraphProviderConfig, AdminSite())
        self.assertIn("delete_selected", stock.get_actions(self.request()))

        self.assertNotIn("delete_selected", self.model_admin.get_actions(self.request()))

    def test_secret_is_never_listed_filtered_or_searchable(self):
        for setting in (self.model_admin.list_display, self.model_admin.list_filter, self.model_admin.search_fields):
            with self.subTest(setting=setting):
                self.assertNotIn("client_secret", setting)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MicrosoftGraphProviderConfigAdminPagesTest(TestCase):
    def setUp(self):
        cache.clear()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = MicrosoftGraphProviderConfig.objects.create(**config_values(is_active=True))
        self.changelist_url = reverse("admin:core_microsoftgraphproviderconfig_changelist")
        self.add_url = reverse("admin:core_microsoftgraphproviderconfig_add")
        self.change_url = reverse("admin:core_microsoftgraphproviderconfig_change", args=[self.config.pk])
        self.delete_url = reverse("admin:core_microsoftgraphproviderconfig_delete", args=[self.config.pk])

    def post_data(self, **overrides):
        return form_data(is_active="on", _save="Save") | overrides

    def test_changelist_lists_configs_without_secrets_or_bulk_delete(self):
        MicrosoftGraphProviderConfig.objects.create(**config_values(name="Standby", mailbox="standby@example.com"))

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MAILBOX)
        self.assertContains(response, "standby@example.com")
        self.assertContains(response, CLIENT_ID)
        self.assertContains(response, "Inactive")
        self.assertNotContains(response, STORED_SECRET)
        self.assertNotContains(response, "delete_selected")

    def test_add_page_renders_with_a_password_input_for_the_secret(self):
        response = self.client.get(self.add_url)

        self.assertEqual(response.status_code, 200)
        for name in ("name", "tenant_id", "client_id", "client_secret", "mailbox", "messages_per_minute"):
            self.assertContains(response, f'name="{name}"')
        self.assertContains(response, 'type="password"')

    def test_change_page_renders_without_the_stored_secret(self):
        response = self.client.get(self.change_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TENANT_ID)
        self.assertContains(response, 'name="client_secret"')
        self.assertNotContains(response, STORED_SECRET)

    def test_valid_change_is_saved_and_a_blank_secret_keeps_the_stored_one(self):
        response = self.client.post(self.change_url, self.post_data(name="Renamed", messages_per_minute="12"))

        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.name, "Renamed")
        self.assertEqual(self.config.messages_per_minute, 12)
        self.assertEqual(self.config.client_secret, STORED_SECRET)
        self.assertTrue(self.config.is_active)

    def test_new_secret_replaces_the_stored_one_and_stays_out_of_the_admin_log(self):
        response = self.client.post(self.change_url, self.post_data(client_secret=NEW_SECRET), follow=True)

        self.assertContains(response, "was changed successfully")
        self.assertNotContains(response, NEW_SECRET)
        self.config.refresh_from_db()
        self.assertEqual(self.config.client_secret, NEW_SECRET)
        entry = LogEntry.objects.get(object_id=str(self.config.pk))
        for text in (entry.get_change_message(), entry.object_repr):
            self.assertNotIn(NEW_SECRET, text)
            self.assertNotIn(STORED_SECRET, text)

    def test_invalid_change_is_rejected_without_echoing_the_typed_secret(self):
        response = self.client.post(self.change_url, self.post_data(tenant_id="common", client_secret=NEW_SECRET))

        self.assertEqual(response.status_code, 200)
        self.assertIn("tenant_id", response.context["adminform"].form.errors)
        self.assertNotContains(response, NEW_SECRET)
        self.config.refresh_from_db()
        self.assertEqual(self.config.tenant_id, TENANT_ID)
        self.assertEqual(self.config.client_secret, STORED_SECRET)

    def test_add_creates_an_inactive_config_with_the_submitted_secret(self):
        data = form_data(name="Standby", client_secret=NEW_SECRET, _save="Save")

        response = self.client.post(self.add_url, data)

        self.assertEqual(response.status_code, 302)
        created = MicrosoftGraphProviderConfig.objects.get(name="Standby")
        self.assertFalse(created.is_active)
        self.assertEqual(created.client_secret, NEW_SECRET)
        self.config.refresh_from_db()
        self.assertTrue(self.config.is_active)

    def test_activating_a_standby_through_the_admin_deactivates_the_active_config(self):
        standby = MicrosoftGraphProviderConfig.objects.create(**config_values(name="Standby"))
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

    def test_inactive_config_can_be_deleted(self):
        standby = MicrosoftGraphProviderConfig.objects.create(**config_values(name="Standby"))
        url = reverse("admin:core_microsoftgraphproviderconfig_delete", args=[standby.pk])

        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.filter(pk=standby.pk).exists())

    def test_only_staff_granted_the_core_app_can_reach_the_credentials(self):
        urls = (self.changelist_url, self.add_url, self.change_url)

        self.client.force_login(make_admin(apps=["cms"], email="cms-editor@example.com"))
        for url in urls:
            with self.subTest(grant="cms", url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(self.change_url, self.post_data(client_secret=NEW_SECRET))
        self.assertEqual(response.status_code, 403)
        self.config.refresh_from_db()
        self.assertEqual(self.config.client_secret, STORED_SECRET)

        self.client.force_login(make_admin(apps=["core"], email="core-admin@example.com"))
        for url in urls:
            with self.subTest(grant="core", url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class MicrosoftGraphProviderConfigConfirmRedactionTest(TestCase):
    """The type-to-confirm step must not expose or persist the client secret in the clear."""

    def setUp(self):
        cache.clear()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = MicrosoftGraphProviderConfig.objects.create(**config_values(is_active=True))
        self.change_url = reverse("admin:core_microsoftgraphproviderconfig_change", args=[self.config.pk])
        self.add_url = reverse("admin:core_microsoftgraphproviderconfig_add")
        self.confirm_url = reverse("admin:core_microsoftgraphproviderconfig_confirm_change")
        self.confirmation_word = MicrosoftGraphProviderConfig._meta.verbose_name

    def tearDown(self):
        cache.clear()

    def test_client_secret_is_classified_as_sensitive(self):
        form = MicrosoftGraphProviderConfigForm()

        self.assertTrue(is_sensitive_field("client_secret", form))
        for name in ("name", "tenant_id", "client_id", "mailbox", "messages_per_minute"):
            with self.subTest(name=name):
                self.assertFalse(is_sensitive_field(name, form))

    def test_change_diff_masks_the_old_and_new_secret_but_not_other_fields(self):
        data = form_data(client_id=OTHER_CLIENT_ID, client_secret=NEW_SECRET)
        form = MicrosoftGraphProviderConfigForm(data=data, instance=self.config)
        self.assertTrue(form.is_valid(), form.errors)

        diff = compute_change_diff(MicrosoftGraphProviderConfig, self.config.pk, form)

        rows = {row["field"]: row for row in diff}
        self.assertEqual(rows["client_secret"]["old_value"], REDACTED)
        self.assertEqual(rows["client_secret"]["new_value"], REDACTED)
        self.assertEqual(rows["client_id"]["new_value"], OTHER_CLIENT_ID)
        self.assertNotIn(STORED_SECRET, json.dumps(diff))
        self.assertNotIn(NEW_SECRET, json.dumps(diff))

    def test_add_diff_masks_the_secret(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(name="Standby", client_secret=NEW_SECRET))
        self.assertTrue(form.is_valid(), form.errors)

        diff = compute_add_diff(form)

        rows = {row["field"]: row for row in diff}
        self.assertEqual(rows["client_secret"]["new_value"], REDACTED)
        self.assertEqual(rows["tenant_id"]["new_value"], TENANT_ID)
        self.assertNotIn(NEW_SECRET, json.dumps(diff))

    def test_delete_diff_masks_the_stored_secret(self):
        diff = compute_delete_diff(self.config)

        rows = {row["field"]: row for row in diff}
        self.assertEqual(rows["client_secret"]["value"], REDACTED)
        self.assertNotIn(STORED_SECRET, json.dumps(diff))

    def test_confirmed_change_saves_the_secret_without_exposing_it_before_or_after(self):
        data = form_data(is_active="on", client_secret=NEW_SECRET, _save="Save")
        response = self.client.post(self.change_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.confirm_url)

        pending = self.client.session[SESSION_KEY]
        self.assertNotIn("client_secret", pending["post_data"])
        self.assertNotIn(NEW_SECRET, json.dumps(pending))
        self.assertNotIn(STORED_SECRET, json.dumps(pending))
        page = self.client.get(self.confirm_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, REDACTED)
        self.assertNotContains(page, NEW_SECRET)
        self.assertNotContains(page, STORED_SECRET)
        self.config.refresh_from_db()
        self.assertEqual(self.config.client_secret, STORED_SECRET)

        confirmed = self.client.post(
            self.confirm_url, {"confirmation_word": self.confirmation_word, "token": pending["token"]}
        )

        self.assertEqual(confirmed.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.client_secret, NEW_SECRET)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_confirmed_add_saves_the_secret_without_keeping_it_in_the_session(self):
        data = form_data(name="Standby", client_secret=NEW_SECRET, _save="Save")
        response = self.client.post(self.add_url, data)
        self.assertEqual(response["Location"], self.confirm_url)

        pending = self.client.session[SESSION_KEY]
        self.assertNotIn(NEW_SECRET, json.dumps(pending))
        self.assertNotContains(self.client.get(self.confirm_url), NEW_SECRET)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.filter(name="Standby").exists())

        self.client.post(self.confirm_url, {"confirmation_word": self.confirmation_word, "token": pending["token"]})

        self.assertEqual(MicrosoftGraphProviderConfig.objects.get(name="Standby").client_secret, NEW_SECRET)
