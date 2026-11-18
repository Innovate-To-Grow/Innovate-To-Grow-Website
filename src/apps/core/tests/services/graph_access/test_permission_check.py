"""The Graph permission check: a fresh token, its roles classified against the approval, the capability table and
token failures. The Message Trace probe and the recorded rows are in ``test_permission_trace_probe``."""

from django.test import TestCase

from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.access_check import permissions
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.graph.tracing import TRACE_ROLE, TraceSetupMixin, token_response, token_with_roles

Trace = permissions.Trace
OIT_ROLES = ("Mail.ReadWrite", "Mail.Send")


class PermissionCheckFixture(TraceSetupMixin, TestCase):
    message_trace = False

    def use_roles(self, roles):
        self.microsoft.token = token_response(token=token_with_roles(roles))

    def check(self):
        self.config.refresh_from_db()
        return permissions.check_permissions(self.config)


class RoleClassificationTests(PermissionCheckFixture):
    def test_todays_roles_are_approved_and_message_trace_is_not_granted_without_a_request(self):
        self.use_roles(OIT_ROLES)

        report = self.check()

        self.assertTrue(report.token_ok)
        self.assertEqual(report.granted_roles, OIT_ROLES)
        self.assertEqual((report.extra_roles, report.warning), ((), ""))
        self.assertEqual(report.trace_result, Trace.NOT_GRANTED)
        self.assertEqual(self.microsoft.traces, [])
        self.assertEqual(report.certificate_sha1, self.config.current_certificate.sha1_thumbprint)
        self.assertIn("Message Trace: not granted (not probed)", report.summary())

    def test_a_role_beyond_the_approval_warns_to_record_the_reference_first(self):
        self.use_roles((*OIT_ROLES, "User.Read.All"))

        report = self.check()

        self.assertEqual(report.extra_roles, ("User.Read.All",))
        self.assertEqual(report.warning, permissions.RECORD_REFERENCE_FIRST)
        self.assertIn("beyond the approval: User.Read.All", report.summary())

    def test_with_the_infosec_reference_recorded_the_extra_role_needs_no_warning(self):
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(
            permission_exception_reference="RITM0450999"
        )
        self.use_roles((*OIT_ROLES, "User.Read.All"))

        report = self.check()

        self.assertEqual((report.extra_roles, report.warning), (("User.Read.All",), ""))

    def test_the_cached_token_is_not_reused(self):
        self.use_roles(OIT_ROLES)
        self.check()
        self.use_roles((*OIT_ROLES, TRACE_ROLE))

        report = self.check()

        self.assertIn(TRACE_ROLE, report.granted_roles)
        self.assertEqual(self.microsoft.tokens, 2)


class CapabilityTableTests(PermissionCheckFixture):
    def table(self, granted):
        return [(row.feature, row.granted) for row in permissions.capabilities(granted)]

    def test_each_feature_shows_whether_its_permission_is_in_the_token(self):
        send, read, trace = (feature for feature, _needs in permissions.GRAPH_FEATURE_PERMISSIONS)
        self.assertEqual(self.table(OIT_ROLES), [(send, True), (read, True), (trace, False)])
        self.assertEqual(self.table(("Mail.Read",)), [(send, False), (read, True), (trace, False)])
        self.assertEqual(self.table(("Mail.Send", TRACE_ROLE)), [(send, True), (read, False), (trace, True)])
        self.assertEqual(self.table(()), [(send, False), (read, False), (trace, False)])
        self.assertEqual(self.table(None), [(send, None), (read, None), (trace, None)])

    def test_the_report_carries_the_table_of_its_roles(self):
        self.use_roles(("Mail.Send",))

        report = self.check()

        self.assertEqual([row.granted for row in report.capabilities], [True, False, False])

    def test_unreadable_roles_are_reported_as_such(self):
        self.microsoft.token = token_response(token="not-a-jwt")

        report = self.check()

        self.assertTrue(report.token_ok)
        self.assertIsNone(report.granted_roles)
        self.assertEqual(report.extra_roles, ())
        self.assertIn("could not be read", report.summary())
        self.assertEqual(self.microsoft.traces, [])


class TokenFailureTests(PermissionCheckFixture):
    def test_a_refused_token_is_reported_with_its_message_and_nothing_is_probed(self):
        self.microsoft.token = HttpResponse(401, {}, b'{"error": "invalid_client"}')
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(message_trace_enabled=True)

        report = self.check()

        self.assertFalse(report.token_ok)
        self.assertTrue(report.token_error)
        self.assertIsNone(report.granted_roles)
        self.assertEqual(report.trace_result, Trace.NOT_CHECKED)
        self.assertEqual(self.microsoft.traces, [])
        self.assertTrue(report.summary().startswith("No token was issued: "))

    def test_without_a_usable_certificate_no_token_is_requested(self):
        self.config.certificates.update(state=MicrosoftGraphCertificate.State.REMOVED)

        report = self.check()

        self.assertFalse(report.token_ok)
        self.assertIn("No usable Microsoft Graph certificate", report.token_error)
        self.assertEqual(report.certificate_sha1, "")
        self.assertEqual(self.microsoft.requests, [])
