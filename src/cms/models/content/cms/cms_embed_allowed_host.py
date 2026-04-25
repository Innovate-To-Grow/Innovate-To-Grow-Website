import re

from django.core.exceptions import ValidationError
from django.db import models

from core.models import ProjectControlModel

HOST_RE = re.compile(r"^(?:\*\.)?[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


class CMSEmbedAllowedHost(ProjectControlModel):
    """Admin-managed allowlist of hosts that may be embedded via CMS `embed` blocks.

    The `hostname` field may be an exact host (e.g. `docs.google.com`) or a
    subdomain wildcard (e.g. `*.youtube.com`). All values are stored
    lowercase.
    """

    hostname = models.CharField(
        max_length=255,
        unique=True,
        help_text="Exact host like 'docs.google.com' or wildcard like '*.youtube.com'.",
    )
    description = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "cms_cmsembedallowedhost"
        ordering = ["hostname"]
        verbose_name = "CMS Embed Allowed Host"
        verbose_name_plural = "CMS Embed Allowed Hosts"

    def __str__(self):
        return self.hostname

    def clean(self):
        super().clean()
        value = (self.hostname or "").strip().lower()
        if not value or not HOST_RE.match(value):
            raise ValidationError({"hostname": "Use a valid host like 'example.com' or wildcard like '*.example.com'."})
        self.hostname = value
