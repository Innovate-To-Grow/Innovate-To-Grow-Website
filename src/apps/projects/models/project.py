from django.db import models

from apps.core.models import ProjectControlModel


class Project(ProjectControlModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual / CSV"
        SHEET = "sheet", "Google Sheet"

    semester = models.ForeignKey("projects.Semester", on_delete=models.CASCADE, related_name="projects")
    class_code = models.CharField(max_length=20, blank=True, default="", db_index=True)
    team_number = models.CharField(max_length=20, blank=True, default="")
    team_name = models.CharField(max_length=255, blank=True, default="")
    project_title = models.CharField(max_length=500)
    organization = models.CharField(max_length=255, blank=True, default="")
    industry = models.CharField(max_length=100, blank=True, default="", db_index=True)
    abstract = models.TextField(blank=True, default="")
    student_names = models.TextField(blank=True, default="")
    track = models.PositiveIntegerField(null=True, blank=True)
    presentation_order = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.MANUAL,
        db_index=True,
        help_text=(
            "Where this row came from. Google-Sheet-synced rows are replaced on every sync; "
            "manual/CSV rows are never touched by the sync."
        ),
    )

    class Meta:
        ordering = ["semester", "class_code", "team_number"]
        indexes = [
            models.Index(fields=["semester", "class_code"]),
            models.Index(fields=["semester", "track", "presentation_order"]),
        ]

    def __str__(self):
        if self.team_number:
            return f"Team {self.team_number} - {self.project_title[:60]}"
        return self.project_title[:60]
