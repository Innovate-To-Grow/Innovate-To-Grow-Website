from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from core.models import ProjectControlModel

FIELD_TYPES = [
    "text",
    "integer",
    "float",
    "boolean",
    "date",
    "datetime",
    "email",
    "url",
    "json",
]


class MiniAppDataSchema(ProjectControlModel):
    """Defines the data schema (field definitions) for a mini-app's data records."""

    app = models.OneToOneField("miniapps.MiniApp", on_delete=models.CASCADE, related_name="data_schema")
    fields = models.JSONField(
        default=list,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text='Array of field definitions: [{"name": "title", "type": "text", "required": true, "max_length": 200}]',
    )

    class Meta:
        verbose_name = "Data Schema"
        verbose_name_plural = "Data Schemas"

    def __str__(self):
        field_count = len(self.fields) if self.fields else 0
        return f"Schema for {self.app.title} ({field_count} fields)"
