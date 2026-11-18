"""Validate the Microsoft Graph access of the active config against Microsoft itself, and record the evidence.

The run must show every scoped mailbox allowed (per its permission level), the deny mailbox refused for reading,
for sending as it and as the From of a scoped mailbox's mail, and the token's application roles within
``GRAPH_APPROVED_APPLICATION_ROLES`` (or an InfoSec exception recorded). Skipped or inconclusive checks make it NOT
A COMPLETE VALIDATION. Exits 1 unless the run matches the approval. Every run is stored as a
``MicrosoftGraphAccessCheck`` row; the admin's "Run access check" does the same from the Graph config page.

``--permissions-only`` runs the read-only permission check instead (the admin's "Check permissions"): the token's
roles, the capability table and the Message Trace probe, recorded as a ``MicrosoftGraphPermissionCheck``. It sends no
mail, needs no deny mailbox, is never go-live evidence and exits 1 only when no token is issued.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph.access_check import go_live_problem
from apps.core.services.email.graph.access_check import (
    FAIL,
    PASS,
    WARN,
    permissions,
    precondition_problem,
    run_and_record,
)

NO_CONFIG = "No active Microsoft Graph provider config."
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
        parser.add_argument(
            "--permissions-only",
            action="store_true",
            help="Only list the token's roles, what they allow and the Message Trace probe; sends no mail.",
        )

    def handle(self, *args, **options):
        config = MicrosoftGraphProviderConfig.load()
        if options["permissions_only"]:
            return self._permissions(config)
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

    def _permissions(self, config) -> None:
        if config._state.adding:
            raise CommandError(NO_CONFIG)
        report, check = permissions.run_and_record(config)
        self.stdout.write(f"Microsoft Graph permission check, {report.checked_at:%Y-%m-%d %H:%M:%S} UTC")
        self.stdout.write(f"Certificate: SHA-1 {report.certificate_sha1 or 'none installed'}")
        if not report.token_ok:
            self.stdout.write(self.style.ERROR(f"Token: NOT ISSUED ({report.token_error})"))
            raise CommandError(report.summary())
        self.stdout.write(self.style.SUCCESS("Token: issued with the current certificate"))
        if report.granted_roles is None:
            self.stdout.write(self.style.WARNING("Granted application roles: could not be read"))
        else:
            self.stdout.write(f"Granted application roles:{'' if report.granted_roles else ' none in the token'}")
        for role in report.granted_roles or ():
            beyond = role in report.extra_roles
            line = f"  {role:<40} {'BEYOND the approval' if beyond else 'approved'}"
            self.stdout.write(self.style.WARNING(line) if beyond else line)
        if report.warning:
            self.stdout.write(self.style.WARNING(report.warning))
        self.stdout.write("Capabilities:")
        for row in report.capabilities:
            mark = {True: "yes", False: "no", None: "?"}[row.granted]
            self.stdout.write(f"  [{mark:>3}] {row.feature} ({' or '.join(row.permissions)})")
        self.stdout.write(f"Message Trace: {check.get_trace_result_display()}. {report.trace_note}")
        self.stdout.write(permissions.CAVEAT)
        self.stdout.write(f"Recorded as permission check {check.pk}.")

    def _write_header(self, report, *, designated: bool) -> None:
        self.stdout.write(f"Microsoft Graph access check, {report.checked_at:%Y-%m-%d %H:%M:%S} UTC")
        self.stdout.write(f"Entra app: tenant {report.tenant_id}, client {report.client_id}")
        self.stdout.write(
            f"Authentication: certificate only; SHA-1 {report.certificate_sha1}, key version {report.key_version_id}"
        )
        self.stdout.write(f"Deny mailbox: {report.deny_mailbox}{'' if designated else NOT_DESIGNATED}")
        self.stdout.write(f"Approved application roles: {', '.join(report.approved_roles)}")
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
