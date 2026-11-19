""" "Check permissions" on the Graph config page: POST only, the Core app, the 30-second cooldown, the card it fills,
and the warning when Message Trace is switched on while the token lacks its role."""

from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.admin.service_credentials.microsoft_graph.permissions import NO_CHECK_YET
from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphPermissionCheck, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.access_check import permissions
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.admin.service_credentials.graph_config.test_graph_provider_guard import change_data
from apps.core.tests.services.graph.tracing import TRACE_ROLE, TraceSetupMixin, token_response, token_with_roles
from apps.event.tests.helpers import make_admin, make_superuser

PREFIX = "admin:core_microsoftgraphproviderconfig"
OIT_ROLES = ("Mail.ReadWrite", "Mail.Send")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class PermissionCheckAdminTests(TraceSetupMixin, TestCase):
    message_trace = False

    def setUp(self):
        super().setUp()
        self.superuser = make_superuser()
        self.client.force_login(self.superuser)
        self.url = reverse(f"{PREFIX}_check_permissions", args=[self.config.pk])
        self.change_url = reverse(f"{PREFIX}_change", args=[self.config.pk])
        self.use_roles(OIT_ROLES)

    def use_roles(self, roles):
        self.microsoft.token = token_response(token=token_with_roles(roles))

    def card(self) -> str:
        html = self.client.get(self.change_url).content.decode()
        start = html.index('id="graph-permissions"')
        return html[start : html.index("</section>", start)]

    def test_it_is_post_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertFalse(MicrosoftGraphPermissionCheck.objects.exists())
        self.assertEqual(self.microsoft.requests, [])

    def test_a_check_is_recorded_and_returns_to_the_card(self):
        response = self.client.post(self.url)

        self.assertRedirects(response, f"{self.change_url}#graph-permissions", fetch_redirect_response=False)
        check = MicrosoftGraphPermissionCheck.objects.get()
        self.assertEqual((check.checked_by, check.granted_roles), (self.superuser, list(OIT_ROLES)))
        [message] = list(get_messages(response.wsgi_request))
        self.assertEqual(message.level_tag, "success")
        self.assertIn("granted Mail.ReadWrite, Mail.Send", message.message)
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.config.pk)).exists())
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())

    def test_core_staff_may_check_but_others_may_not(self):
        self.client.force_login(make_admin(apps=["core"], email="core@example.com"))
        self.assertEqual(self.client.post(self.url).status_code, 302)
        MicrosoftGraphPermissionCheck.objects.all().delete()
        for apps in (("mail",), ()):
            with self.subTest(apps=apps):
                self.client.force_login(make_admin(apps=list(apps), email=f"s-{'-'.join(apps) or 'none'}@example.com"))
                self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertFalse(MicrosoftGraphPermissionCheck.objects.exists())

    def test_a_second_check_within_thirty_seconds_is_refused(self):
        self.client.post(self.url)

        response = self.client.post(self.url)

        self.assertEqual(MicrosoftGraphPermissionCheck.objects.count(), 1)
        [message] = list(get_messages(response.wsgi_request))[-1:]
        self.assertIn("wait", message.message)
        earlier = MicrosoftGraphPermissionCheck.objects.get().created_at - timedelta(seconds=31)
        MicrosoftGraphPermissionCheck.objects.update(created_at=earlier)
        self.client.post(self.url)
        self.assertEqual(MicrosoftGraphPermissionCheck.objects.count(), 2)

    def test_an_unknown_config_is_a_404(self):
        url = reverse(f"{PREFIX}_check_permissions", args=["00000000-0000-0000-0000-000000000000"])

        self.assertEqual(self.client.post(url).status_code, 404)

    def test_before_any_check_the_card_offers_the_button(self):
        card = self.card()

        self.assertIn("have not been checked", card)
        self.assertIn('id="graph-check-permissions"', card)
        self.assertIn("csrfmiddlewaretoken", card)
        self.assertIn(permissions.CAVEAT, card)

    def test_the_card_shows_the_roles_capabilities_and_trace_with_setup_steps(self):
        self.use_roles((*OIT_ROLES, "User.Read.All"))
        self.client.post(self.url)

        card = self.card()

        self.assertEqual(card.count('data-approved="yes"'), 2)
        self.assertIn("User.Read.All (beyond the approval)", card)
        self.assertIn(permissions.RECORD_REFERENCE_FIRST, card)
        self.assertEqual(card.count('data-granted="yes"'), 2)
        self.assertEqual(card.count('data-granted="no"'), 1)
        self.assertIn('data-trace="not_granted"', card)
        self.assertIn(permissions.TRACE_APP_ID, card)

    def test_an_available_trace_needs_no_setup_steps(self):
        self.use_roles((*OIT_ROLES, TRACE_ROLE))
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(permission_exception_reference="R1")
        self.client.post(self.url)

        card = self.card()

        self.assertIn('data-trace="available"', card)
        self.assertNotIn(permissions.TRACE_APP_ID, card)
        self.assertNotIn(permissions.RECORD_REFERENCE_FIRST, card)

    def test_a_token_failure_is_shown_as_an_error(self):
        self.microsoft.token = HttpResponse(401, {}, b'{"error": "invalid_client"}')

        response = self.client.post(self.url)

        [message] = list(get_messages(response.wsgi_request))
        self.assertEqual(message.level_tag, "error")
        self.assertIn("No token was issued", self.card())


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class TraceToggleWarningTests(TraceSetupMixin, TestCase):
    message_trace = False

    def setUp(self):
        super().setUp()
        self.client.force_login(make_superuser())
        self.change_url = reverse(f"{PREFIX}_change", args=[self.config.pk])

    def save(self, **values):
        response = self.client.post(self.change_url, change_data(self.config, **values), follow=True)
        return [message.message for message in response.context["messages"]]

    def check_with(self, roles):
        self.microsoft.token = token_response(token=token_with_roles(roles))
        permissions.run_and_record(self.config)

    def test_switching_it_on_without_a_check_or_the_role_warns_but_saves(self):
        self.assertTrue(any(NO_CHECK_YET in message for message in self.save(message_trace_enabled="on")))
        self.config.refresh_from_db()
        self.assertTrue(self.config.message_trace_enabled)
        self.check_with(OIT_ROLES)
        self.assertTrue(any(f"found no {TRACE_ROLE}" in message for message in self.save(message_trace_enabled="on")))

    def test_no_warning_once_the_role_is_in_the_token_or_while_it_is_off(self):
        self.assertFalse(any("Message Trace" in message for message in self.save()))
        self.check_with((*OIT_ROLES, TRACE_ROLE))
        self.assertFalse(any("Message Trace" in message for message in self.save(message_trace_enabled="on")))
