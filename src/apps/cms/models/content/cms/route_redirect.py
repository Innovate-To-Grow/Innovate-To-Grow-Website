"""Administrator-managed permanent route redirects."""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import ProjectControlModel


class RouteRedirectQuerySet(models.QuerySet):
    def delete(self):
        raise ValidationError("Route redirects cannot be deleted; disable redirects instead.")


class RouteRedirectManager(models.Manager.from_queryset(RouteRedirectQuerySet)):
    pass


class RouteRedirect(ProjectControlModel):
    """An exact, internal old-path to new-path permanent redirect."""

    class EdgeSyncStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"

    source_path = models.CharField(
        max_length=200,
        unique=True,
        help_text="Exact legacy path. It cannot be changed after this redirect is created.",
    )
    destination_path = models.CharField(
        max_length=200,
        help_text="A published CMS page or registered public application route.",
    )
    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "Enable this permanent 301 redirect after reviewing it carefully. "
            "Browsers and search engines may cache a 301 for a long time."
        ),
    )
    notes = models.TextField(blank=True, default="")

    edge_sync_status = models.CharField(
        max_length=10,
        choices=EdgeSyncStatus.choices,
        default=EdgeSyncStatus.PENDING,
        editable=False,
        db_index=True,
    )
    edge_sync_error = models.TextField(blank=True, default="", editable=False)
    edge_sync_attempted_at = models.DateTimeField(null=True, blank=True, editable=False)
    edge_synced_at = models.DateTimeField(null=True, blank=True, editable=False)
    edge_rule_managed = models.BooleanField(
        default=False,
        editable=False,
        db_index=True,
        help_text="Internal marker that a confirmed CMS-managed Amplify rule still owns this source.",
    )

    objects = RouteRedirectManager()

    class Meta:
        db_table = "cms_routeredirect"
        ordering = ["source_path"]
        verbose_name = "Route Redirect"
        verbose_name_plural = "Route Redirects"
        indexes = [
            models.Index(fields=["destination_path", "is_active"]),
        ]

    def __str__(self):
        state = "active" if self.is_active else "inactive"
        return f"{self.source_path} → {self.destination_path} ({state})"

    def clean(self):
        super().clean()
        from apps.cms.services.route_redirects import (
            normalize_and_validate_legacy_source,
            normalize_and_validate_route,
            redirect_mapping_conflicts,
        )

        self.source_path = normalize_and_validate_legacy_source(self.source_path)
        self.destination_path = normalize_and_validate_route(self.destination_path)

        old_values = None
        if not self._state.adding:
            old_values = type(self).objects.filter(pk=self.pk).values("source_path", "is_active").first()
            if old_values is not None and old_values["source_path"] != self.source_path:
                raise ValidationError(
                    {"source_path": "Source path cannot be changed after creation; disable this redirect instead."}
                )

        # Recovery must remain possible if a later page/app-route change makes
        # an existing active mapping conflict with current validation rules.
        if old_values and old_values["is_active"] and not self.is_active:
            return

        inactive_maintenance = bool(old_values and not old_values["is_active"] and not self.is_active)

        source, destination, conflicts = redirect_mapping_conflicts(
            self.source_path,
            self.destination_path,
            exclude_redirect_id=self.pk,
        )
        self.source_path = source
        self.destination_path = destination

        if inactive_maintenance:
            # An inactive historical source can become reserved later as the
            # React/system route registry evolves. Its immutable source is no
            # longer runtime-active, so allow notes/destination maintenance
            # (including page-rename retargeting) while still validating the
            # destination. Reactivation runs the complete conflict check.
            conflicts = [conflict for conflict in conflicts if conflict.field != "source_path"]

        errors: dict[str, list[str]] = {}
        for conflict in conflicts:
            errors.setdefault(conflict.field, []).append(conflict.message)
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        from apps.cms.services.route_redirects import (
            normalize_and_validate_legacy_source,
            normalize_and_validate_route,
        )
        from apps.cms.services.route_write_locks import lock_route_redirect_write

        self.source_path = normalize_and_validate_legacy_source(self.source_path)
        self.destination_path = normalize_and_validate_route(self.destination_path)

        # Validation must run after the target page and redirect graph are
        # locked.  Otherwise activation can race a page archive/delete and
        # both transactions can validate stale pre-commit state.
        with lock_route_redirect_write(self):
            self.full_clean()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Route redirects cannot be deleted; disable the redirect instead.")
