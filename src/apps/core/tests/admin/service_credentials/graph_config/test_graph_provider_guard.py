"""The Graph config page cannot stop email that Microsoft Graph sends, nor move it to a config or Entra app that email
could not switch to; scope rows are case-insensitive and editable by Core staff."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.admin.service_credentials.microsoft_graph_scope import WOULD_STOP_EMAIL
from apps.core.models import EmailServiceConfig, MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph import TAKEOVER_REFUSED
from apps.core.tests.graph_helpers import create_graph_config
from apps.event.tests.helpers import make_superuser

Permission = MicrosoftGraphMailboxScope.Permission
MAILBOX = "i2g@contoso.com"
STOPS = WOULD_STOP_EMAIL.format(from_email=MAILBOX)


def sending_limit_data(config=None) -> dict:
    """The sending-limit inputs as the browser posts them (prefilled with the row's values, or the defaults)."""
    config = config or MicrosoftGraphProviderConfig()
    return {
        name: "" if getattr(config, name) is None else str(getattr(config, name))
        for name in (
            "max_recipients_per_message",
            "messages_per_minute_limit",
            "recipients_per_day_limit",
            "external_recipients_per_hour_limit",
            "internal_recipients_per_hour_limit",
        )
    }


def change_data(config, *, scopes=None, new_scopes=(), **overrides):
    """The change form as the browser posts it: config fields, every existing scope row, then new rows."""
    scopes = list(config.mailbox_scopes.all()) if scopes is None else scopes
    data = {
        "name": config.name,
        "is_active": "on" if config.is_active else "",
        "mailbox": config.mailbox,
        **sending_limit_data(config),
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

    def assert_takeover_refused(self, standby, problem):
        response = self.post(standby, change_data(standby, is_active="on"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TAKEOVER_REFUSED.format(problem="")[:60])
        self.assertContains(response, problem)
        self.assertEqual(MicrosoftGraphProviderConfig.load(), self.config)


OTHER_APP = "99999999-8888-7777-6666-555555555555"
