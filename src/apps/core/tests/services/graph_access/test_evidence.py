"""Recording an access-check run (``MicrosoftGraphAccessCheck``) and the checks that refuse to run at all."""

import json
import logging

from django.contrib.admin.models import LogEntry
from django.core import serializers
from django.db.models import ProtectedError
from django.test import TestCase

from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphCertificate
from apps.core.services.email.graph.access_check import precondition_problem, run_and_record
from apps.core.services.email.graph.access_check.runner import (
    DENY_MAILBOX_IN_USE,
    INVALID_DENY_MAILBOX,
    NO_DENY_MAILBOX,
    NOT_READY,
)
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import grant, private_key_lines
from apps.core.tests.services.graph_access.helpers import (
    DENY,
    EXTRA_ROLES,
    SCOPED,
    ProbeFixtureMixin,
    Verdict,
    token_with_roles,
)
from apps.event.tests.helpers import make_superuser

Source = MicrosoftGraphAccessCheck.Source
GUID_LIKE = "6233fba6-1111-2222-3333-444455556666"


class RecordAccessCheckTests(ProbeFixtureMixin, TestCase):
    def record(self, **kwargs):
        return run_and_record(self.config, deny_mailbox=DENY, source=Source.COMMAND, **kwargs)

    def test_a_run_is_stored_with_what_identifies_it(self):
        report, check = self.record()

        certificate = self.config.current_certificate
        self.assertEqual(MicrosoftGraphAccessCheck.objects.get(), check)
        self.assertEqual((check.config, check.certificate), (self.config, certificate))
        self.assertEqual(check.certificate_sha1, certificate.sha1_thumbprint)
        self.assertEqual((check.tenant_id, check.client_id), (self.config.tenant_id, self.config.client_id))
        self.assertEqual((check.deny_mailbox, check.source, check.run_by), (DENY, Source.COMMAND, None))
        self.assertEqual(check.granted_roles, ["Mail.ReadWrite", "Mail.Send"])
        self.assertEqual(check.approved_roles, ["Mail.Read", "Mail.ReadWrite", "Mail.Send"])
        self.assertTrue(check.mailbox_restriction_passed and check.complete and check.roles_within_approval)
        self.assertEqual(check.verdict, Verdict.COMPLIANT)
        self.assertEqual(check.results, [result.as_dict() for result in report.results])
        self.assertEqual(check.results[0]["check"], "token")

    def test_the_deny_mailbox_is_normalized(self):
        _report, check = run_and_record(self.config, deny_mailbox=f"  {DENY.upper()} ", source=Source.COMMAND)

        self.assertEqual(check.deny_mailbox, DENY)

    def test_roles_beyond_the_approval_are_recorded_as_not_compliant(self):
        self.use_roles(EXTRA_ROLES)

        _report, check = self.record()

        self.assertEqual(check.granted_roles, ["Mail.Send", "User.Read.All"])
        self.assertIs(check.roles_within_approval, False)
        self.assertTrue(check.mailbox_restriction_passed)
        self.assertEqual(check.verdict, Verdict.NOT_COMPLIANT)

    def test_an_admin_run_records_who_ran_it_in_the_row_and_the_config_history(self):
        admin = make_superuser(email="graph-check@example.com")

        _report, check = run_and_record(self.config, deny_mailbox=DENY, source=Source.ADMIN, run_by=admin)

        self.assertEqual((check.run_by, check.source), (admin, Source.ADMIN))
        entry = LogEntry.objects.get(object_id=str(self.config.pk))
        self.assertEqual(entry.user, admin)
        self.assertEqual(
            entry.change_message, f"Ran the Microsoft Graph access check against {DENY}: Matches the approval."
        )

    def test_neither_the_row_nor_the_logs_hold_the_token_or_the_key(self):
        token = token_with_roles()
        with self.assertLogs(level=logging.DEBUG) as logs:
            self.record()

        stored = serializers.serialize("json", MicrosoftGraphAccessCheck.objects.all())
        surfaces = [stored, *logs.output, json.dumps(list(LogEntry.objects.values_list("change_message", flat=True)))]
        secrets = [token, token.split(".")[1], *private_key_lines()[1:3]]
        for surface in surfaces:
            for secret in secrets:
                self.assertNotIn(secret, surface)
        self.assertTrue(any("graph_access_check verdict=compliant" in line for line in logs.output))

    def test_a_token_issued_with_a_certificate_installed_as_not_trusted_marks_it_trusted(self):
        certificate = self.config.current_certificate
        MicrosoftGraphCertificate.objects.filter(pk=certificate.pk).update(
            entra_check="not_trusted", entra_check_code="AADSTS700027"
        )

        report, _check = self.record()

        certificate.refresh_from_db()
        self.assertEqual((certificate.entra_check, certificate.entra_check_code), ("ok", ""))
        self.assertEqual(certificate.entra_checked_at, report.checked_at)

    def test_a_refused_token_leaves_the_entra_check_alone(self):
        certificate = self.config.current_certificate
        MicrosoftGraphCertificate.objects.filter(pk=certificate.pk).update(entra_check="not_trusted")
        self.probe.token = HttpResponse(401, {}, json.dumps({"error": "invalid_client"}).encode())

        _report, check = self.record()

        certificate.refresh_from_db()
        self.assertEqual(certificate.entra_check, "not_trusted")
        self.assertNotEqual(check.verdict, Verdict.COMPLIANT)

    def test_a_config_with_recorded_checks_cannot_be_deleted(self):
        self.record()
        self.config.is_active = False
        self.config.save()

        with self.assertRaises(ProtectedError):
            self.config.delete()

        self.assertEqual(MicrosoftGraphAccessCheck.objects.filter(config=self.config).count(), 1)

    def test_a_removed_certificate_keeps_its_evidence_rows(self):
        _report, check = self.record()

        MicrosoftGraphCertificate.objects.filter(pk=check.certificate_id).update(state="removed")
        check.refresh_from_db()

        self.assertIsNotNone(check.certificate)


class PreconditionTests(ProbeFixtureMixin, TestCase):
    def test_a_ready_config_and_an_outside_mailbox_can_be_checked(self):
        self.assertEqual(precondition_problem(self.config, DENY), "")

    def test_the_deny_mailbox_must_be_set_and_plain(self):
        for value, problem in (("", NO_DENY_MAILBOX), ("not a mailbox", INVALID_DENY_MAILBOX)):
            with self.subTest(value=value):
                self.assertEqual(precondition_problem(self.config, value), problem)
        for value in ("a/b@contoso.com", "x?y@contoso.com", "x#y@contoso.com", "x%2f@contoso.com", GUID_LIKE):
            with self.subTest(value=value):
                self.assertEqual(precondition_problem(self.config, value), INVALID_DENY_MAILBOX)

    def test_the_deny_mailbox_must_be_outside_the_scope_and_not_a_sender(self):
        grant(self.config, "shared@contoso.com")
        for value in (SCOPED.upper(), "shared@contoso.com"):
            with self.subTest(value=value):
                self.assertEqual(precondition_problem(self.config, value), DENY_MAILBOX_IN_USE)

    def test_a_config_without_a_usable_certificate_or_scope_is_not_ready(self):
        self.config.mailbox_scopes.all().delete()
        self.assertEqual(precondition_problem(self.config, DENY), NOT_READY)
        grant(self.config, SCOPED)
        self.config.certificates.update(state="removed")
        self.assertEqual(precondition_problem(self.config, DENY), NOT_READY)
