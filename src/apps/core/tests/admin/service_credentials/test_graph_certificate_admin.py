"""Graph config admin: the write-only private key, the application rule, and the mailbox scope inline."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.admin.service_credentials.microsoft_graph import MicrosoftGraphProviderConfigForm
from apps.core.models import MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.tests.graph_helpers import certificate_pair, grant
from apps.event.tests.helpers import make_superuser
from apps.mail.admin.settings.forms import GraphDeliveryForm

AuthMethod = MicrosoftGraphProviderConfig.AuthMethod
Permission = MicrosoftGraphMailboxScope.Permission
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_CLIENT_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
MAILBOX = "i2g@contoso.com"
NEW_APPLICATION_ERROR = "Enter the private key for the new application."


def key_body(key_pem):
    """A line of base64 key material that must never appear in rendered HTML."""
    return key_pem.splitlines()[2]


def form_data(certificate, **overrides):
    data = {
        "name": "Graph",
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "auth_method": AuthMethod.CERTIFICATE,
        "certificate": certificate,
        "private_key": "",
        "client_secret": "",
        "mailbox": MAILBOX,
        "messages_per_minute": "24",
    }
    return data | overrides


class GraphCertificateFormTests(TestCase):
    def setUp(self):
        self.certificate, self.key = certificate_pair()
        self.config = MicrosoftGraphProviderConfig.objects.create(
            name="Graph",
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            auth_method=AuthMethod.CERTIFICATE,
            certificate=self.certificate,
            private_key=self.key,
            mailbox=MAILBOX,
        )

    def form(self, **overrides):
        return MicrosoftGraphProviderConfigForm(data=form_data(self.certificate, **overrides), instance=self.config)

    def test_blank_private_key_keeps_the_stored_key(self):
        form = self.form(name="Renamed")

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.config.refresh_from_db()
        self.assertEqual((self.config.name, self.config.private_key), ("Renamed", self.key.strip()))
        self.assertTrue(self.config.certificate_thumbprint)

    def test_whitespace_only_private_key_keeps_the_stored_key(self):
        form = self.form(private_key="   \n ")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["private_key"], self.key.strip())

    def test_a_new_pair_replaces_the_stored_one(self):
        certificate, key = certificate_pair(days_valid=30)
        form = MicrosoftGraphProviderConfigForm(data=form_data(certificate, private_key=key), instance=self.config)

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.config.refresh_from_db()
        self.assertEqual(self.config.certificate, certificate.strip())
        self.assertLess((self.config.certificate_expires_at - self.config.created_at).days, 31)

    def test_changing_the_application_requires_the_key_again(self):
        for field, value in {"client_id": OTHER_CLIENT_ID, "tenant_id": "contoso.onmicrosoft.com"}.items():
            with self.subTest(field):
                form = self.form(**{field: value})
                self.assertFalse(form.is_valid())
                self.assertEqual(form.errors["private_key"], [NEW_APPLICATION_ERROR])

    def test_a_new_key_may_accompany_a_new_application(self):
        form = self.form(client_id=OTHER_CLIENT_ID, private_key=self.key)

        self.assertTrue(form.is_valid(), form.errors)

    def test_both_kept_secrets_are_flagged_on_an_application_change(self):
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(client_secret="stored-not-a-real-secret")
        self.config.refresh_from_db()

        form = self.form(client_id=OTHER_CLIENT_ID)

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["client_secret"], ["Enter the client secret for the new application."])
        self.assertEqual(form.errors["private_key"], [NEW_APPLICATION_ERROR])

    def test_a_mismatched_key_is_reported_without_echoing_it(self):
        _, other_key = certificate_pair(key_size=3072)
        form = self.form(private_key=other_key)

        self.assertFalse(form.is_valid())
        self.assertIn("does not belong", " ".join(form.errors["certificate"]))
        self.assertNotIn(key_body(other_key), str(form.errors))

    def test_the_submitted_blank_key_is_rendered_blank(self):
        html = str(self.form())

        self.assertIn('name="private_key"', html)
        self.assertNotIn(key_body(self.key), html)

    def test_the_stored_key_is_never_rendered_on_an_unbound_form(self):
        html = str(MicrosoftGraphProviderConfigForm(instance=self.config))

        self.assertIn('name="private_key"', html)
        self.assertNotIn(key_body(self.key), html)

    def test_the_mail_settings_graph_form_never_renders_the_stored_key(self):
        html = str(GraphDeliveryForm(instance=self.config))

        self.assertIn('name="private_key"', html)
        self.assertNotIn(key_body(self.key), html)

    def test_an_untouched_key_is_not_a_change(self):
        self.assertNotIn("private_key", self.form().changed_data)
        self.assertIn("private_key", self.form(private_key=self.key).changed_data)

    def test_a_new_config_with_blank_key_stays_blank(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data("", name="Standby"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["private_key"], "")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class GraphCertificateAdminPagesTests(TestCase):
    def setUp(self):
        cache.clear()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.certificate, self.key = certificate_pair()
        self.config = MicrosoftGraphProviderConfig.objects.create(
            name="Graph",
            is_active=True,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            auth_method=AuthMethod.CERTIFICATE,
            certificate=self.certificate,
            private_key=self.key,
            mailbox=MAILBOX,
        )
        self.change_url = reverse("admin:core_microsoftgraphproviderconfig_change", args=[self.config.pk])

    def post_data(self, scopes=(), initial=(), **overrides):
        data = form_data(self.certificate, is_active="on", _save="Save") | {
            "mailbox_scopes-TOTAL_FORMS": str(len(initial) + len(scopes)),
            "mailbox_scopes-INITIAL_FORMS": str(len(initial)),
            "mailbox_scopes-MIN_NUM_FORMS": "0",
            "mailbox_scopes-MAX_NUM_FORMS": "1000",
        }
        for index, scope in enumerate(initial):
            data[f"mailbox_scopes-{index}-id"] = str(scope.pk)
            data[f"mailbox_scopes-{index}-config"] = str(self.config.pk)
            data[f"mailbox_scopes-{index}-mailbox"] = scope.mailbox
            data[f"mailbox_scopes-{index}-permission"] = scope.permission
        for offset, (mailbox, permission) in enumerate(scopes, start=len(initial)):
            data[f"mailbox_scopes-{offset}-config"] = str(self.config.pk)
            data[f"mailbox_scopes-{offset}-mailbox"] = mailbox
            data[f"mailbox_scopes-{offset}-permission"] = permission
        return data | overrides

    def test_change_page_never_renders_the_private_key(self):
        grant(self.config, MAILBOX)

        response = self.client.get(self.change_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="private_key"')
        self.assertContains(response, self.config.certificate_thumbprint)
        self.assertContains(response, 'name="mailbox_scopes-TOTAL_FORMS"')
        self.assertContains(response, MAILBOX)
        self.assertNotContains(response, key_body(self.key))

    def test_inline_saves_normalized_scope_rows_and_keeps_the_key(self):
        response = self.client.post(
            self.change_url,
            self.post_data(scopes=[("I2G@Contoso.com", Permission.SEND_AND_READ), ("alias@contoso.com", "send")]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(self.config.mailbox_scopes.values_list("mailbox", "permission")),
            [("alias@contoso.com", "send"), (MAILBOX, "send_read")],
        )
        self.config.refresh_from_db()
        self.assertEqual(self.config.private_key, self.key.strip())
        self.assertTrue(self.config.is_configured)

    def test_inline_updates_and_deletes_existing_rows(self):
        keep = MicrosoftGraphMailboxScope.objects.create(config=self.config, mailbox=MAILBOX, permission="send")
        drop = MicrosoftGraphMailboxScope.objects.create(config=self.config, mailbox="old@contoso.com")
        keep.permission = Permission.READ
        data = self.post_data(initial=(drop, keep), **{"mailbox_scopes-0-DELETE": "on"})

        response = self.client.post(self.change_url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.config.mailbox_scopes.values_list("mailbox", "permission")), [(MAILBOX, "read")])

    def test_inline_rejects_a_malformed_mailbox(self):
        response = self.client.post(self.change_url, self.post_data(scopes=[("not a mailbox", "send")]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.config.mailbox_scopes.exists())
        self.assertNotContains(response, key_body(self.key))

    def test_changing_the_application_without_a_key_is_refused(self):
        response = self.client.post(self.change_url, self.post_data(client_id=OTHER_CLIENT_ID))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, NEW_APPLICATION_ERROR)
        self.assertNotContains(response, key_body(self.key))
        self.config.refresh_from_db()
        self.assertEqual(self.config.client_id, CLIENT_ID)

    def test_a_submitted_key_is_not_echoed_back_on_a_rejected_save(self):
        response = self.client.post(self.change_url, self.post_data(tenant_id="common", private_key=self.key))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, key_body(self.key))

    def test_changelist_shows_the_scope_summary_and_never_the_key(self):
        grant(self.config, MAILBOX, permission=Permission.READ)
        MicrosoftGraphProviderConfig.objects.create(
            name="Standby", tenant_id=TENANT_ID, client_id=CLIENT_ID, client_secret="not-a-real-secret"
        )

        response = self.client.get(reverse("admin:core_microsoftgraphproviderconfig_changelist"))

        self.assertContains(response, f"{MAILBOX} (Read only (Mail.Read))")
        self.assertContains(response, "nothing allowed")
        self.assertNotContains(response, key_body(self.key))
        self.assertNotContains(response, "not-a-real-secret")
