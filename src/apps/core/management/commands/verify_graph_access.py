"""Validate the Microsoft Graph access of the active config against Microsoft itself, and record the evidence.

The run must show every scoped mailbox allowed (per its permission level), the deny mailbox refused for reading,
for sending as it and as the From of a scoped mailbox's mail, and the token's application roles within
``GRAPH_APPROVED_APPLICATION_ROLES`` (or an InfoSec exception recorded). Skipped or inconclusive checks make it NOT
A COMPLETE VALIDATION. Exits 1 unless the run matches the approval. Every run is stored as a
``MicrosoftGraphAccessCheck`` row; the admin's "Run access check" does the same from the Graph config page.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph_access_check import go_live_problem
from apps.core.services.email.graph.access_check import FAIL, PASS, WARN, precondition_problem, run_and_record

NOT_CONFIGURED = "No active, fully configured Microsoft Graph provider config (with a mailbox scope)."
PROPAGATION_NOTE = (
    "Microsoft notes that changes to an access policy can take more than an hour to apply: after OIT changes "
    "anything, wait before running this again."
)
NOT_DESIGNATED = " (not the designated Access Check Deny Mailbox: this run does not count for the go-live gate)"
# Outcome -> ``self.style`` attribute; SKIP and INCONCLUSIVE use NOTICE.
STYLES = {PASS: "SUCCESS", FAIL: "ERROR", WARN: "WARNING"}


class Command(BaseCommand):
    help = "Check what Microsoft lets the Graph app do against the approval, and record the result as evidence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--deny-mailbox",
            default="",
            help=(
                "An existing mailbox OUTSIDE the scope whose access must be refused. Defaults to the config's "
                "designated Access Check Deny Mailbox; the go-live gate accepts only runs against that one."
            ),
        )
        parser.add_argument(
            "--no-send",
            action="store_true",
            help="Skip the send probes. The run is then NOT A COMPLETE VALIDATION.",
        )

    def handle(self, *args, **options):
        config = MicrosoftGraphProviderConfig.load()
        if not config.is_configured:
            raise CommandError(NOT_CONFIGURED)
        deny_mailbox = options["deny_mailbox"] or config.access_check_deny_mailbox
        problem = precondition_problem(config, deny_mailbox)
        if problem:
            raise CommandError(problem)
        report, check = run_and_record(
            config,
            deny_mailbox=deny_mailbox,
            source=MicrosoftGraphAccessCheck.Source.COMMAND,
            send=not options["no_send"],
        )
        self._write_header(report, designated=report.deny_mailbox == config.access_check_deny_mailbox)
        for result in report.results:
            self.stdout.write(getattr(self.style, STYLES.get(result.outcome, "NOTICE"))(self._line(result)))
        self.stdout.write("")
        self.stdout.write(report.summary())
        self.stdout.write(PROPAGATION_NOTE)
        compliant = check.verdict == MicrosoftGraphAccessCheck.Verdict.COMPLIANT
        self.stdout.write((self.style.SUCCESS if compliant else self.style.ERROR)(report.conclusion()))
        self.stdout.write(f"Recorded as access check {check.pk}.")
        gate = go_live_problem(config)
        self.stdout.write(f"Go-live evidence: {'present' if not gate else 'missing: ' + gate}")
        if not compliant:
            raise CommandError(report.conclusion())

    def _write_header(self, report, *, designated: bool) -> None:
        self.stdout.write(f"Microsoft Graph access check, {report.checked_at:%Y-%m-%d %H:%M:%S} UTC")
        self.stdout.write(f"Entra app: tenant {report.tenant_id}, client {report.client_id}")
        self.stdout.write(
            f"Authentication: certificate only; SHA-1 {report.certificate_sha1}, key version {report.key_version_id}"
        )
        self.stdout.write(f"Deny mailbox: {report.deny_mailbox}{'' if designated else NOT_DESIGNATED}")
        self.stdout.write(f"Approved application roles: {', '.join(report.approved_roles)}")
        broader = ", ".join(report.broader_roles) or "none"
        self.stdout.write(f"Accepted broader roles (no InfoSec exception needed): {broader}")
        self.stdout.write(f"InfoSec exception: {report.exception_reference or 'none recorded'}")
        self.stdout.write("")

    @staticmethod
    def _line(result) -> str:
        status = result.status if result.status is not None else "-"
        line = (
            f"{result.outcome:<12} {result.check:<6} {result.mailbox:<40} expected {result.expected:<14} got {status}"
        )
        line = f"{line} {result.code}".rstrip()
        if result.request_id:
            line = f"{line} [request-id {result.request_id}]"
        return f"{line}  ({result.note})" if result.note else line
