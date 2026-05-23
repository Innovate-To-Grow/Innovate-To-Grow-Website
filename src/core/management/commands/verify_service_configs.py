"""Verify that database-managed service credentials are configured.

Run before removing process env vars to confirm that runtime services
(email, SMS, Sheets) have valid configs in the database.
"""

from django.core.management.base import BaseCommand, CommandError

from core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GoogleCredentialConfig,
    SMSServiceConfig,
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
            help="Treat missing SMSServiceConfig as a failure under --strict.",
        )
        parser.add_argument(
            "--require-google",
            action="store_true",
            help="Treat missing GoogleCredentialConfig as a failure under --strict.",
        )
        parser.add_argument(
            "--require-aws",
            action="store_true",
            help="Treat missing AWSCredentialConfig (or SES fallback) as a failure under --strict.",
        )

    def handle(self, *args, **options):
        strict = options["strict"]
        failures: list[str] = []
        warnings: list[str] = []

        email = EmailServiceConfig.load()
        email_ok = bool(email.pk) and (email.ses_configured or self._smtp_configured(email))
        self._report("EmailServiceConfig", email, email_ok, required=True)
        if not email_ok:
            failures.append("EmailServiceConfig is not configured (SES or SMTP required).")

        sms = SMSServiceConfig.load()
        sms_ok = bool(sms.pk) and sms.is_configured
        self._report("SMSServiceConfig", sms, sms_ok, required=options["require_sms"])
        if not sms_ok:
            (failures if options["require_sms"] else warnings).append(
                "SMSServiceConfig is not configured (needs origination number + AWS credentials)."
            )

        google = GoogleCredentialConfig.load()
        google_ok = bool(google.pk) and google.is_configured
        self._report("GoogleCredentialConfig", google, google_ok, required=options["require_google"])
        if not google_ok:
            (failures if options["require_google"] else warnings).append("GoogleCredentialConfig is not configured.")

        aws = AWSCredentialConfig.load()
        aws_ok = bool(aws.pk) and aws.is_configured
        aws_fallback_ok = aws_ok or (email_ok and email.ses_configured)
        self._report("AWSCredentialConfig", aws, aws_ok, required=options["require_aws"])
        if not aws_fallback_ok:
            (failures if options["require_aws"] else warnings).append(
                "No AWSCredentialConfig and no SES keys to fall back on (SMS/Bedrock will fail)."
            )

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
    def _smtp_configured(config) -> bool:
        return bool(config.smtp_host and config.smtp_username and config.smtp_password)
