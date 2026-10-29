"""Validate the Microsoft Graph mailbox restriction against Microsoft itself.

Expected result: every mailbox in the active config's scope is allowed (read and/or send, per its permission level)
and the --deny-mailbox is refused with 403 for both reading and sending. Exits 1 when any check does not match.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph import normalize_mailbox
from apps.core.services.email.graph.access_check import run_access_check
from apps.core.utils.security import is_exchange_mailbox


class Command(BaseCommand):
    help = "Check that Microsoft Graph reaches the scoped mailboxes and is denied for an unrelated mailbox."

    def add_arguments(self, parser):
        parser.add_argument(
            "--deny-mailbox",
            required=True,
            help="An existing mailbox OUTSIDE the scope (for example a test mailbox). Access to it must be denied.",
        )
        parser.add_argument(
            "--no-send",
            action="store_true",
            help="Skip the send probes (they email the scoped mailbox itself).",
        )

    def handle(self, *args, **options):
        config = MicrosoftGraphProviderConfig.load()
        if not config.is_configured:
            raise CommandError("No active, fully configured Microsoft Graph provider config (with a mailbox scope).")
        deny_mailbox = normalize_mailbox(options["deny_mailbox"])
        if not is_exchange_mailbox(deny_mailbox):
            raise CommandError("--deny-mailbox must be a mailbox address or object ID.")
        if config.mailbox_scopes.filter(mailbox=deny_mailbox).exists():
            raise CommandError("--deny-mailbox is inside the configured scope; choose a mailbox outside it.")

        results = run_access_check(config, deny_mailbox=deny_mailbox, send=not options["no_send"])
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            style = self.style.SUCCESS if result.passed else self.style.ERROR
            line = (
                f"{status}  {result.check:<5} {result.mailbox:<40} expected {result.expected:<13} "
                f"got {result.status if result.status is not None else '-'} {result.code}".rstrip()
            )
            self.stdout.write(style(line + (f"  ({result.note})" if result.note else "")))
        if not all(result.passed for result in results):
            raise CommandError("Microsoft Graph access does not match the approved scope.")
        self.stdout.write(self.style.SUCCESS("Microsoft Graph access matches the approved mailbox scope."))
