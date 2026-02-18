import uuid

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import ProjectControlModel


def default_config() -> dict:
    return {}


class ComponentDataSource(ProjectControlModel):
    """
    Whitelisted internal API data source for components.
    Do NOT store arbitrary external URLs here (SSRF risk).
    """

    class AuthMode(models.TextChoices):
        PUBLIC = "public", "Public"
        LOGIN_REQUIRED = "login_required", "Login Required"
        SELF_ONLY = "self_only", "Self Only"

    class HttpMethod(models.TextChoices):
        GET = "GET", "GET"
        POST = "POST", "POST"

    source_name = models.CharField(
        max_length=255,
        unique=True,
    )

    # must be an internal path
    source_url = models.URLField(
        max_length=255,
    )

    request_method = models.CharField(
        max_length=10,
        choices=HttpMethod.choices,
        default=HttpMethod.GET,
    )

    auth_mode = models.CharField(
        max_length=32,
        choices=AuthMode.choices,
        default=AuthMode.PUBLIC,
    )

    cache_ttl_seconds = models.PositiveIntegerField(default=300)
    timeout_ms = models.PositiveIntegerField(default=10000)
    is_enabled = models.BooleanField(default=True)

    # Optional: versioning for client contract
    response_schema_version = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        verbose_name = "Component Data Source"
        verbose_name_plural = "Component Data Sources"
        ordering = ["source_name"]

    def clean(self):
        super().clean()
        # Validate internal path format
        if self.source_url and not self.source_url.startswith("/"):
            raise ValidationError("DataSource URL must be an internal absolute path starting with '/'.")

    def __str__(self) -> str:
        return f"{self.source_name} -> {self.request_method} {self.source_url}"


class PageComponent(ProjectControlModel):
    """
    Component/section block that belongs to exactly one of Page or HomePage.
    Supports HTML + images + forms + optional dynamic data pulled from a server-side endpoint.
    """

    class ComponentType(models.TextChoices):
        HTML = "html", "HTML"
        TEMPLATE = "template", "Template"
        MARKDOWN = "markdown", "Markdown"
        WIDGET = "widget", "Widget"
        FORM = "form", "Form"

    component_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, default="")

    component_type = models.CharField(
        max_length=32, choices=ComponentType.choices, default=ComponentType.HTML, db_index=True
    )

    # Parent assignment (exactly one)
    page = models.ForeignKey("pages.Page", on_delete=models.CASCADE, related_name="components", blank=True, null=True)
    home_page = models.ForeignKey(
        "pages.HomePage", on_delete=models.CASCADE, related_name="components", blank=True, null=True
    )

    order = models.PositiveIntegerField(default=0, db_index=True)
    is_enabled = models.BooleanField(default=True, db_index=True)

    # Content/code
    html_content = models.TextField(blank=True, default="")
    css_file = models.FileField(upload_to="page_components/css/", blank=True, null=True)
    css_code = models.TextField(blank=True, default="")
    js_code = models.TextField(blank=True, default="")
    config = models.JSONField(default=default_config, blank=True, null=True)

    # Images (single hero + background)
    image = models.ImageField(upload_to="page_components/images/", blank=True, null=True)
    image_alt = models.CharField(max_length=255, blank=True, default="")
    image_caption = models.CharField(max_length=255, blank=True, default="")
    image_link = models.URLField(blank=True, default="")

    background_image = models.ImageField(upload_to="page_components/backgrounds/", blank=True, null=True)
    background_image_alt = models.CharField(max_length=255, blank=True, default="")

    # Embedded form (for component_type='form')
    form = models.ForeignKey(
        "pages.UniformForm",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="page_components",
        help_text="Form to embed when component_type is 'form'.",
    )

    # Dynamic data (optional)
    data_source = models.ForeignKey(
        ComponentDataSource, on_delete=models.SET_NULL, blank=True, null=True, related_name="components"
    )
    data_params = models.JSONField(default=default_config, blank=True, null=True)

    # Client refresh policy (0 = no auto refresh)
    refresh_interval_seconds = models.PositiveIntegerField(default=0)
    hydrate_on_client = models.BooleanField(
        default=True,
        help_text="If true, client calls /api/components/<uuid>/data/; otherwise you can embed data server-side.",
    )

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Page Component"
        verbose_name_plural = "Page Components"
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(page__isnull=False) & Q(home_page__isnull=True))
                    | (Q(page__isnull=True) & Q(home_page__isnull=False))
                ),
                name="pages_pagecomponent_single_parent",
            ),
            models.UniqueConstraint(
                fields=["page", "order"],
                condition=Q(page__isnull=False),
                name="uniq_component_order_per_page",
            ),
            models.UniqueConstraint(
                fields=["home_page", "order"],
                condition=Q(home_page__isnull=False),
                name="uniq_component_order_per_homepage",
            ),
        ]
        indexes = [
            models.Index(fields=["page", "is_enabled", "order"]),
            models.Index(fields=["home_page", "is_enabled", "order"]),
            models.Index(fields=["component_type"]),
            models.Index(fields=["data_source"]),
            models.Index(fields=["form"]),
        ]

    def clean(self):
        super().clean()

        # Exactly one parent
        if bool(self.page_id) == bool(self.home_page_id):
            raise ValidationError("Component must belong to exactly one of page or home_page.")

        # Data source must be enabled if set
        if self.data_source_id and not self.data_source.is_enabled:
            raise ValidationError("Selected data source is disabled.")

        # Form component validation
        if self.component_type == self.ComponentType.FORM:
            if not self.form_id:
                raise ValidationError("Form component must have a form selected.")
            if self.form and not self.form.is_active:
                raise ValidationError("Selected form is not active.")

        # Basic coherence for HTML
        if self.component_type == self.ComponentType.HTML:
            if not (self.html_content or self.image or self.background_image or self.config):
                raise ValidationError("HTML component should have html_content or assets/config.")

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        # Invalidate parent page/homepage cache
        self._invalidate_parent_cache()
        return result

    def _invalidate_parent_cache(self):
        """Invalidate cache for the parent page or home page."""
        if self.page_id:
            from .page import PAGE_CACHE_KEY_PREFIX

            cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.slug.{self.page.slug}")
        if self.home_page_id:
            from .home_page import HOMEPAGE_CACHE_KEY

            cache.delete(HOMEPAGE_CACHE_KEY)

    def __str__(self) -> str:
        parent_label = self.page.slug if self.page_id else self.home_page.name
        return f"{self.component_type} component for {parent_label} (order {self.order})"


