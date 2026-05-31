"""FrozenPage: an external webpage captured ("frozen") into self-contained HTML.

Mirrors the CMSEmbedWidget pattern — a standalone model that the ``frozen_page``
block references by UUID. The captured document (CSS inlined, assets base64,
scripts stripped) is served into a sandboxed iframe by ``FrozenPageDocumentView``.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.models import ProjectControlModel

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_CHOICES = [
    (STATUS_DRAFT, "Draft"),
    (STATUS_PUBLISHED, "Published"),
]

# (model field name, freeze-service preset key). Keep keys in sync with
# apps.cms.services.freeze.REMOVAL_PRESETS.
_PRESET_FIELDS = [
    ("remove_header", "header"),
    ("remove_nav", "nav"),
    ("remove_footer", "footer"),
    ("remove_cookie_consent", "cookie_consent"),
    ("remove_ads", "ads"),
]


class FrozenPage(ProjectControlModel):
    source_url = models.URLField(max_length=2000, help_text="The external page URL to capture.")
    title = models.CharField(max_length=300, blank=True, default="", help_text="Defaults to the source page's <title>.")
    slug = models.SlugField(max_length=200, unique=True, help_text="Stable identifier (kebab-case).")
    frozen_html = models.TextField(blank=True, default="", help_text="The captured self-contained HTML document.")

    remove_header = models.BooleanField(default=False, help_text="Strip page headers / banners on import.")
    remove_nav = models.BooleanField(default=False, help_text="Strip navigation bars / menus on import.")
    remove_footer = models.BooleanField(default=False, help_text="Strip page footers on import.")
    remove_cookie_consent = models.BooleanField(default=False, help_text="Strip cookie / consent banners on import.")
    remove_ads = models.BooleanField(default=False, help_text="Strip ad / advertisement blocks on import.")
    extra_remove_selectors = models.TextField(
        blank=True,
        default="",
        help_text="Extra CSS selectors to remove, one per line (e.g. '.newsletter-popup').",
    )

    fetched_at = models.DateTimeField(null=True, blank=True, help_text="When the document was last captured.")
    byte_size = models.PositiveIntegerField(default=0, help_text="Size of the captured document in bytes.")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)

    class Meta:
        db_table = "cms_frozenpage"
        ordering = ["-updated_at"]
        verbose_name = "Frozen Page"
        verbose_name_plural = "Frozen Pages"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.title or self.slug} ({self.slug})"

    def selected_presets(self) -> tuple[str, ...]:
        return tuple(preset for field, preset in _PRESET_FIELDS if getattr(self, field))

    def selected_selectors(self) -> list[str]:
        return [line.strip() for line in (self.extra_remove_selectors or "").splitlines() if line.strip()]

    def is_visible(self) -> bool:
        """A frozen page is renderable only once published and actually captured."""
        return self.status == STATUS_PUBLISHED and bool(self.frozen_html)

    def re_freeze(self) -> None:
        """(Re-)capture ``source_url`` with the current removal options and update the fields.

        Raises the freeze service's BlockedURLError / FreezeError on failure; the
        caller (admin) is responsible for surfacing those to the user.
        """
        from apps.cms.services.freeze import freeze_url

        result = freeze_url(
            self.source_url,
            remove_presets=self.selected_presets(),
            extra_selectors=self.selected_selectors(),
        )
        self.frozen_html = result.html
        self.byte_size = result.byte_size
        self.fetched_at = timezone.now()
        if not self.title and result.title:
            self.title = result.title
