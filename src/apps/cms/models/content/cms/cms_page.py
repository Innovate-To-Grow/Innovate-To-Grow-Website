import re

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import ProjectControlModel

ROUTE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$")
_PERSISTED_ROUTE_NOT_PROVIDED = object()


def normalize_cms_route(route):
    """Normalize CMS route paths to a canonical leading-slash/no-trailing-slash form."""
    route = (route or "").strip()
    if not route:
        return "/"

    segments = [segment.strip() for segment in route.split("/") if segment.strip()]
    if not segments:
        return "/"

    return "/" + "/".join(segments)


def validate_cms_route(route):
    """Validate a normalized CMS route."""
    normalized = normalize_cms_route(route)

    if normalized == "/":
        return normalized

    for segment in normalized.strip("/").split("/"):
        if not ROUTE_SEGMENT_RE.fullmatch(segment):
            raise ValidationError(
                "Each path segment must use letters, numbers, hyphens, or underscores only.",
            )

    return normalized


class CMSPageQuerySet(models.QuerySet):
    def delete(self):
        """Delete pages through the instance lock/guard path.

        Django's bulk delete bypasses ``CMSPage.delete()``.  Running each
        instance delete in one transaction keeps admin/queryset deletion on
        the same page-row-then-redirect-row protocol as every other writer.
        """

        deleted_total = 0
        deleted_by_model: dict[str, int] = {}
        with transaction.atomic():
            pages = list(self.order_by("pk"))
            for page in pages:
                deleted, per_model = page.delete()
                deleted_total += deleted
                for model_label, count in per_model.items():
                    deleted_by_model[model_label] = deleted_by_model.get(model_label, 0) + count
        return deleted_total, deleted_by_model


class CMSPageManager(models.Manager.from_queryset(CMSPageQuerySet)):
    pass


class CMSPage(ProjectControlModel):
    """A CMS-managed page. One record per frontend route."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="Stable identifier for import/export. Do not change after publishing.",
    )
    route = models.CharField(
        max_length=200,
        unique=True,
        help_text="Frontend route path, e.g. '/about'. Must start with '/'.",
    )
    title = models.CharField(max_length=300)
    meta_description = models.TextField(blank=True, default="")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft", db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)

    page_css_class = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="CSS class for the page wrapper div, e.g. 'about-page'.",
    )
    page_css = models.TextField(
        blank=True,
        default="",
        help_text="Custom CSS injected when this page is loaded. Scoped to the page wrapper.",
    )
    sort_order = models.IntegerField(default=0)

    objects = CMSPageManager()

    class Meta:
        db_table = "cms_cmspage"
        ordering = ["sort_order", "title"]
        verbose_name = "CMS Page"
        verbose_name_plural = "CMS Pages"
        indexes = [
            models.Index(fields=["route", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.route})"

    def clean(self):
        super().clean()
        from apps.cms.services.route_redirects import page_route_conflicts

        self.route, conflicts = page_route_conflicts(self.route, exclude_page_id=self.pk)
        if conflicts:
            raise ValidationError({"route": [conflict.message for conflict in conflicts]})
        # ``save()`` re-runs this ownership check while holding the shared
        # route/page/redirect locks.  The marker preserves the intentional
        # legacy behavior where raw ORM writes can bypass route ownership
        # validation, while all supported CMS writers call full_clean().
        self._route_ownership_validated = True
        self._validate_redirect_destination_status()

    def _redirect_destination_routes(self, persisted_route=_PERSISTED_ROUTE_NOT_PROVIDED):
        routes = {self.route}
        if persisted_route is _PERSISTED_ROUTE_NOT_PROVIDED:
            persisted_route = None
            if self.pk and not self._state.adding:
                persisted_route = type(self).objects.filter(pk=self.pk).values_list("route", flat=True).first()
        if persisted_route:
            routes.add(persisted_route)
        return routes

    def _active_destination_redirect(self, persisted_route=_PERSISTED_ROUTE_NOT_PROVIDED):
        """Return the first active redirect targeting this page's old/new route."""

        # Imported lazily to avoid a model-module cycle.
        from .route_redirect import RouteRedirect

        return (
            RouteRedirect.objects.filter(
                is_active=True,
                destination_path__in=self._redirect_destination_routes(persisted_route),
            )
            .only("source_path", "destination_path")
            .order_by("source_path", "pk")
            .first()
        )

    def _validate_redirect_destination_status(self, persisted_route=_PERSISTED_ROUTE_NOT_PROVIDED):
        """Do not leave active redirects pointing at an unpublished page."""

        if self.status == "published":
            return

        redirect = self._active_destination_redirect(persisted_route)
        if redirect:
            raise ValidationError(
                {
                    "status": (
                        f'Page cannot be unpublished or archived while active redirect "{redirect.source_path}" '
                        f'points to "{redirect.destination_path}". Disable or retarget the redirect first.'
                    )
                }
            )

    def save(self, *args, **kwargs):
        # Django does not call full_clean() from save().  Supported CMS writers
        # (Admin ModelForm, JSON import, CLI CRUD, and System Intelligence)
        # validate explicitly; direct ORM writes remain available to migrations
        # and tests that need to inspect legacy collision state.
        update_fields = kwargs.get("update_fields")
        route_will_save = update_fields is None or "route" in update_fields
        self.route = normalize_cms_route(self.route)

        from apps.cms.services.route_write_locks import lock_cms_page_write

        with lock_cms_page_write(
            self,
            candidate_route=self.route if route_will_save else None,
        ) as snapshot:
            if getattr(self, "_route_ownership_validated", False):
                from apps.cms.services.route_redirects import page_route_conflicts

                self.route, conflicts = page_route_conflicts(self.route, exclude_page_id=self.pk)
                if conflicts:
                    raise ValidationError({"route": [conflict.message for conflict in conflicts]})

            # Re-read the redirect state only after this page row and all
            # relevant redirect rows are locked.  This closes activation vs.
            # archive/unpublish races in either commit order.
            self._validate_redirect_destination_status(snapshot.persisted_route)
            if self.status == "published" and not self.published_at:
                self.published_at = timezone.now()
            super().save(*args, **kwargs)
            if route_will_save and snapshot.persisted_route and snapshot.persisted_route != self.route:
                from apps.cms.services.page_routes import apply_page_route_change

                apply_page_route_change(page=self, old_route=snapshot.persisted_route, keep_redirect=False)

    def delete(self, *args, **kwargs):
        from apps.cms.services.route_write_locks import lock_cms_page_write

        with lock_cms_page_write(self, candidate_route=self.route) as snapshot:
            redirect = self._active_destination_redirect(snapshot.persisted_route)
            if redirect:
                raise ValidationError(
                    f'CMS page cannot be deleted while active redirect "{redirect.source_path}" points to '
                    f'"{redirect.destination_path}". Disable or retarget the redirect first.'
                )
            return super().delete(*args, **kwargs)
