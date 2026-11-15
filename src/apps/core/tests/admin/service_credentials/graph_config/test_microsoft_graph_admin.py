"""Django admin for MicrosoftGraphProviderConfig: no credential inputs, the certificate panel, read-only Entra
application fields, delete rules, access control and confirm-on-save."""

from django.test import TestCase

from apps.core.admin.confirmation.post_data import is_sensitive_field
from apps.core.admin.service_credentials.microsoft_graph.config import (
    GRAPH_FORM_FIELDS,
    MicrosoftGraphProviderConfigForm,
)
from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.tests.graph_helpers import create_graph_config

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
        # The mailbox's sending limits, as the form shows them prefilled.
        "max_recipients_per_message": "500",
        "messages_per_minute_limit": "30",
        "recipients_per_day_limit": "10000",
        "external_recipients_per_hour_limit": "500",
        "internal_recipients_per_hour_limit": "1000",
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

    def test_the_sending_limits_are_entered_on_the_form(self):
        data = form_data(
            max_recipients_per_message="400",
            messages_per_minute_limit="25",
            recipients_per_day_limit="8000",
            external_recipients_per_hour_limit="",
            internal_recipients_per_hour_limit="900",
        )
        form = MicrosoftGraphProviderConfigForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)
        config = form.save()

        config.refresh_from_db()
        self.assertEqual(
            (
                config.max_recipients_per_message,
                config.messages_per_minute_limit,
                config.recipients_per_day_limit,
                config.external_recipients_per_hour_limit,
                config.internal_recipients_per_hour_limit,
            ),
            (400, 25, 8000, None, 900),
        )

    def test_a_limit_that_does_not_fit_the_day_is_refused_on_its_field(self):
        form = MicrosoftGraphProviderConfigForm(data=form_data(recipients_per_day_limit="300"))

        self.assertFalse(form.is_valid())
        self.assertEqual(
            sorted(form.errors),
            ["external_recipients_per_hour_limit", "internal_recipients_per_hour_limit", "max_recipients_per_message"],
        )

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
