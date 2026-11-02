"""The live side of request limits: each scope's Smart factor and each web process's heartbeat."""

from django.db import models

from ..base.control import ProjectControlModel


class RequestRateLimitState(ProjectControlModel):
    """One scope's Smart factor (written only when the controller changes it, never per request)."""

    scope = models.CharField(max_length=64, unique=True)
    # Share of the scope's baseline Smart limit allows now, in [smart floor, 1].
    factor = models.FloatField(default=1.0)
    factor_changed_at = models.DateTimeField(null=True, blank=True)
    last_cut_at = models.DateTimeField(null=True, blank=True)
    # The controller's last decision for the scope: pressure, the tier being shed or restored and the signal
    # values behind it (shown on the admin page).
    last_decision = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Request Limit State"
        verbose_name_plural = "Request Limit States"
        ordering = ("scope",)

    def __str__(self):
        return f"{self.scope}: × {self.factor:.2f}"


class RequestLimitProcess(ProjectControlModel):
    """One live web process. Without a shared counter store each process enforces ``limit / live processes``; the
    count comes from these rows (refreshed about every 30 s, stale after about 90 s)."""

    instance = models.CharField(max_length=32, unique=True)
    host = models.CharField(max_length=255, blank=True, default="")
    pid = models.PositiveIntegerField()
    started_at = models.DateTimeField()
    last_seen = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "Request Limit Process"
        verbose_name_plural = "Request Limit Processes"
        ordering = ("-last_seen",)

    def __str__(self):
        return f"{self.host or '?'}:{self.pid}"
