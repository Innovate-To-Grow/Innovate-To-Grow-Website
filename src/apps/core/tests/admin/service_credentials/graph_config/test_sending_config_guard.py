from django.test import override_settings
from django.urls import reverse

from apps.core.models import EmailServiceConfig, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.credential.recovery import remove_certificates
from apps.core.tests.admin.service_credentials.graph_config.test_graph_provider_guard import (
    MAILBOX,
    OTHER_APP,
    GuardFixture,
    Permission,
    change_data,
    sending_limit_data,
)
from apps.core.tests.graph_helpers import CLIENT_ID, TENANT_ID, create_graph_config, install_test_certificate
from apps.core.tests.project.models.graph.test_graph_go_live_gate import DENY, evidence
from apps.event.tests.helpers import make_admin


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
        data = change_data(self.config, new_scopes=[("alias@contoso.com", Permission.SEND)], name="Renamed")

        response = self.post(self.config, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.config.mailbox_scopes.count(), 2)
        self.assertTrue(EmailServiceConfig.load().delivery_configured)

    def test_a_standby_that_cannot_send_cannot_take_over(self):
        without_certificate = create_graph_config(name="No certificate", certificate=False, scope=(MAILBOX,))
        out_of_scope = create_graph_config(name="Out of scope", mailbox=MAILBOX, scope=("other@contoso.com",))

        self.assert_takeover_refused(without_certificate, "has no current certificate")
        self.assert_refused(self.post(out_of_scope, change_data(out_of_scope, is_active="on")))
        self.config.refresh_from_db()
        self.assertTrue(self.config.is_active)

    def test_a_standby_whose_certificate_entra_has_not_trusted_cannot_take_over(self):
        standby = create_graph_config(name="Standby", mailbox=MAILBOX, scope=(MAILBOX,), certificate=False)
        install_test_certificate(standby, entra_check="not_trusted")

        self.assert_takeover_refused(standby, "Microsoft Entra has not issued a token with its current certificate")

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
            **sending_limit_data(),
            "_save": "Save",
            "mailbox_scopes-TOTAL_FORMS": "1",
            "mailbox_scopes-INITIAL_FORMS": "0",
            "mailbox_scopes-MIN_NUM_FORMS": "0",
            "mailbox_scopes-MAX_NUM_FORMS": "1000",
            "mailbox_scopes-0-mailbox": MAILBOX,
            "mailbox_scopes-0-permission": Permission.SEND_AND_READ,
        }

        response = self.client.post(reverse("admin:core_microsoftgraphproviderconfig_add"), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "has no current certificate")
        self.assertEqual(MicrosoftGraphProviderConfig.objects.count(), 1)

    def test_a_standby_can_still_be_edited_and_deleted(self):
        standby = create_graph_config(name="Standby", certificate=False)

        self.assertEqual(self.post(standby, change_data(standby, name="Renamed")).status_code, 302)
        delete_url = reverse("admin:core_microsoftgraphproviderconfig_delete", args=[standby.pk])
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 302)
        self.assertTrue(EmailServiceConfig.load().delivery_configured)


@override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
class TakeoverGateTests(GuardFixture):
    """With the go-live gate on, a standby (here for another Entra app) takes over only with evidence of its own."""

    def setUp(self):
        super().setUp()
        self.standby = create_graph_config(
            name="Standby", mailbox=MAILBOX, scope=(MAILBOX,), client_id=OTHER_APP, access_check_deny_mailbox=DENY
        )

    def test_admins_cannot_activate_a_standby_without_evidence(self):
        evidence(self.config)  # the sending config's evidence says nothing about the standby's app
        self.client.force_login(make_admin(email="other-admin@example.com"))
        self.assert_takeover_refused(self.standby, "no access check is recorded for the current certificate")
        self.assertTrue(EmailServiceConfig.load().delivery_configured)

    def test_a_standby_with_its_own_passing_check_may_take_over(self):
        evidence(self.standby)
        self.client.force_login(make_admin(email="other-admin@example.com"))

        response = self.post(self.standby, change_data(self.standby, is_active="on"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MicrosoftGraphProviderConfig.load(), self.standby)

    def test_after_removing_its_certificates_the_sending_config_cannot_move_to_another_app(self):
        remove_certificates(self.config, reason="Moving to another app")

        response = self.post(self.config, change_data(self.config, client_id=OTHER_APP, tenant_id=TENANT_ID))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "its Entra application cannot change")
        self.config.refresh_from_db()
        self.assertEqual(self.config.client_id, CLIENT_ID)


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
