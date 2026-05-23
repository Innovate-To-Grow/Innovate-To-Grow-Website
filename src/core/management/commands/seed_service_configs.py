"""Seed skeleton service configs and ensure staff members have verified ContactEmails.

Service credentials (SES, SMS, Sheets) are managed via Django admin → Site Settings.
This command creates empty active rows so the admin UI has something to edit; it
no longer reads provider-specific env vars. AWSCredentialConfig is still seeded
from AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY when those are set locally.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authn.models import ContactEmail
from core.models import AWSCredentialConfig, EmailServiceConfig, SMSServiceConfig

Member = get_user_model()


class Command(BaseCommand):
    help = "Create skeleton EmailServiceConfig/SMSServiceConfig rows and ensure staff ContactEmails."

    def handle(self, *args, **options):
        self._seed_email()
        self._seed_sms()
        self._seed_aws()
        self._seed_staff_contact_emails()

    def _seed_email(self):
        if EmailServiceConfig.objects.exists():
            self.stdout.write(self.style.WARNING("EmailServiceConfig already exists — skipping."))
            return

        EmailServiceConfig.objects.create(name="Production", is_active=True)
        self.stdout.write(
            self.style.SUCCESS(
                "Created skeleton active EmailServiceConfig 'Production'. "
                "Fill in SES or SMTP credentials in Django admin."
            )
        )

    def _seed_sms(self):
        if SMSServiceConfig.objects.exists():
            self.stdout.write(self.style.WARNING("SMSServiceConfig already exists — skipping."))
            return

        SMSServiceConfig.objects.create(name="Production", is_active=True)
        self.stdout.write(
            self.style.SUCCESS(
                "Created skeleton active SMSServiceConfig 'Production'. "
                "Set the SNS origination number in Django admin."
            )
        )

    def _seed_aws(self):
        if AWSCredentialConfig.objects.exists():
            self.stdout.write(self.style.WARNING("AWSCredentialConfig already exists — skipping."))
            return

        access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        if not access_key and not secret_key:
            self.stdout.write(self.style.WARNING("AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set — skipping."))
            return

        AWSCredentialConfig.objects.create(
            name="Production",
            is_active=True,
            access_key_id=access_key,
            secret_access_key=secret_key,
            default_region=os.environ.get("AWS_DEFAULT_REGION", "us-west-2"),
        )
        self.stdout.write(self.style.SUCCESS("Created active AWSCredentialConfig 'Production'."))

    def _seed_staff_contact_emails(self):
        """Ensure every staff member has a verified primary ContactEmail so admin login works."""
        for member in Member.objects.filter(is_staff=True, is_active=True):
            primary_email = member.get_primary_email()
            if not primary_email:
                continue
            _, created = ContactEmail.objects.get_or_create(
                email_address=primary_email,
                defaults={
                    "member": member,
                    "email_type": "primary",
                    "verified": True,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created verified ContactEmail for staff '{primary_email}'."))
            else:
                self.stdout.write(self.style.WARNING(f"ContactEmail already exists for '{primary_email}' — skipping."))
