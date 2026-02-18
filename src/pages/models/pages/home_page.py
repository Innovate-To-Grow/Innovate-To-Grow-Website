"""
Home page model for the main landing page.

Supports multiple versions with only one active at a time.
Content is composed of ordered PageComponent blocks.
Includes publishing workflow: Draft -> Review -> Published.
"""

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone

from core.models import ProjectControlModel

# ============================== Cache Configuration ==============================

HOMEPAGE_CACHE_KEY = "pages.homepage.active"
HOMEPAGE_CACHE_TIMEOUT = 300  # 5 minutes

# ============================== HomePage Model ==============================


class HomePage(ProjectControlModel):
    """Home page model composed of ordered PageComponents (one version active)."""

    class PublishStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Pending Publish"
        PUBLISHED = "published", "Published"

    name = models.CharField(max_length=200, help_text="Internal name to identify this home page version")
    is_active = models.BooleanField(default=False, help_text="Only one home page can be active at a time")

    # Publishing workflow
    status = models.CharField(
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
        help_text="Publishing workflow status.",
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this home page was first published.",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homepages_published",
        help_text="User who published this home page.",
    )
    submitted_for_review_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when submitted for review.",
    )
    submitted_for_review_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homepages_submitted_review",
        help_text="User who submitted for review.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Home Page"
        verbose_name_plural = "Home Pages"

    def save(self, *args, **kwargs):
        # Only allow setting is_active if status is published
        if self.is_active and self.status != self.PublishStatus.PUBLISHED:
            from django.core.exceptions import ValidationError

            raise ValidationError("Cannot activate a home page that is not published.")
        # If this home page is being set as active, deactivate all others
        if self.is_active:
            HomePage.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
        # Invalidate cache
        cache.delete(HOMEPAGE_CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(HOMEPAGE_CACHE_KEY)

    def __str__(self):
        parts = [self.name]
        if self.is_active:
            parts.append("(Active)")
        parts.append(f"[{self.get_status_display()}]")
        return " ".join(parts)

    @classmethod
    def get_active(cls):
        """Get the currently active AND published home page, with caching."""
        cached = cache.get(HOMEPAGE_CACHE_KEY)
        if cached is not None:
            return cached

        home = cls.objects.filter(is_active=True, status="published").first()
        cache.set(HOMEPAGE_CACHE_KEY, home, HOMEPAGE_CACHE_TIMEOUT)
        return home

    # Backward-compatible property
    @property
    def published(self):
        """Backward-compatible boolean check."""
        return self.status == self.PublishStatus.PUBLISHED

    # ========================
    # Workflow Transitions
    # ========================

    def submit_for_review(self, user=None):
        """Transition from Draft to Review."""
        if self.status != self.PublishStatus.DRAFT:
            raise ValueError(f"Cannot submit for review: current status is '{self.get_status_display()}'.")
        self.status = self.PublishStatus.REVIEW
        self.submitted_for_review_at = timezone.now()
        self.submitted_for_review_by = user
        self.save(
            update_fields=["status", "submitted_for_review_at", "submitted_for_review_by", "updated_at"]
        )
        self.save_version(comment="Submitted for review", user=user)

    def publish(self, user=None):
        """Transition from Review (or Draft) to Published."""
        if self.status not in (self.PublishStatus.REVIEW, self.PublishStatus.DRAFT):
            raise ValueError(f"Cannot publish: current status is '{self.get_status_display()}'.")
        self.status = self.PublishStatus.PUBLISHED
        if not self.published_at:
            self.published_at = timezone.now()
        self.published_by = user
        self.save(
            update_fields=["status", "published_at", "published_by", "updated_at"]
        )
        self.save_version(comment="Published", user=user)

    def unpublish(self, user=None):
        """Revert to Draft from any state. Also deactivates."""
        self.status = self.PublishStatus.DRAFT
        self.is_active = False
        self.save(update_fields=["status", "is_active", "updated_at"])
        self.save_version(comment="Unpublished (reverted to draft)", user=user)

    def reject_review(self, user=None):
        """Reject review and send back to Draft."""
        if self.status != self.PublishStatus.REVIEW:
            raise ValueError(f"Cannot reject: current status is '{self.get_status_display()}'.")
        self.status = self.PublishStatus.DRAFT
        self.save(update_fields=["status", "updated_at"])
        self.save_version(comment="Review rejected, reverted to draft", user=user)

    @property
    def ordered_components(self):
        """Return enabled components ordered for rendering."""
        return self.components.filter(is_enabled=True).order_by("order", "id")

    @property
    def all_components(self):
        """Return all components (including disabled) ordered."""
        return self.components.order_by("order", "id")
