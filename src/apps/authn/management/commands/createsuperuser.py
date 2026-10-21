"""
Custom createsuperuser command that prompts for email and creates a ContactEmail record.

Since Member has no username field (UUID is the primary key), this command
prompts for email + password and creates the superuser with a ContactEmail.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.authn.models import ContactEmail


class Command(BaseCommand):
    help = "Create a superuser with an email address and ContactEmail record."

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str, help="Email address for the superuser.")
        parser.add_argument("--password", type=str, help="Password for the superuser.")
        parser.add_argument("--first-name", type=str, default="", help="First name.")
        parser.add_argument("--last-name", type=str, default="", help="Last name.")
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="Non-interactive mode.",
        )

    def handle(self, *args, **options):
        Member = get_user_model()
        interactive = options.get("interactive", True)
        email = options.get("email")
        password = options.get("password")
        first_name = options.get("first_name") or ""
        last_name = options.get("last_name") or ""

        if interactive:
            email = email or self._prompt_email()
            password = password or self._prompt_password()
            first_name = self._prompt_name("First name", first_name)
            last_name = self._prompt_name("Last name", last_name)
        else:
            if not email or not password or not first_name.strip() or not last_name.strip():
                raise CommandError(
                    "--email, --password, --first-name, and --last-name are required in non-interactive mode."
                )
            if ContactEmail.objects.filter(email_address__iexact=email).exists():
                raise CommandError(f"A contact email with address '{email}' already exists.")

        member = Member.objects.create_superuser(
            password=password,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
        )

        ContactEmail.objects.create(
            member=member,
            email_address=email,
            email_type="primary",
            verified=True,
            subscribe=True,
        )

        self.stdout.write(self.style.SUCCESS(f"Superuser created with email '{email}' (UUID: {member.id})."))

    def _prompt_email(self) -> str:
        while True:
            email = input("Email address: ").strip()
            if not email:
                self.stderr.write("Error: Email address cannot be blank.")
            elif ContactEmail.objects.filter(email_address__iexact=email).exists():
                self.stderr.write(f"Error: A contact email with address '{email}' already exists.")
            else:
                return email

    def _prompt_password(self) -> str:
        import getpass

        while True:
            password = getpass.getpass("Password: ")
            password2 = getpass.getpass("Password (again): ")
            if password != password2:
                self.stderr.write("Error: Passwords do not match.")
            elif password:
                return password

    def _prompt_name(self, label: str, current: str) -> str:
        """Keep a name given on the command line; otherwise ask until one is entered."""
        name = current
        while not name.strip():
            name = input(f"{label}: ").strip()
            if not name:
                self.stderr.write(f"Error: {label} cannot be blank.")
        return name
