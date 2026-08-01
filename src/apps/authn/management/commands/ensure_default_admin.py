"""Create a default Django admin account once, without repairing existing users."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.authn.models import ContactEmail

DEFAULT_FIRST_NAME = "Demo"
DEFAULT_LAST_NAME = "Admin"


class Command(BaseCommand):
    help = "Create a default superuser identified by email if it does not already exist."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirm that this command may mutate admin users.")
        parser.add_argument("--email", default=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""))
        parser.add_argument("--password-env", default="DJANGO_SUPERUSER_PASSWORD")
        parser.add_argument(
            "--first-name",
            default=os.environ.get("DJANGO_SUPERUSER_FIRST_NAME", DEFAULT_FIRST_NAME),
        )
        parser.add_argument(
            "--last-name",
            default=os.environ.get("DJANGO_SUPERUSER_LAST_NAME", DEFAULT_LAST_NAME),
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("Refusing to mutate admin users without --yes.")

        email = (options["email"] or "").strip().lower()
        password_env = (options["password_env"] or "").strip()
        first_name = (options["first_name"] or DEFAULT_FIRST_NAME).strip() or DEFAULT_FIRST_NAME
        last_name = (options["last_name"] or DEFAULT_LAST_NAME).strip() or DEFAULT_LAST_NAME

        if not email:
            raise CommandError("--email or DJANGO_SUPERUSER_EMAIL is required.")
        if not password_env:
            raise CommandError("--password-env is required.")

        with transaction.atomic():
            # Only the contact row needs locking. Joining the nullable member
            # relation makes PostgreSQL reject FOR UPDATE on the outer join.
            contact = ContactEmail.objects.select_for_update().filter(email_address__iexact=email).first()
            if contact is not None:
                self.stdout.write(
                    self.style.WARNING(
                        f"Default admin already exists; left unchanged: email={email}, member={contact.member_id}"
                    )
                )
                return

            password = os.environ.get(password_env, "")
            if not password:
                raise CommandError(f"{password_env} must be set.")

            member = self._create_member(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

        self.stdout.write(self.style.SUCCESS(f"Default admin created: email={email}, member={member.pk}"))

    def _create_member(self, *, email: str, password: str, first_name: str, last_name: str):
        Member = get_user_model()
        member = Member.objects.create_user(
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )
        ContactEmail.objects.create(
            member=member,
            email_address=email,
            email_type="primary",
            verified=True,
            subscribe=True,
        )
        return member
