"""The permission check's live Message Trace probe (200 / 401 / 403 / 429 / other), when it runs, and the recorded
``MicrosoftGraphPermissionCheck`` rows: never an access check, the go-live gate untouched, the latest 20 kept."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from apps.core.models import (
    EmailDeliveryTraceState,
    EmailServiceConfig,
    MicrosoftGraphAccessCheck,
    MicrosoftGraphPermissionCheck,
    MicrosoftGraphProviderConfig,
)
from apps.core.models.base.service_credentials.microsoft_graph import go_live_problem
from apps.core.services.email.graph.access_check import permissions
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.graph.tracing import PRIVATE, SENDER, TRACE_ROLE, trace_page, trace_row
from apps.core.tests.services.graph_access.test_permission_check import OIT_ROLES, PermissionCheckFixture, Trace

DENY = "deny-test@ucmerced.edu"


class TraceProbeTests(PermissionCheckFixture):
    def setUp(self):
        super().setUp()
        self.use_roles((*OIT_ROLES, TRACE_ROLE))

    def test_with_the_role_one_small_query_for_the_from_address_shows_it_available(self):
        self.microsoft.pages = [trace_page([trace_row()])]

        with self.assertLogs("apps.core.services.email.graph", "INFO") as logs:
            report, _check = permissions.run_and_record(self.config)

        self.assertEqual(report.trace_result, Trace.AVAILABLE)
        [request] = self.microsoft.traces
        self.assertEqual(request["method"], "GET")
        self.assertIn("senderAddress%20eq%20%27i2g%40ucmerced.edu%27", request["path"])
        self.assertTrue(request["path"].endswith("&$top=1"))
        for value in (*PRIVATE, SENDER):
            self.assertNotIn(value, "\n".join(logs.output))

    def test_microsofts_answers_map_to_what_staff_must_do(self):
        cases = {
            401: Trace.NO_SERVICE_PRINCIPAL,
            403: Trace.NOT_CONSENTED,
            429: Trace.THROTTLED,
            503: Trace.THROTTLED,
            500: Trace.ERROR,
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                self.microsoft.pages = [trace_page(status=status, body=b"{}")]

                report = self.check()

                self.assertEqual(report.trace_result, expected)
                self.assertTrue(report.trace_note)
        self.assertIn(permissions.TRACE_APP_ID, permissions.TRACE_NOTES[Trace.NO_SERVICE_PRINCIPAL])

    def test_with_the_toggle_on_it_probes_even_without_the_role(self):
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(message_trace_enabled=True)
        self.use_roles(OIT_ROLES)
        self.microsoft.pages = [trace_page(status=403, body=b"{}")]

        report = self.check()

        self.assertEqual(report.trace_result, Trace.NOT_CONSENTED)
        self.assertEqual(len(self.microsoft.traces), 1)

    def test_a_from_address_outside_the_send_scope_is_not_probed(self):
        EmailServiceConfig.objects.update(from_email="someone-else@ucmerced.edu")

        report = self.check()

        self.assertEqual((report.trace_result, report.trace_note), (Trace.ERROR, permissions.NO_SENDER))
        self.assertEqual(self.microsoft.traces, [])

    def test_an_available_trace_ends_the_syncs_not_permitted_backoff(self):
        later = timezone.now() + timedelta(hours=5)
        Permission = EmailDeliveryTraceState.Permission
        EmailDeliveryTraceState.objects.create(sender=SENDER, permission=Permission.NOT_PERMITTED, next_run_after=later)

        self.check()

        state = EmailDeliveryTraceState.objects.get(sender=SENDER)
        self.assertEqual((state.permission, state.next_run_after), (Permission.UNKNOWN, None))

    def test_a_refused_trace_keeps_the_backoff(self):
        later = timezone.now() + timedelta(hours=5)
        Permission = EmailDeliveryTraceState.Permission
        EmailDeliveryTraceState.objects.create(sender=SENDER, permission=Permission.NOT_PERMITTED, next_run_after=later)
        self.microsoft.pages = [trace_page(status=403, body=b"{}")]

        self.check()

        self.assertEqual(EmailDeliveryTraceState.objects.get(sender=SENDER).next_run_after, later)


class RecordTests(PermissionCheckFixture):
    def test_a_run_is_recorded_without_touching_the_access_checks(self):
        self.use_roles((*OIT_ROLES, TRACE_ROLE))

        report, check = permissions.run_and_record(self.config)

        self.assertEqual(MicrosoftGraphPermissionCheck.objects.get(), check)
        self.assertEqual(check.granted_roles, sorted((*OIT_ROLES, TRACE_ROLE)))
        self.assertEqual(check.extra_roles, [TRACE_ROLE])
        self.assertEqual((check.token_ok, check.trace_result), (True, Trace.AVAILABLE))
        self.assertEqual(check.certificate_sha1, report.certificate_sha1)
        self.assertIsNone(check.checked_by)
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_a_new_role_before_the_reference_never_withdraws_the_go_live_evidence(self):
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(access_check_deny_mailbox=DENY)
        self.config.refresh_from_db()
        MicrosoftGraphAccessCheck.objects.create(
            config=self.config,
            certificate=self.config.current_certificate,
            certificate_sha1=self.config.current_certificate.sha1_thumbprint,
            tenant_id=self.config.tenant_id,
            client_id=self.config.client_id,
            deny_mailbox=DENY,
            source="command",
            granted_roles=list(OIT_ROLES),
            verdict=MicrosoftGraphAccessCheck.Verdict.COMPLIANT,
        )
        self.assertEqual(go_live_problem(self.config), "")
        self.use_roles((*OIT_ROLES, TRACE_ROLE))

        report, _check = permissions.run_and_record(self.config)

        self.assertEqual(report.warning, permissions.RECORD_REFERENCE_FIRST)
        self.assertEqual(MicrosoftGraphAccessCheck.objects.count(), 1)
        self.assertEqual(go_live_problem(self.config), "")

    def test_a_failed_token_is_recorded_too(self):
        self.microsoft.token = HttpResponse(401, {}, b'{"error": "invalid_client"}')

        _report, check = permissions.run_and_record(self.config)

        self.assertEqual((check.token_ok, check.trace_result, check.granted_roles), (False, Trace.NOT_CHECKED, None))
        self.assertTrue(check.token_error)

    def test_only_the_latest_twenty_runs_of_a_config_are_kept(self):
        old = timezone.now() - timedelta(days=1)
        for minutes in range(MicrosoftGraphPermissionCheck.RETAINED):
            row = MicrosoftGraphPermissionCheck.objects.create(config=self.config)
            MicrosoftGraphPermissionCheck.objects.filter(pk=row.pk).update(created_at=old + timedelta(minutes=minutes))
        oldest = MicrosoftGraphPermissionCheck.objects.order_by("created_at").first()

        _report, check = permissions.run_and_record(self.config)

        rows = MicrosoftGraphPermissionCheck.objects.filter(config=self.config)
        self.assertEqual(rows.count(), MicrosoftGraphPermissionCheck.RETAINED)
        self.assertTrue(rows.filter(pk=check.pk).exists())
        self.assertFalse(rows.filter(pk=oldest.pk).exists())
