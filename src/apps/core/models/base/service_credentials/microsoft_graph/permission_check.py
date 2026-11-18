from django.conf import settings
from django.db import models
from django.utils import timezone

from ...abstract.control import ProjectControlModel


class MicrosoftGraphPermissionCheck(ProjectControlModel):
    """One "Check permissions" run: which application roles the current certificate's token carries.

    Read-only diagnostics, written by the admin's "Check permissions" and ``manage.py verify_graph_access
    --permissions-only``. It sends no mail, needs no deny mailbox and is never go-live evidence: the go-live gate reads
    only ``MicrosoftGraphAccessCheck``. ``granted_roles`` is the token's ``roles`` claim, read without verifying it
    (None means unreadable); ``extra_roles`` are those beyond ``GRAPH_APPROVED_APPLICATION_ROLES`` at the time.
    ``trace_result`` is the live Message Trace probe's outcome. Only the latest ``RETAINED`` rows of a config are kept.
    """

    RETAINED = 20

    class TraceResult(models.TextChoices):
        AVAILABLE = "available", "Available"
        NOT_GRANTED = "not_granted", "Not granted (not probed)"
        NO_SERVICE_PRINCIPAL = "no_service_principal", "Service principal missing or still provisioning"
        NOT_CONSENTED = "not_consented", "Permission not consented"
        THROTTLED = "throttled", "Throttled; try again later"
        ERROR = "error", "Error"
        NOT_CHECKED = "not_checked", "Not checked (no token)"

    config = models.ForeignKey(
        "core.MicrosoftGraphProviderConfig", on_delete=models.CASCADE, related_name="permission_checks"
    )
    certificate_sha1 = models.CharField(max_length=40, blank=True, default="", verbose_name="Certificate (SHA-1)")
    token_ok = models.BooleanField(default=False, verbose_name="Token Issued")
    token_error = models.CharField(max_length=500, blank=True, default="", verbose_name="Token Error")
    granted_roles = models.JSONField(null=True, blank=True, verbose_name="Granted Application Roles")
    extra_roles = models.JSONField(default=list, blank=True, verbose_name="Roles Beyond the Approval")
    trace_result = models.CharField(
        max_length=24, choices=TraceResult.choices, default=TraceResult.NOT_CHECKED, verbose_name="Message Trace"
    )
    trace_note = models.CharField(max_length=500, blank=True, default="", verbose_name="Message Trace Note")
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Checked By",
    )

    class Meta:
        verbose_name = "Microsoft Graph Permission Check"
        verbose_name_plural = "Microsoft Graph Permission Checks"
        ordering = ("-created_at",)

    def __str__(self):
        return f"Permission check ({timezone.localtime(self.created_at):%Y-%m-%d %H:%M})"

    @classmethod
    def prune(cls, config) -> int:
        """Delete all but the latest ``RETAINED`` checks of *config*; returns how many were deleted."""
        rows = cls.objects.filter(config=config).order_by("-created_at", "-pk")
        stale = list(rows.values_list("pk", flat=True)[cls.RETAINED :])
        return cls.objects.filter(pk__in=stale).delete()[0] if stale else 0
