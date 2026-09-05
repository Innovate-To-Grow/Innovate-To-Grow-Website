"""Verify that database-managed service credentials are configured.

Run before removing process env vars to confirm that runtime services
(email, SMS, Sheets) have valid configs in the database. All AWS-backed
services share a single AWSCredentialConfig.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GoogleCredentialConfig,
    SendVerificationConfig,
    SMTPProviderConfig,
)


class Command(BaseCommand):
    help = "Verify active service credential configs exist in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 if any required config is missing.",
        )
        parser.add_argument(
            "--require-sms",
            action="store_true",
            help="Treat missing AWS SNS settings as a failure under --strict.",
        )
        parser.add_argument(
            "--require-google",
            action="store_true",
            help="Treat missing GoogleCredentialConfig as a failure under --strict.",
        )
        parser.add_argument(
            "--require-aws",
            action="store_true",
            help="Treat missing AWSCredentialConfig as a failure under --strict.",
        )

    def handle(self, *args, **options):
        strict = options["strict"]
        failures: list[str] = []
        warnings: list[str] = []

        email = EmailServiceConfig.load()
        aws = AWSCredentialConfig.load()
        aws_ok = bool(aws.pk) and aws.is_configured
        aws_required = options["require_aws"] or email.provider == "ses"
        self._report("AWSCredentialConfig", aws, aws_ok, required=aws_required)
        if not aws_ok:
            (failures if aws_required else warnings).append(
                "AWSCredentialConfig is not configured (SES, SNS, and Bedrock all depend on it)."
            )

        sender_ok = self._valid_email(email.from_email)
        smtp = SMTPProviderConfig.load()
        smtp_ok = bool(smtp.pk) and smtp.is_configured
        if email.provider == "ses":
            provider_ok = aws_ok
        elif email.provider == "smtp":
            provider_ok = smtp_ok
        else:
            provider_ok = False
        email_ok = bool(email.pk) and email.is_active and sender_ok and provider_ok
        self._report("EmailServiceConfig", email, email_ok, required=True)
        if not email_ok:
            if not sender_ok:
                failures.append("EmailServiceConfig From address is empty or invalid.")
            elif email.provider == "smtp":
                failures.append("EmailServiceConfig selects SMTP, but SMTPProviderConfig is not configured.")
            elif email.provider == "ses":
                failures.append(
                    "EmailServiceConfig selects SES, but its active sender or AWS Credentials are not configured."
                )
            else:
                failures.append(f"EmailServiceConfig selects unsupported provider {email.provider!r}.")

        smtp_required = email.provider == "smtp"
        self._report("SMTPProviderConfig", smtp, smtp_ok, required=smtp_required)
        if not smtp_ok:
            (failures if smtp_required else warnings).append("SMTPProviderConfig is not configured.")

        sms_ok = bool(aws.pk) and aws.sns_configured
        self._report("AWS SNS SMS", aws, sms_ok, required=options["require_sms"])
        if not sms_ok:
            (failures if options["require_sms"] else warnings).append(
                "AWS SNS SMS is not configured (no active SMS origination number found for the AWS "
                "account; register one in SNS/Pinpoint, or set a manual override on AWS Credentials)."
            )

        google = GoogleCredentialConfig.load()
        google_ok = bool(google.pk) and google.is_configured
        self._report("GoogleCredentialConfig", google, google_ok, required=options["require_google"])
        if not google_ok:
            (failures if options["require_google"] else warnings).append("GoogleCredentialConfig is not configured.")

        send_verification = SendVerificationConfig.load()
        send_ok = bool(send_verification.pk) and send_verification.is_configured
        self._report("SendVerificationConfig", send_verification, send_ok, required=False)
        if not send_ok:
            warnings.append("SendVerificationConfig HMAC secret is not configured. Enforce mode will fail closed.")

        for warning in warnings:
            self.stdout.write(self.style.WARNING(f"WARN: {warning}"))

        if failures:
            for failure in failures:
                self.stdout.write(self.style.ERROR(f"FAIL: {failure}"))
            if strict:
                raise CommandError("Service config verification failed.")
            return

        self.stdout.write(self.style.SUCCESS("Service config verification passed."))

    def _report(self, label: str, config, configured: bool, *, required: bool) -> None:
        if configured:
            status = self.style.SUCCESS("OK")
            name = getattr(config, "name", "—")
            self.stdout.write(f"{label}: {status} ({name})")
            return

        marker = self.style.ERROR("MISSING") if required else self.style.WARNING("missing")
        self.stdout.write(f"{label}: {marker}")

    @staticmethod
    def _valid_email(value: str) -> bool:
        if not value:
            return False
        try:
            validate_email(value)
        except ValidationError:
            return False
        return True
