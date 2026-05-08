from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from core.models import ProjectControlModel

from .block_types import BLOCK_TYPE_CHOICES, normalize_block_data_for_storage, validate_block_data
from .cms_page import CMSPage


class CMSBlock(ProjectControlModel):
    """A content block within a CMS page."""

    page = models.ForeignKey(CMSPage, on_delete=models.CASCADE, related_name="blocks")
    block_type = models.CharField(max_length=30, choices=BLOCK_TYPE_CHOICES)
    sort_order = models.IntegerField(default=0)
    data = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    admin_label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Label shown in admin for easier identification.",
    )

    class Meta:
        db_table = "cms_cmsblock"
        ordering = ["sort_order"]
        verbose_name = "Content Block"
        verbose_name_plural = "Content Blocks"
        indexes = [
            models.Index(fields=["page", "sort_order"]),
        ]

    def __str__(self):
        label = self.admin_label or self.get_block_type_display()
        return f"{label} (#{self.sort_order})"

    def clean(self):
        super().clean()
        validate_block_data(self.block_type, self.data)
        self.data = normalize_block_data_for_storage(self.block_type, self.data)
