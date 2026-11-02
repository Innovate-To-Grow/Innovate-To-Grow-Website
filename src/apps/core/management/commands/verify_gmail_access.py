"""Check what Google lets the installed Gmail API key do, and record the evidence email needs to switch to it.

The run must show the pinned key readable and matching, a gmail.send token for every account on the allow-list, an
address off the list refused by the site (Google is never asked for it), and every broader scope refused by Google.
Checks 1-5 all passing write ``access_checked_at``; each token PASS writes that account's ``verified_at``. It runs
against the active config, or the newest one when none is active (to check a standby before go-live). Exits 1 on
any FAIL. The admin's "Run access check" does the same from the config page.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import GmailApiProviderConfig
from apps.core.services.email.gmail.access_check import FAIL, PASS, precondition_problem, run_access_check
from apps.core.services.email.gmail.access_check.report import DELEGATION_NOTE

NO_CONFIG = "No Gmail API provider config exists."
STYLES = {PASS: "SUCCESS", FAIL: "ERROR"}


class Command(BaseCommand):
    help = "Check the Gmail API key's delegation against the allow-list and gmail.send, and record the evidence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--deny-subject",
            default="",
            help="An address NOT on the allow-list that the site must refuse (default: a generated one on the From "
            "domain). Nothing is sent to Google for it.",
        )
        parser.add_argument("--no-send", action="store_true", help="Skip the probe emails.")
        parser.add_argument(
            "--skip-breadth",
            action="store_true",
            help="Skip the broader-scope checks. The run is then NOT A COMPLETE VALIDATION and records nothing.",
        )

    def handle(self, *args, **options):
        config = GmailApiProviderConfig.load()
        if config._state.adding:
            config = GmailApiProviderConfig.objects.order_by("-updated_at").first()
        if config is None:
            raise CommandError(NO_CONFIG)
        problem = precondition_problem(config)
        if problem:
            raise CommandError(problem)
        report = run_access_check(
            config,
            deny_subject=options["deny_subject"],
            send=not options["no_send"],
            breadth=not options["skip_breadth"],
        )
        self.stdout.write(f"Gmail API access check, {report.checked_at:%Y-%m-%d %H:%M:%S} UTC, config {config.name}")
        self.stdout.write(f"Service account {report.service_account_email}, client ID {report.client_id}")
        self.stdout.write(f"Key ID {report.key_id}, key version {report.key_version_id}")
        self.stdout.write("")
        for result in report.results:
            self.stdout.write(getattr(self.style, STYLES.get(result.outcome, "NOTICE"))(result.line()))
        self.stdout.write("")
        self.stdout.write(DELEGATION_NOTE)
        self.stdout.write(report.summary())
        self.stdout.write((self.style.ERROR if report.failed else self.style.SUCCESS)(report.conclusion()))
        if report.failed:
            raise CommandError(report.conclusion())