class PageComponentImage(ProjectControlModel):
    """
    Optional: multiple images per component (carousel/gallery).
    Kept for backward compatibility — new code should use PageComponentAsset.
    """

    image_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    component = models.ForeignKey(PageComponent, on_delete=models.CASCADE, related_name="images")

    order = models.PositiveIntegerField(default=0, db_index=True)
    image = models.ImageField(upload_to="page_components/images/")
    alt = models.CharField(max_length=255, blank=True, default="")
    caption = models.CharField(max_length=255, blank=True, default="")
    link = models.URLField(blank=True, default="")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Page Component Image"
        verbose_name_plural = "Page Component Images"
        constraints = [
            models.UniqueConstraint(fields=["component", "order"], name="uniq_component_image_order"),
        ]
        indexes = [
            models.Index(fields=["component", "order"]),
        ]

    def __str__(self) -> str:
        return f"Image {self.order} for {self.component.name}"


class PageComponentAsset(ProjectControlModel):
    """
    General-purpose static asset attached to a PageComponent.
    Supports images, videos, audio, CSS, JS, PDFs, and any other file type.
    """

    class AssetType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"
        CSS = "css", "CSS"
        JS = "js", "JavaScript"
        PDF = "pdf", "PDF"
        OTHER = "other", "Other"

    asset_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    component = models.ForeignKey(PageComponent, on_delete=models.CASCADE, related_name="assets")

    file = models.FileField(upload_to="page_components/assets/")
    asset_type = models.CharField(
        max_length=16,
        choices=AssetType.choices,
        default=AssetType.OTHER,
        db_index=True,
        help_text="Auto-detected from MIME type on upload; can be corrected manually.",
    )

    order = models.PositiveIntegerField(default=0, db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")
    caption = models.CharField(max_length=255, blank=True, default="")
    link = models.URLField(blank=True, default="")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Page Component Asset"
        verbose_name_plural = "Page Component Assets"
        constraints = [
            models.UniqueConstraint(fields=["component", "order"], name="uniq_component_asset_order"),
        ]
        indexes = [
            models.Index(fields=["component", "order"]),
            models.Index(fields=["asset_type"]),
        ]

    @staticmethod
    def detect_asset_type(content_type: str, filename: str = "") -> str:
        """Infer AssetType from MIME content_type or filename extension."""
        ct = (content_type or "").lower()
        if ct.startswith("image/"):
            return PageComponentAsset.AssetType.IMAGE
        if ct.startswith("video/"):
            return PageComponentAsset.AssetType.VIDEO
        if ct.startswith("audio/"):
            return PageComponentAsset.AssetType.AUDIO
        if ct in ("text/css",):
            return PageComponentAsset.AssetType.CSS
        if ct in ("application/javascript", "text/javascript"):
            return PageComponentAsset.AssetType.JS
        if ct == "application/pdf":
            return PageComponentAsset.AssetType.PDF

        # Fallback: check extension
        import os

        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        ext_map = {
            "css": PageComponentAsset.AssetType.CSS,
            "js": PageComponentAsset.AssetType.JS,
            "pdf": PageComponentAsset.AssetType.PDF,
        }
        return ext_map.get(ext, PageComponentAsset.AssetType.OTHER)

    def __str__(self) -> str:
        return f"{self.get_asset_type_display()} asset {self.order} for {self.component.name}"
