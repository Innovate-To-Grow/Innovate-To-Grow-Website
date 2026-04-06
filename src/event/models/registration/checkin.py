from django.conf import settings
from django.db import models

from core.models import ProjectControlModel


class CheckIn(ProjectControlModel):
    event = models.ForeignKey("event.Event", on_delete=models.CASCADE, related_name="check_ins")
    name = models.CharField(max_length=255, help_text='E.g. "Main Entrance", "VIP Gate", "Morning Session"')
    is_active = models.BooleanField(default=True, help_text="Whether this check-in point is currently accepting scans.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event.name} — {self.name}"

    @property
    def scan_count(self):
        return self.records.count()


class CheckInRecord(ProjectControlModel):
    check_in = models.ForeignKey(CheckIn, on_delete=models.CASCADE, related_name="records")
    registration = models.ForeignKey(
        "event.EventRegistration", on_delete=models.CASCADE, related_name="check_in_records"
    )
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["check_in", "registration"],
                name="unique_checkin_per_registration",
            ),
        ]

    def __str__(self):
        return f"{self.registration.attendee_name} @ {self.check_in.name}"
