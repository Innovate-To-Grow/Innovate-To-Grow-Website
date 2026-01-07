"""
Past Projects models for storing shared project URLs.
"""

import uuid
from django.db import models


class SharedProjectURL(models.Model):
    """
    Model for storing shared project URLs with UUID identifiers.
    
    Stores team names and team numbers that can be used to filter
    and display specific projects from the past projects dataset.
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the shared URL."
    )

    team_names = models.JSONField(
        default=list,
        help_text="List of team names to filter projects."
    )

    team_numbers = models.JSONField(
        default=list,
        help_text="List of team numbers to filter projects."
    )

    project_keys = models.JSONField(
        default=list,
        blank=True,
        help_text="List of unique project keys (JSON strings) for precise matching."
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this shared URL was created."
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional expiration date for the shared URL."
    )

    class Meta:
        verbose_name = "Shared Project URL"
        verbose_name_plural = "Shared Project URLs"
        ordering = ['-created_at']

    def __str__(self):
        return f"Shared URL: {self.uuid}"

