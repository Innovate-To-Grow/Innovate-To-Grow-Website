"""Seed EmailServiceConfig, SMSServiceConfig, and staff ContactEmails from environment variables."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from authn.models import ContactEmail
from core.models import EmailServiceConfig, SMSServiceConfig

Member = get_user_model()


class Command(BaseCommand):
    help = "Create initial service configs from .env and ensure staff members have verified ContactEmails"

    def handle(self, *args, **options):
        self._seed_email()
        self._seed_sms()
        self._seed_staff_contact_emails()

    def _seed_email(self):
        if EmailServiceConfig.objects.exists():
            self.stdout.write(self.style.WARNING("EmailServiceConfig already exists — skipping."))
            return

        EmailServiceConfig.objects.create(
            name="Production",
            is_active=True,
            ses_access_key_id=os.environ.get("SES_AWS_ACCESS_KEY_ID", ""),
            ses_secret_access_key=os.environ.get("SES_AWS_SECRET_ACCESS_KEY", ""),
            ses_region=os.environ.get("SES_AWS_REGION", "us-west-2"),
            ses_from_email=os.environ.get("SES_FROM_EMAIL", "i2g@g.ucmerced.edu"),
            ses_from_name=os.environ.get("SES_FROM_NAME", "Innovate to Grow"),
            smtp_host=os.environ.get("MAIL_SERVER", "smtp.gmail.com"),
            smtp_port=587,
            smtp_use_tls=True,
            smtp_username=os.environ.get("MAIL_USERNAME", ""),
            smtp_password=os.environ.get("MAIL_PASSWORD", ""),
        )
        self.stdout.write(self.style.SUCCESS("Created active EmailServiceConfig 'Production'."))

    def _seed_sms(self):
        if SMSServiceConfig.objects.exists():
            self.stdout.write(self.style.WARNING("SMSServiceConfig already exists — skipping."))
            return

        SMSServiceConfig.objects.create(
            name="Production",
            is_active=True,
            account_sid=os.environ.get("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.environ.get("TWILIO_AUTH_TOKEN", ""),
            verify_sid=os.environ.get("TWILIO_VERIFY_SID", ""),
        )
        self.stdout.write(self.style.SUCCESS("Created active SMSServiceConfig 'Production'."))

    def _seed_staff_contact_emails(self):
        """Ensure every staff member has a verified primary ContactEmail so admin login works."""
        for member in Member.objects.filter(is_staff=True, is_active=True):
            if not member.email:
                continue
            _, created = ContactEmail.objects.get_or_create(
                email_address=member.email,
                defaults={
                    "member": member,
                    "email_type": "primary",
                    "verified": True,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created verified ContactEmail for staff '{member.username}'."))
            else:
                self.stdout.write(
                    self.style.WARNING(f"ContactEmail already exists for '{member.username}' — skipping.")
                )
