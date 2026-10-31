"""The Graph config page cannot stop email that Microsoft Graph sends; scope rows are case-insensitive and editable
by Core staff."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.admin.service_credentials.microsoft_graph_scope import WOULD_STOP_EMAIL
from apps.core.models import EmailServiceConfig, MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.tests.graph_helpers import CLIENT_ID, TENANT_ID, create_graph_config
from apps.event.tests.helpers import make_admin, make_superuser

Permission = MicrosoftGraphMailboxScope.Permission
MAILBOX = "i2g@contoso.com"
STOPS = WOULD_STOP_EMAIL.format(from_email=MAILBOX)


def change_data(config, *, scopes=None, new_scopes=(), **overrides):
    """The change form as the browser posts it: config fields, every existing scope row, then new rows."""
    scopes = list(config.mailbox_scopes.all()) if scopes is None else scopes
    data = {
        "name": config.name,
        "is_active": "on" if config.is_active else "",
        "mailbox": config.mailbox,
        "messages_per_minute": str(config.messages_per_minute),
        "_save": "Save",
        "mailbox_scopes-TOTAL_FORMS": str(len(scopes) + len(new_scopes)),
        "mailbox_scopes-INITIAL_FORMS": str(len(scopes)),
        "mailbox_scopes-MIN_NUM_FORMS": "0",
        "mailbox_scopes-MAX_NUM_FORMS": "1000",
    }
    if config.current_certificate is None:
        data |= {"tenant_id": config.tenant_id, "client_id": config.client_id}
    for index, scope in enumerate(scopes):
        data |= {
            f"mailbox_scopes-{index}-id": str(scope.pk),
            f"mailbox_scopes-{index}-config": str(config.pk),
            f"mailbox_scopes-{index}-mailbox": scope.mailbox,
            f"mailbox_scopes-{index}-permission": scope.permission,
        }
    for offset, (mailbox, permission) in enumerate(new_scopes, start=len(scopes)):
        data |= {
            f"mailbox_scopes-{offset}-config": str(config.pk),
            f"mailbox_scopes-{offset}-mailbox": mailbox,
            f"mailbox_scopes-{offset}-permission": permission,
        }
    data = {key: value for key, value in data.items() if value != ""}
    return data | overrides


def change_url(config):
    return reverse("admin:core_microsoftgraphproviderconfig_change", args=[config.pk])


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class GuardFixture(TestCase):
    """Email is sent through the active, working Graph config ``self.config``."""

    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())
        self.config = create_graph_config(name="Graph", is_active=True, mailbox=MAILBOX, scope=(MAILBOX,))
        self.email = EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="graph", from_email=MAILBOX
        )
        self.assertTrue(self.email.delivery_configured)

    def post(self, config, data):
        return self.client.post(change_url(config), data)

    def assert_refused(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, STOPS)
        self.assertTrue(EmailServiceConfig.load().delivery_configured)


class SendingConfigGuardTests(GuardFixture):
    def test_the_sending_config_cannot_be_deactivated(self):
        data = change_data(self.config)
        data.pop("is_active")

        self.assert_refused(self.post(self.config, data))
        self.config.refresh_from_db()
        self.assertTrue(self.config.is_active)

    def test_its_last_sending_scope_row_cannot_be_deleted_or_narrowed(self):
        scope = self.config.mailbox_scopes.get()
        for change in ({"mailbox_scopes-0-DELETE": "on"}, {"mailbox_scopes-0-permission": Permission.READ}):
            with self.subTest(change):
                self.assert_refused(self.post(self.config, change_data(self.config) | change))
                scope.refresh_from_db()
                self.assertEqual(scope.permission, Permission.SEND_AND_READ)

    def test_the_sender_mailbox_cannot_move_outside_the_scope(self):
        self.assert_refused(self.post(self.config, change_data(self.config, mailbox="other@contoso.com")))
        self.config.refresh_from_db()
        self.assertEqual(self.config.mailbox, MAILBOX)

    def test_changes_that_keep_it_sending_are_saved(self):
        data = change_data(self.config, new_scopes=[("alias@contoso.com", Permission.SEND)], messages_per_minute="12")

        response = self.post(self.config, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.config.mailbox_scopes.count(), 2)
        self.assertTrue(EmailServiceConfig.load().delivery_configured)

    def test_a_standby_that_cannot_send_cannot_take_over(self):
        standby = create_graph_config(name="Standby", certificate=False, scope=(MAILBOX,))

        self.assert_refused(self.post(standby, change_data(standby, is_active="on")))
        self.config.refresh_from_db()
        self.assertTrue(self.config.is_active)

    def test_a_standby_that_can_send_may_take_over(self):
        standby = create_graph_config(name="Standby", mailbox=MAILBOX, scope=(MAILBOX,))

        response = self.post(standby, change_data(standby, is_active="on"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MicrosoftGraphProviderConfig.load(), standby)
        self.assertTrue(EmailServiceConfig.load().delivery_configured)

    def test_adding_a_new_active_config_is_refused(self):
        data = {
            "name": "New",
            "is_active": "on",
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
            "mailbox": MAILBOX,
            "messages_per_minute": "24",
            "_save": "Save",
            "mailbox_scopes-TOTAL_FORMS": "1",
            "mailbox_scopes-INITIAL_FORMS": "0",
            "mailbox_scopes-MIN_NUM_FORMS": "0",
            "mailbox_scopes-MAX_NUM_FORMS": "1000",
            "mailbox_scopes-0-mailbox": MAILBOX,
            "mailbox_scopes-0-permission": Permission.SEND_AND_READ,
        }

        response = self.client.post(reverse("admin:core_microsoftgraphproviderconfig_add"), data)

        self.assert_refused(response)
        self.assertEqual(MicrosoftGraphProviderConfig.objects.count(), 1)

    def test_a_standby_can_still_be_edited_and_deleted(self):
        standby = create_graph_config(name="Standby", certificate=False)

        self.assertEqual(self.post(standby, change_data(standby, name="Renamed")).status_code, 302)
        delete_url = reverse("admin:core_microsoftgraphproviderconfig_delete", args=[standby.pk])
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 302)
        self.assertTrue(EmailServiceConfig.load().delivery_configured)


class GuardOffTests(GuardFixture):
    def test_with_another_provider_selected_the_graph_config_may_be_deactivated(self):
        self.email.provider = "ses"
        self.email.save()
        data = change_data(self.config)
        data.pop("is_active")

        self.assertEqual(self.post(self.config, data).status_code, 302)
        self.config.refresh_from_db()
        self.assertFalse(self.config.is_active)

    def test_when_graph_already_cannot_send_edits_are_not_blocked(self):
        self.email.from_email = "outside@contoso.com"  # not in the scope, so email already fails
        self.email.save()
        data = change_data(self.config)
        data.pop("is_active")

        self.assertEqual(self.post(self.config, data).status_code, 302)


class ScopeInlineTests(GuardFixture):
    def test_two_rows_for_one_mailbox_in_different_case_are_a_form_error(self):
        self.email.provider = "ses"
        self.email.save()
        new_scopes = [("Alias@Contoso.com", Permission.SEND), ("alias@contoso.com", Permission.READ)]

        response = self.post(self.config, change_data(self.config, new_scopes=new_scopes))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please correct the duplicate data for mailbox")
        self.assertEqual(self.config.mailbox_scopes.count(), 1)

    def test_a_new_row_that_repeats_a_stored_mailbox_in_another_case_is_a_form_error(self):
        response = self.post(self.config, change_data(self.config, new_scopes=[("I2G@Contoso.com", "send")]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please correct the duplicate data for mailbox")

    def test_core_staff_can_see_and_edit_the_scope(self):
        self.client.force_login(make_admin(apps=["core"], email="core@example.com"))

        page = self.client.get(change_url(self.config))
        self.assertContains(page, 'name="mailbox_scopes-TOTAL_FORMS"')
        response = self.post(self.config, change_data(self.config, new_scopes=[("alias@contoso.com", "send")]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.config.mailbox_scopes.filter(mailbox="alias@contoso.com").exists())

    def test_core_staff_are_held_to_the_same_guard(self):
        self.client.force_login(make_admin(apps=["core"], email="core@example.com"))

        self.assert_refused(self.post(self.config, change_data(self.config) | {"mailbox_scopes-0-DELETE": "on"}))
