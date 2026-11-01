import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone

from ..control import ProjectControlModel

RUN_THE_CHECK = (
    "Run the access check (superuser: Run access check on the Microsoft Graph configuration's page, or "
    "manage.py verify_graph_access) and try again."
)


class MicrosoftGraphAccessCheck(ProjectControlModel):
    """One run of the Microsoft Graph access check: evidence of what Microsoft let the Entra app do.

    Written by ``manage.py verify_graph_access`` and by the admin's "Run access check". ``results`` holds one entry
    per probe (outcome, HTTP status, allow-listed Graph error code, Microsoft request id and a fixed note), never a
    token, message content or response body. ``granted_roles`` is what the access token claims, read without
    verifying it (diagnostic only: RBAC for Applications grants never appear there); None means it was unreadable.
    """

    class Verdict(models.TextChoices):
        COMPLIANT = "compliant", "Matches the approval"
        NOT_COMPLIANT = "not_compliant", "Does not match the approval"
        INCOMPLETE = "incomplete", "Not a complete validation"

    class Source(models.TextChoices):
        COMMAND = "command", "manage.py verify_graph_access"
        ADMIN = "admin", "Django admin"

    config = models.ForeignKey(
        "core.MicrosoftGraphProviderConfig", on_delete=models.CASCADE, related_name="access_checks"
    )
    certificate = models.ForeignKey(
        "core.MicrosoftGraphCertificate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_checks",
        help_text="The certificate the access token was requested with.",
    )
    certificate_sha1 = models.CharField(max_length=40, verbose_name="Certificate Thumbprint (SHA-1)")
    tenant_id = models.CharField(max_length=253, verbose_name="Tenant ID")
    client_id = models.CharField(max_length=64, verbose_name="Client ID")
    deny_mailbox = models.CharField(max_length=254, verbose_name="Deny Mailbox")
    source = models.CharField(max_length=16, choices=Source.choices, verbose_name="Run From")
    run_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Run By",
    )
    results = models.JSONField(default=list, blank=True, verbose_name="Probe Results")
    granted_roles = models.JSONField(null=True, blank=True, verbose_name="Granted Application Roles")
    approved_roles = models.JSONField(default=list, blank=True, verbose_name="Approved Application Roles")
    mailbox_restriction_passed = models.BooleanField(default=False, verbose_name="Mailbox Restriction Holds")
    roles_within_approval = models.BooleanField(null=True, verbose_name="Roles Within the Approval")
    complete = models.BooleanField(default=False, verbose_name="Complete Validation")
    permission_exception_reference = models.CharField(
        max_length=255, blank=True, default="", verbose_name="InfoSec Exception Reference (at the time)"
    )
    verdict = models.CharField(max_length=16, choices=Verdict.choices, verbose_name="Verdict")

    class Meta:
        verbose_name = "Microsoft Graph Access Check"
        verbose_name_plural = "Microsoft Graph Access Checks"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.get_verdict_display()} ({timezone.localtime(self.created_at):%Y-%m-%d %H:%M})"


def go_live_problem(config, *, now=None) -> str:
    """Why email delivery may not switch to Microsoft Graph yet (``GRAPH_REQUIRE_ACCESS_EVIDENCE``), or "".

    The latest access check run with *config*'s current certificate must match the approval, have been run against
    the designated deny mailbox, and be no older than ``GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS``. Any role its token
    claimed beyond today's ``GRAPH_APPROVED_APPLICATION_ROLES`` still needs an InfoSec exception reference now, so
    clearing the reference (or narrowing the approval) withdraws the evidence.
    """
    certificate = config.current_certificate
    check = None
    if certificate is not None:
        check = config.access_checks.filter(certificate=certificate).order_by("-created_at").first()
    if check is None:
        return f"no access check is recorded for the current certificate. {RUN_THE_CHECK}"
    max_age = settings.GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS
    if check.created_at < (now or timezone.now()) - datetime.timedelta(days=max_age):
        return f"the latest access check is more than {max_age} days old. {RUN_THE_CHECK}"
    if not config.access_check_deny_mailbox or check.deny_mailbox != config.access_check_deny_mailbox:
        return f"the latest access check did not use the designated deny mailbox. {RUN_THE_CHECK}"
    if check.verdict != MicrosoftGraphAccessCheck.Verdict.COMPLIANT:
        return f"the latest access check found: {check.get_verdict_display().lower()}. {RUN_THE_CHECK}"
    extra = sorted(set(check.granted_roles or ()) - set(settings.GRAPH_APPROVED_APPLICATION_ROLES))
    if extra and not config.permission_exception_reference:
        return (
            f"the access token claims {', '.join(extra)} beyond the approval, and no InfoSec exception reference "
            "is recorded. Ask OIT to remove the extra permissions and run the access check again, or record the "
            "reference of InfoSec's written review."
        )
    return ""
