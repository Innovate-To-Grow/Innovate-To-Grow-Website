from django.conf import settings
from django.db import models
from django.utils import timezone


class SEOFieldsMixin(models.Model):
    """Reusable SEO and Open Graph fields."""

    meta_title = models.CharField(
        max_length=255, blank=True, help_text="SEO title (will fall back to page title if empty)."
    )
    meta_description = models.TextField(blank=True, help_text="SEO description for search engines and social sharing.")
    meta_keywords = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated SEO keywords (optional, some search engines may ignore this).",
    )
    og_image = models.URLField(
        blank=True, null=True, help_text="Open Graph share image URL (e.g. for social media cards)."
    )
    canonical_url = models.URLField(
        blank=True, null=True, help_text="Canonical URL for SEO (optional, usually auto-resolved)."
    )
    meta_robots = models.CharField(
        max_length=100, blank=True, help_text="Robots meta tag value, e.g. 'index,follow' or 'noindex,nofollow'."
    )
    google_site_verification = models.CharField(
        max_length=255, blank=True, help_text="Google Search Console verification token for this page (optional)."
    )
    google_structured_data = models.JSONField(
        blank=True, null=True, help_text="Optional JSON-LD structured data payload for Google Search."
    )

    class Meta:
        abstract = True


class AnalyticsFieldsMixin(models.Model):
    """Reusable analytics and rendering metadata."""

    slug_depth = models.PositiveIntegerField(
        default=0, help_text="Redundant: number of path segments (e.g. 'about/team' -> 1 slash)."
    )
    view_count = models.PositiveIntegerField(
        default=0, help_text="Redundant: total view count (may be updated externally)."
    )
    last_viewed_at = models.DateTimeField(null=True, blank=True, help_text="Redundant: timestamp of last page view.")
    template_name = models.CharField(
        max_length=255, blank=True, help_text="Optional template name override for rendering this page."
    )

    class Meta:
        abstract = True


class WorkflowPublishingMixin(models.Model):
    """
    Publishing workflow: Draft -> Review -> Published.

    Provides status field, workflow transition methods, and audit fields.
    Integrates with ProjectControlModel's versioning system.
    """

    class PublishStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Pending Publish"
        PUBLISHED = "published", "Published"

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
        help_text="Timestamp when the page was first published.",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_published",
        help_text="User who published this content.",
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
        related_name="%(app_label)s_%(class)s_submitted_review",
        help_text="User who submitted for review.",
    )

    class Meta:
        abstract = True

    # Backward compatibility: computed property
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
        self.save(update_fields=["status", "submitted_for_review_at", "submitted_for_review_by", "updated_at"])
        # Save version for audit trail
        if hasattr(self, "save_version"):
            self.save_version(comment="Submitted for review", user=user)

    def publish(self, user=None):
        """Transition from Review (or Draft) to Published."""
        if self.status not in (self.PublishStatus.REVIEW, self.PublishStatus.DRAFT):
            raise ValueError(f"Cannot publish: current status is '{self.get_status_display()}'.")
        self.status = self.PublishStatus.PUBLISHED
        if not self.published_at:
            self.published_at = timezone.now()
        self.published_by = user
        self.save(update_fields=["status", "published_at", "published_by", "updated_at"])
        if hasattr(self, "save_version"):
            self.save_version(comment="Published", user=user)

    def unpublish(self, user=None):
        """Revert to Draft from any state."""
        self.status = self.PublishStatus.DRAFT
        self.save(update_fields=["status", "updated_at"])
        if hasattr(self, "save_version"):
            self.save_version(comment="Unpublished (reverted to draft)", user=user)

    def reject_review(self, user=None):
        """Reject review and send back to Draft."""
        if self.status != self.PublishStatus.REVIEW:
            raise ValueError(f"Cannot reject: current status is '{self.get_status_display()}'.")
        self.status = self.PublishStatus.DRAFT
        self.save(update_fields=["status", "updated_at"])
        if hasattr(self, "save_version"):
            self.save_version(comment="Review rejected, reverted to draft", user=user)


class ComponentPageMixin(models.Model):
    """Shared component-ordering logic for Page and HomePage."""

    class Meta:
        abstract = True

    @property
    def ordered_components(self):
        """Return enabled components ordered by placement order."""
        placements = (
            self.component_placements.filter(component__is_enabled=True)
            .select_related("component")
            .order_by("order", "id")
        )
        return [p.component for p in placements]

    @property
    def all_components(self):
        """Return all components (including disabled) ordered by placement order."""
        placements = self.component_placements.select_related("component").order_by("order", "id")
        return [p.component for p in placements]


# Backward-compatible alias
PublishingFieldsMixin = WorkflowPublishingMixin
