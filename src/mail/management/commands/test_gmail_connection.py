"""
Management command to test Gmail API connectivity.

Usage:
    python manage.py test_gmail_connection
"""

from django.core.management.base import BaseCommand, CommandError

from mail.models import GoogleAccount
from mail.services.gmail import GmailService, GmailServiceError


class Command(BaseCommand):
    help = "Test Gmail API connection using the active GoogleAccount"

    # noinspection PyUnusedLocal
    def handle(self, *args, **options):
        account = GoogleAccount.get_active()
        if not account:
            raise CommandError("No active GoogleAccount found. Add one in Django admin first.")

        self.stdout.write(f"Testing connection for: {account.email}")

        try:
            service = GmailService(account)
            profile = service.test_connection()
        except GmailServiceError as exc:
            account.mark_used(error=str(exc))
            raise CommandError(f"Connection FAILED: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Connection successful!"))
        self.stdout.write(f"  Email: {profile['email']}")
        self.stdout.write(f"  Total messages: {profile['messages_total']}")
        self.stdout.write(f"  Total threads: {profile['threads_total']}")

        # List 5 most recent subjects
        self.stdout.write("\nMost recent emails:")
        try:
            result = service.list_messages(max_results=5)
            for msg in result["messages"]:
                unread = " [UNREAD]" if msg["is_unread"] else ""
                self.stdout.write(f"  - {msg['subject'] or '(no subject)'}{unread}")
        except GmailServiceError as exc:
            self.stdout.write(self.style.WARNING(f"  Could not list messages: {exc}"))

        account.mark_used()
        self.stdout.write(self.style.SUCCESS("\nDone."))
