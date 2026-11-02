"""Graph config admin: the mailbox scope inline, which edits only public data next to the installed certificate."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.tests.graph_helpers import create_graph_config, grant, private_key_lines
from apps.event.tests.helpers import make_superuser

Permission = MicrosoftGraphMailboxScope.Permission
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_CLIENT_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
MAILBOX = "i2g@contoso.com"


def form_data(**overrides):
    data = {
        "name": "Graph",
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "mailbox": MAILBOX,
    }
    return data | overrides


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class GraphScopeInlineAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = create_graph_config(
            name="Graph", is_active=True, tenant_id=TENANT_ID, client_id=CLIENT_ID, mailbox=MAILBOX
        )
        self.certificate = self.config.current_certificate
        self.change_url = reverse("admin:core_microsoftgraphproviderconfig_change", args=[self.config.pk])

    def post_data(self, scopes=(), initial=(), **overrides):
        data = form_data(is_active="on", _save="Save") | {
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

    def assert_no_key_material(self, response):
        for line in private_key_lines():
            self.assertNotContains(response, line)

    def test_change_page_renders_the_scope_inline_and_the_thumbprint(self):
        grant(self.config, MAILBOX)

        response = self.client.get(self.change_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.certificate.sha1_thumbprint)
        self.assertContains(response, 'name="mailbox_scopes-TOTAL_FORMS"')
        self.assertContains(response, MAILBOX)
        self.assert_no_key_material(response)

    def test_inline_saves_normalized_scope_rows_and_keeps_the_certificate(self):
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
        self.assertEqual(self.config.current_certificate, self.certificate)
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
        self.assert_no_key_material(response)

    def test_the_application_cannot_be_changed_under_the_certificate(self):
        response = self.client.post(self.change_url, self.post_data(client_id=OTHER_CLIENT_ID))

        self.assertEqual(response.status_code, 302)  # the read-only field's posted value is ignored
        self.config.refresh_from_db()
        self.assertEqual(self.config.client_id, CLIENT_ID)
        self.assertEqual(self.config.current_certificate, self.certificate)

    def test_changelist_shows_the_scope_summary(self):
        grant(self.config, MAILBOX, permission=Permission.READ)
        MicrosoftGraphProviderConfig.objects.create(name="Standby", tenant_id=TENANT_ID, client_id=CLIENT_ID)

        response = self.client.get(reverse("admin:core_microsoftgraphproviderconfig_changelist"))

        self.assertContains(response, f"{MAILBOX} (Read only (Mail.Read))")
        self.assertContains(response, "nothing allowed")
        self.assert_no_key_material(response)
