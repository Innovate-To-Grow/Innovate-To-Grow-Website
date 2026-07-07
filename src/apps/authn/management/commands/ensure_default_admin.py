"""Ensure an idempotent default Django admin account exists."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.authn.models import ContactEmail

DEFAULT_FIRST_NAME = "Demo"
DEFAULT_LAST_NAME = "Admin"


class Command(BaseCommand):
    help = "Create or update a default superuser identified by email."

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
        password = os.environ.get(password_env, "")
        first_name = (options["first_name"] or DEFAULT_FIRST_NAME).strip() or DEFAULT_FIRST_NAME
        last_name = (options["last_name"] or DEFAULT_LAST_NAME).strip() or DEFAULT_LAST_NAME

        if not email:
            raise CommandError("--email or DJANGO_SUPERUSER_EMAIL is required.")
        if not password_env:
            raise CommandError("--password-env is required.")
        if not password:
            raise CommandError(f"{password_env} must be set.")

        with transaction.atomic():
            member, created = self._ensure_member(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Default admin {action}: email={email}, member={member.pk}"))

    def _ensure_member(self, *, email: str, password: str, first_name: str, last_name: str):
        Member = get_user_model()
        contact = ContactEmail.objects.select_related("member").filter(email_address__iexact=email).first()
        member = contact.member if contact else None
        created = member is None

        if member is None:
            member = Member.objects.create_user(
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
                is_staff=True,
                is_superuser=True,
            )
        else:
            member.first_name = first_name
            member.last_name = last_name
            member.is_active = True
            member.is_staff = True
            member.is_superuser = True
            member.set_password(password)
            member.save(update_fields=["first_name", "last_name", "is_active", "is_staff", "is_superuser", "password"])

        if contact is None:
            contact = ContactEmail.objects.create(
                member=member,
                email_address=email,
                email_type="primary",
                verified=True,
                subscribe=True,
            )
        else:
            contact.member = member
            contact.email_address = email
            contact.email_type = "primary"
            contact.verified = True
            contact.subscribe = True
            contact.save(update_fields=["member", "email_address", "email_type", "verified", "subscribe"])

        ContactEmail.objects.filter(member=member, email_type="primary").exclude(pk=contact.pk).update(
            email_type="secondary"
        )
        return member, created
